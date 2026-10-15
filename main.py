
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ==================================================
# 1. 기본 화면 설정
# ==================================================
st.set_page_config(
    page_title="동네별 인구 피라미드",
    page_icon="🏘️",
    layout="wide"
)

# 따뜻한 색상을 사용한 화면 디자인
st.markdown("""
<style>
    .stApp {
        background-color: #FFF9F2;
    }

    h1, h2, h3 {
        color: #754C38;
    }

    div[data-testid="stMetric"] {
        background-color: #FFF0DF;
        border: 1px solid #F0D5B8;
        padding: 15px;
        border-radius: 12px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏘️ 동네별 인구 피라미드")
st.write(
    "우리 동네의 연령별 인구를 살펴보세요. "
    "남자는 왼쪽, 여자는 오른쪽에 표시됩니다."
)

# ==================================================
# 2. 데이터 불러오기
# ==================================================
# GitHub의 ZIP 파일을 직접 내려받는 주소
DATA_URL = (
    "https://raw.githubusercontent.com/"
    "yjgj0908/yg-population/main/"
    "population_ts_yearly_gender.zip"
)


@st.cache_data(show_spinner="전국 인구 데이터를 불러오는 중...")
def load_data():
    # pandas가 ZIP 파일을 직접 읽도록 설정
    data = pd.read_csv(DATA_URL, compression="zip")

    # 열 이름에 불필요한 공백이 있다면 제거
    data.columns = data.columns.astype(str).str.strip()

    # 연도 열을 숫자로 변환
    data["연도"] = pd.to_numeric(
        data["연도"], errors="coerce"
    )

    # 연도가 없는 행은 제외
    data = data.dropna(subset=["연도"])
    data["연도"] = data["연도"].astype(int)

    # 숫자 형태의 인구 데이터가 문자로 읽혔다면 숫자로 변환
    age_columns = [
        col for col in data.columns
        if col.startswith("남_") or col.startswith("여_")
    ]

    for col in age_columns:
        data[col] = pd.to_numeric(
            data[col].astype(str).str.replace(",", "", regex=False),
            errors="coerce"
        ).fillna(0)

    # 지역명 누락 행은 선택 과정에서 혼란을 줄 수 있으므로 제외
    for col in ["시도", "시군구", "동"]:
        data[col] = data[col].fillna("").astype(str).str.strip()

    return data


try:
    df = load_data()

except Exception as e:
    st.error("인구 데이터를 불러오지 못했습니다.")
    st.info(
        "인터넷 연결과 GitHub 저장소의 ZIP 파일 주소를 확인해 주세요."
    )
    st.caption(f"오류 내용: {e}")
    st.stop()


# ==================================================
# 3. 가장 최신 연도만 선택
# ==================================================
latest_year = int(df["연도"].max())
df_latest = df[df["연도"] == latest_year].copy()

# 필요한 지역 정보 열이 있는지 확인
required_columns = ["시도", "시군구", "동"]

missing_columns = [
    col for col in required_columns
    if col not in df_latest.columns
]

if missing_columns:
    st.error(
        "데이터에서 지역 열을 찾을 수 없습니다: "
        + ", ".join(missing_columns)
    )
    st.stop()


# ==================================================
# 4. 나이 라벨을 0세부터 100세 이상까지 직접 생성
# ==================================================
# 정렬 옵션에 의존하지 않고 원하는 순서를 직접 지정
ages = [f"{i}세" for i in range(101)]
ages.append("100세 이상")

# 데이터에 실제로 존재하는 연령 열만 사용
male_columns = [f"남_{age}" for age in ages]
female_columns = [f"여_{age}" for age in ages]

missing_age_columns = [
    col for col in male_columns + female_columns
    if col not in df_latest.columns
]

if missing_age_columns:
    st.error(
        "일부 연령별 인구 열을 찾을 수 없습니다. "
        "CSV의 열 이름을 확인해 주세요."
    )
    st.write("찾지 못한 열:", missing_age_columns[:10])
    st.stop()


# ==================================================
# 5. 시도 → 시군구 → 동 드롭다운
# ==================================================
st.subheader("📍 지역 선택")

col1, col2, col3 = st.columns(3)

with col1:
    sido_list = sorted(
        df_latest["시도"].unique().tolist()
    )
    selected_sido = st.selectbox(
        "① 시도",
        sido_list,
        key="sido"
    )

# 선택한 시도에 속하는 시군구만 표시
sigung_df = df_latest[
    df_latest["시도"] == selected_sido
]

sigung_list = sorted(
    sigung_df["시군구"].unique().tolist()
)

with col2:
    selected_sigung = st.selectbox(
        "② 시군구",
        sigung_list,
        key="sigung"
    )

# 선택한 시군구에 속하는 동만 표시
dong_df = sigung_df[
    sigung_df["시군구"] == selected_sigung
]

dong_list = sorted(
    dong_df["동"].unique().tolist()
)

with col3:
    selected_dong = st.selectbox(
        "③ 동",
        dong_list,
        key="dong"
    )


# ==================================================
# 6. 선택한 지역의 인구 데이터 추출
# ==================================================
selected_df = df_latest[
    (df_latest["시도"] == selected_sido)
    & (df_latest["시군구"] == selected_sigung)
    & (df_latest["동"] == selected_dong)
]

if selected_df.empty:
    st.warning("선택한 지역의 인구 데이터가 없습니다.")
    st.stop()

if len(selected_df) > 1:
    st.warning(
        "같은 지역에 해당하는 행이 여러 개 있습니다. "
        "데이터의 지역 구분을 확인해 주세요."
    )

# 해당 지역의 첫 번째 행을 사용
row = selected_df.iloc[0]

# 나이 순서를 유지한 채 인구 수를 추출
male_population = np.array(
    [row[col] for col in male_columns],
    dtype=float
)

female_population = np.array(
    [row[col] for col in female_columns],
    dtype=float
)

# 남자 인구는 음수로 바꿔 왼쪽에 표시
male_values = -male_population

# 여자 인구는 양수로 유지해 오른쪽에 표시
female_values = female_population

total_male = int(male_population.sum())
total_female = int(female_population.sum())
total_population = total_male + total_female


# ==================================================
# 7. 지역 인구 요약
# ==================================================
st.divider()

st.subheader(
    f"📊 {selected_sido} {selected_sigung} {selected_dong}"
)

st.caption(f"기준 연도: {latest_year}년")

metric1, metric2, metric3 = st.columns(3)

metric1.metric("전체 인구", f"{total_population:,}명")
metric2.metric("남자 인구", f"{total_male:,}명")
metric3.metric("여자 인구", f"{total_female:,}명")


# ==================================================
# 8. Plotly 인구 피라미드
# ==================================================
fig = go.Figure()

# 남자: 음수 값으로 왼쪽 막대 생성
fig.add_trace(
    go.Bar(
        y=ages,
        x=male_values,
        name="남자",
        orientation="h",
        marker_color="#D98C68",
        hovertemplate=(
            "나이: %{y}<br>"
            "남자 인구: %{customdata:,}명"
            "<extra></extra>"
        ),
        customdata=male_population
    )
)

# 여자: 양수 값으로 오른쪽 막대 생성
fig.add_trace(
    go.Bar(
        y=ages,
        x=female_values,
        name="여자",
        orientation="h",
        marker_color="#E8A6A1",
        hovertemplate=(
            "나이: %{y}<br>"
            "여자 인구: %{x:,}명"
            "<extra></extra>"
        )
    )
)

# 인구 수가 음수로 표시되는 왼쪽 축도 절댓값 기준으로 보이게 설정
max_population = max(
    float(male_population.max()),
    float(female_population.max()),
    1
)

# 좌우 대칭 축 범위 설정
axis_limit = max_population * 1.1

fig.update_layout(
    title={
        "text": f"{selected_dong} 연령별 인구 분포",
        "x": 0.5,
        "xanchor": "center"
    },
    barmode="overlay",
    bargap=0.12,
    height=1100,
    plot_bgcolor="#FFFDF9",
    paper_bgcolor="#FFF9F2",
    font=dict(
        family="Arial, sans-serif",
        size=12,
        color="#5C4638"
    ),
    legend=dict(
        title="성별",
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="center",
        x=0.5
    ),
    xaxis=dict(
        title="인구 수 (명)",
        range=[-axis_limit, axis_limit],
        tickmode="array",
        tickvals=np.linspace(
            -axis_limit, axis_limit, 9
        ),
        # 왼쪽의 음수 눈금은 양수 인구 수로 표시
        ticktext=[
            f"{abs(int(v)):,}"
            for v in np.linspace(
                -axis_limit, axis_limit, 9
            )
        ],
        zeroline=True,
        zerolinecolor="#8C7668",
        zerolinewidth=1.5,
        gridcolor="#EDE2D8"
    ),
    yaxis=dict(
        title="나이",
        # 중요: 나이 라벨을 0세 → 100세 이상 순서로 직접 고정
        categoryorder="array",
        categoryarray=ages,
        # 자동으로 순서를 뒤집지 않도록 명시
        autorange=True,
        tickmode="array",
        tickvals=ages,
        ticktext=ages
    ),
    margin=dict(
        l=85,
        r=40,
        t=100,
        b=70
    )
)

# 그래프 표시
st.plotly_chart(
    fig,
    use_container_width=True
)

# ==================================================
# 9. 그래프 읽는 법
# ==================================================
with st.expander("💡 인구 피라미드 읽는 법"):
    st.markdown("""
    - **왼쪽 주황색:** 남자 인구
    - **오른쪽 분홍색:** 여자 인구
    - **가로 막대의 길이:** 해당 나이의 인구수
    - **세로축:** 아래쪽은 0세, 위쪽은 100세 이상
    - **가운데 0:** 남녀 인구를 나누는 기준선

    막대가 길수록 해당 나이의 인구가 많다는 뜻입니다.
    """)

# ==================================================
# 10. 원본 데이터 확인
# ==================================================
with st.expander("📋 선택한 지역의 연령별 인구표"):
    population_table = pd.DataFrame({
        "나이": ages,
        "남자 인구": male_population.astype(int),
        "여자 인구": female_population.astype(int)
    })

    st.dataframe(
        population_table,
        use_container_width=True,
        hide_index=True
    )

st.caption(
    "데이터 출처: "
    "yjgj0908/yg-population GitHub 저장소"
)
