from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import pytz

# 페이지 기본 설정
st.set_page_config(
    page_title="일별 박스오피스 조회", page_icon="🎬", layout="wide"
)


# API 데이터 요청 함수 (캐싱: 1시간 동안 동일 날짜 요청 시 저장된 데이터 활용)
@st.cache_data(ttl=3600)
def fetch_box_office(api_key, target_date):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_date}

    try:
        response = requests.get(url, params=params, timeout=10)
        # HTTP 응답 코드 확인
        if response.status_code != 200:
            return None, f"서버 응답 오류 (상태 코드: {response.status_code})"

        data = response.json()

        # API 내부 인증 실패 또는 에러 응답 처리 (faultInfo 체크)
        if "faultInfo" in data:
            message = data["faultInfo"].get(
                "message", "인증키 문제로 오류가 발생했습니다."
            )
            return None, f"KOBIS API 오류: {message}"

        # 데이터 구조 추출
        box_office_result = data.get("boxOfficeResult", {})
        movie_list = box_office_result.get("dailyBoxOfficeList", [])

        # 영화 목록이 비어있는 경우
        if not movie_list:
            return None, "EMPTY_LIST"

        return movie_list, None

    except requests.exceptions.RequestException as e:
        return None, f"네트워크 통신 오류가 발생했습니다: {e}"


# 전날 대비 순위 증감 문자열 생성 함수 (화살표 추가)
def format_rank_change(rank_inten):
    if rank_inten > 0:
        return f"🔺 {rank_inten}"  # 순위 상승 (빨간 위 화살표)
    elif rank_inten < 0:
        return f"🔹 {abs(rank_inten)}"  # 순위 하강 (파란 아래 화살표)
    else:
        return "-"  # 변동 없음


# 메인 실행 함수
def main():
    st.title("🎬 일별 박스오피스 조회")

    # 1. API 키 불러오기 (streamlit secrets 활용)
    if "KOBIS_KEY" not in st.secrets:
        st.error("🔑 API 인증키가 설정되지 않았습니다!")
        st.info(
            "Streamlit Cloud의 **Secrets** 항목에 `KOBIS_KEY`를 추가해 주세요."
        )
        return

    api_key = st.secrets["KOBIS_KEY"]

    # 2. 날짜 선택 기준 설정 (한국 표준시 기준 최대 선택 가능일 = 어제)
    kst_tz = pytz.timezone("Asia/Seoul")
    now_kst = datetime.now(kst_tz)
    max_date = (now_kst - timedelta(days=1)).date()
    default_date = max_date

    # 사이드바 또는 메인 화면에서 날짜 선택 달력 제공
    selected_date = st.date_input(
        "📅 조회할 날짜를 선택하세요 (최대 어제까지 선택 가능):",
        value=default_date,
        max_value=max_date,
    )

    target_date_str = selected_date.strftime("%Y%m%d")
    formatted_date_display = selected_date.strftime("%Y년 %m월 %d일")

    st.write(f"📅 **선택한 날짜:** {formatted_date_display}")

    # 3. 데이터 수집
    movie_list, error_msg = fetch_box_office(api_key, target_date_str)

    # 4. 예외 및 오류 안내
    if error_msg:
        if error_msg == "EMPTY_LIST":
            st.warning("⚠️ 그날은 아직 집계 전입니다.")
        else:
            st.error("❌ 데이터를 불러올 수 없습니다.")
            st.warning(f"**상세 원인:** {error_msg}")

            # 사용자 조치 가이드 제공
            with st.expander("🛠️ 문제 해결 방법 안내"):
                st.markdown("""
                - **KOBIS 인증키 확인**: Streamlit Secrets에 입력한 인증키가 올바른지 확인해 주세요.
                - **네트워크 연결**: 잠시 후 다시 시도해 주세요.
                - **집계 시간**: 자정 직후에는 해당 일자 집계가 아직 진행 중일 수 있습니다.
                """)
        return

    # 5. 데이터 프레임 변환 및 전처리
    df = pd.DataFrame(movie_list)

    # 숫자형 변환 (문자열 -> 정수형/실수형)
    numeric_columns = [
        "rank",
        "rankInten",
        "audiCnt",
        "audiAcc",
        "scrnCnt",
        "showCnt",
    ]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # 정렬 (순위 기준)
    df = df.sort_values(by="rank", ascending=True)

    # 6. 트로피 이모지 및 순위 증감 화살표 열 가공
    # 누적관객 100만(1,000,000) 이상 영화명 뒤에 🏆 표시
    df["display_movieNm"] = df.apply(
        lambda row: f"{row['movieNm']} 🏆"
        if row["audiAcc"] >= 1000000
        else row["movieNm"],
        axis=1,
    )

    # 전날 대비 순위 증감 표시 가공
    df["display_rankInten"] = df["rankInten"].apply(format_rank_change)

    # 7. 1위 영화 지표 카드 (Metric) 출력
    top_movie = df.iloc[0]
    st.subheader(f"🥇 1위 영화: {top_movie['display_movieNm']}")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("일일 관객수", f"{int(top_movie['audiCnt']):,}명")
    with col2:
        st.metric("누적 관객수", f"{int(top_movie['audiAcc']):,}명")
    with col3:
        st.metric("스크린수", f"{int(top_movie['scrnCnt']):,}개")

    st.divider()

    # 8. 관객수 상위 5개 영화 시각화 (막대그래프)
    st.subheader("📊 일일 관객수 Top 5")
    top_5_df = df.head(5)

    fig = px.bar(
        top_5_df,
        x="display_movieNm",
        y="audiCnt",
        labels={"display_movieNm": "영화 제목", "audiCnt": "일일 관객수(명)"},
        text_auto=",",
    )
    fig.update_layout(xaxis_title="", yaxis_title="관객수 (명)")
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # 9. 전체 박스오피스 데이터 표 출력
    st.subheader("📋 박스오피스 전체 순위")

    # 표시용 데이터 프레임 가공
    display_df = df[
        [
            "rank",
            "display_rankInten",
            "display_movieNm",
            "openDt",
            "audiCnt",
            "audiAcc",
            "scrnCnt",
        ]
    ].copy()

    display_df.columns = [
        "순위",
        "순위증감",
        "영화명",
        "개봉일",
        "관객수",
        "누적관객",
        "스크린수",
    ]

    # 테이블 형태 출력 및 숫자에 천 단위 쉼표 추가
    st.dataframe(
        display_df.style.format(
            {"관객수": "{:,.0f}명", "누적관객": "{:,.0f}명", "스크린수": "{:,.0f}개"}
        ),
        hide_index=True,
        use_container_width=True,
    )


if __name__ == "__main__":
    main()
