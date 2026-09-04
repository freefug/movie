import datetime
import requests
import pandas as pd
import streamlit as st
import pytz

# 1. 페이지 기본 설정 (제목, 레이아웃)
st.set_page_config(
    page_title="어제 박스오피스",
    page_icon="🎬",
    layout="wide"
)

# 2. 한국 시간(KST) 기준 '어제' 날짜 계산 함수
def get_yesterday_kst():
    # 배포 서버의 시계와 상관없이 한국 시간대를 불러옵니다.
    kst = pytz.timezone('Asia/Seoul')
    now_kst = datetime.datetime.now(kst)
    yesterday_kst = now_kst - datetime.timedelta(days=1)
    # API 요청 형식인 YYYYMMDD 형태로 변환합니다.
    return yesterday_kst.strftime('%Y%m%d')

# 3. KOBIS API 데이터 호출 함수 (캐시 적용: 1시간 = 3600초)
@st.cache_data(ttl=3600)
def fetch_box_office_data(target_date):
    # Streamlit Secrets(비밀 금고)에서 API 키를 안전하게 불러옵니다.
    try:
        api_key = st.secrets["KOBIS_KEY"]
    except KeyError:
        return None, "secrets.toml에 KOBIS_KEY 설정이 없습니다. 비밀 금고를 확인해 주세요."

    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {
        "key": api_key,
        "targetDt": target_date
    }

    try:
        response = requests.get(url, timeout=10)
        # HTTP 응답 코드가 200이 아닌 경우 예외 처리
        if response.status_code != 200:
            return None, f"서버 통신 오류 (HTTP 상태 코드: {response.status_code})"

        data = response.json()

        # 인증키 오류 등이 발생했을 때 오는 faultInfo 확인
        if "faultInfo" in data:
            message = data["faultInfo"].get("message", "알 수 없는 API 오류")
            return None, f"KOBIS API 오류: {message} (인증키 KOBIS_KEY를 확인해 주세요.)"

        # 영화 목록 데이터 추출
        box_office_result = data.get("boxOfficeResult", {})
        daily_list = box_office_result.get("dailyBoxOfficeList", [])

        # 목록이 비어있는 경우
        if not daily_list:
            return None, "선택한 날짜의 박스오피스 데이터가 존재하지 않습니다."

        return daily_list, None

    except requests.exceptions.RequestException as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {str(e)}"
    except Exception as e:
        return None, f"데이터 처리 중 오류가 발생했습니다: {str(e)}"


# --- 메인 화면 구성 ---

target_date = get_yesterday_kst()
# 날짜를 읽기 쉬운 YYYY-MM-DD 형식으로 변환하여 제목에 표시
formatted_date = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:]}"

st.title(f"🎬 어제({formatted_date}) 일별 박스오피스")
st.caption("KOBIS(영화관입장권통합전산망) 공식 데이터를 활용합니다.")

# 데이터 불러오기
daily_list, error_message = fetch_box_office_data(target_date)

# 오류 발생 시 사용자 안내 화면 표시
if error_message:
    st.error("⚠️ 데이터를 불러올 수 없습니다.")
    st.warning(f"**상세 원인:** {error_message}")
    st.markdown("""
    **확인해보세요:**
    1. Streamlit Cloud 앱 설정의 **Secrets** 항목에 `KOBIS_KEY`가 올바르게 입력되어 있는지 확인하세요.
    2. KOBIS 개발자 센터에서 발급받은 인증키가 유효한지 확인하세요.
    3. 인터넷 연결 또는 KOBIS 서버 상태를 확인하세요.
    """)
else:
    # 4. 데이터 전처리 (문자열 -> 숫자 변환)
    df = pd.DataFrame(daily_list)

    # 필요한 숫자로 변환할 컬럼들
    numeric_cols = ['rank', 'audiCnt', 'audiAcc', 'scrnCnt', 'showCnt']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 순위 기준 정렬
    df = df.sort_values(by='rank').reset_index(drop=True)

    # 5. 1위 영화 핵심 지표 카드 (Metric) 표시
    top_1 = df.iloc[0]
    st.subheader(f"🥇 1위 영화: {top_1['movieNm']}")

    col1, col2, col3 = st.columns(3)
    col1.metric("일별 관객수", f"{int(top_1['audiCnt']):,} 명")
    col2.metric("누적 관객수", f"{int(top_1['audiAcc']):,} 명")
    col3.metric("스크린 수", f"{int(top_1['scrnCnt']):,} 개")

    st.divider()

    # 6. 관객수 상위 5편 막대그래프 시각화
    st.subheader("📊 관객수 상위 5개 영화")
    top_5_df = df.head(5)
    
    # Streamlit 차트에 쓰기 위해 영화명을 인덱스로 설정
    chart_data = top_5_df.set_index("movieNm")[["audiCnt"]]
    chart_data.columns = ["관객수"]
    st.bar_chart(chart_data)

    st.divider()

    # 7. 전체 박스오피스 순위 표(Table) 표시
    st.subheader("📋 전체 순위 목록")

    # 표에 표시할 컬럼 선택 및 이름 변경
    display_df = df[['rank', 'movieNm', 'openDt', 'audiCnt', 'audiAcc', 'scrnCnt']].copy()
    display_df.columns = ['순위', '영화명', '개봉일', '관객수', '누적관객수', '스크린수']

    # 숫자 포맷 적용하여 출력
    st.dataframe(
        display_df,
        column_config={
            "순위": st.column_config.NumberColumn("순위", format="%d위"),
            "관객수": st.column_config.NumberColumn("관객수", format="%d명"),
            "누적관객수": st.column_config.NumberColumn("누적관객수", format="%d명"),
            "스크린수": st.column_config.NumberColumn("스크린수", format="%d개"),
        },
        use_container_width=True,
        hide_index=True
    )
