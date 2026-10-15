
import re
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
st.write("시도, 시군구, 동을 선택하여 연령별 인구를 살펴보세요.")

# ==================================================
# 2. 데이터 불러오기
# ==================================================
DATA_URL = (
    "https://raw.githubusercontent.com/"
    "yjgj0908/yg-population/main/"
    "population_ts_yearly_gender.zip"
)


@st.cache_data(show_spinner="전국 인구 데이터를 불러오는 중...")
def load_data():
    # ZIP 파일을 pandas로 직접 읽음
    data = pd.read_csv(DATA_URL, compression="zip")

    # 열 이름 앞뒤의 공백 및 BOM 제거
    data.columns = [
        str(col).replace("\ufeff", "").strip()
        for col in data.columns
    ]

    # 연도 열을 숫자로 변환
    data["연도"] = pd.to_numeric(data["연도"], errors="coerce")
    data = data.dropna(subset=["연도"])
    data["연도"] = data["연도"].astype(int)

    # 지역 열 정리
    for col in ["시도", "시군구", "동"]:
        data[col] = data[col].fillna("").astype(str).str.strip()

    # 인구 열의 쉼표를 제거하고 숫자로 변환
    for col in data.columns:
        if col.startswith("남_") or col.startswith("여_"):
            data[col] = pd.to_numeric(
                data[col].astype(str).str.replace(",", "", regex=False),
                errors="coerce"
            ).fillna(0)

    return data


try:
    df = load_data()
except Exception as e:
    st.error("인구 데이터를 불러오지 못했습니다.")
    st.code(str(e))
    st.stop()

# ==================================================
# 3. 가장 최신 연도 선택
# ==================================================
latest_year = int(df["연도"].max())
df_latest = df[df["연도"] == latest_year].copy()

required_columns = ["시도", "시군구", "동"]
missing = [c for c in required_columns if c not in df_latest.columns]

if missing:
    st.error(f"필요한 지역 열이 없습니다: {missing}")
    st.stop()

# ==================================================
# 4. 연령별 열 이름 자동 인식
# ==================================================
# 화면에 표시할 연령 순서
ages = [f"{i}세" for i in range(100)] + ["100세 이상"]


def normalize_column_name(name):
    """공백, 밑줄 등 표기 차이를 줄여 열 이름을 비교한다."""
    name = str(name).strip().replace("\ufeff", "")
    name = name.replace(" ", "").replace("_", "")
    return name


# 정규화한 열 이름과 원래 열 이름의 연결표
column_map = {}
for col in df_latest.columns:
    normalized = normalize_column_name(col)
    column_map.setdefault(normalized, []).append(col)


def find_age_column(gender, age):
    """성별과 나이에 해당하는 실제 CSV 열 이름을 찾는다."""
    if age == "100세 이상":
        # 100세 이상은 여러 가지 표기를 허용한다.
        candidates = [
            f"{gender}100세이상",
            f"{gender}100세+",
            f"{gender}100세이상인구",
            f"{gender}100세초과",
        ]
    else:
        number = int(age.replace("세", ""))
        candidates = [
            f"{gender}{number}세",
        ]

    for candidate in candidates:
        normalized = normalize_column_name(candidate)
        matches = column_map.get(normalized, [])
        if matches:
            return matches[0]

    # 마지막 연령대의 열 이름을 더 유연하게 검색
    if age == "100세 이상":
        for col in df_latest.columns:
            normalized = normalize_column_name(col)

            if (
                normalized.startswith(gender)
                and "100세" in normalized
                and (
                    "이상" in normalized
                    or "+" in normalized
                    or "초과" in normalized
                )
            ):
                return col

    return None


male_columns = [find_age_column("남", age) for age in ages]
female_columns = [find_age_column("여", age) for age in ages]

missing_columns = []

for age, col in zip(ages, male_columns):
    if col is None:
        missing_columns.append(f"남_{age}")

for age, col in zip(ages, female_columns):
    if col is None:
        missing_columns.append(f"여_{age}")

if missing_columns:
    st.error("일부 연령별 인구 열을 찾을 수 없습니다.")
    st.write("찾지 못한 열:", missing_columns)

    st.write("📋 CSV에서 실제로 읽은 95세 이상 관련 열")
    st.code(
        "\n".join(
            str(c) for c in df_latest.columns
            if any(x in normalize_column_name(c)
                   for x in ["95세", "96세", "97세", "98세", "99세", "100세"])
        )
    )

    st.info(
        "실제 열 이름을 확인하면 해당 데이터 형식에 맞게 "
        "연령 열 연결을 수정할 수 있습니다."
    )
    st.stop()

# ==================================================
# 5. 지역 선택 드롭다운
# ==================================================
st.subheader("📍 지역 선택")

col1, col2, col3 = st.columns(3)

with col1:
    sido_list = sorted(df_latest["시도"].unique().tolist())
    selected_sido = st.selectbox("① 시도", sido_list)

sigung_df = df_latest[df_latest["시도"] == selected_sido]
sigung_list = sorted(sigung_df["시군구"].unique().tolist())

with col2:
    selected_sigung = st.selectbox("② 시군구", sigung_list)

dong_df = sigung_df[sigung_df["시군구"] == selected_sigung]
dong_list = sorted(dong_df["동"].unique().tolist())

with col3:
    selected_dong = st.selectbox("③ 동", dong_list)

# ==================================================
# 6. 선택한 지역의 인구 추출
# ==================================================
selected_df = df_latest[
    (df_latest["시도"] == selected_sido)
    & (df_latest["시군구"] == selected_sigung)
    & (df_latest["동"] == selected_dong)
]

if selected_df.empty:
    st.warning("선택한 지역의 데이터가 없습니다.")
    st.stop()

if len(selected_df) > 1:
    st.warning(
        "같은 지역에 해당하는 행이 여러 개입니다. "
        "첫 번째 행을 표시합니다."
    )

row = selected_df.iloc[0]

male_population = np.array(
    [row[col] for col in male_columns], dtype=float
)
female_population = np.array(
    [row[col] for col in female_columns], dtype=float
)

male_values = -male_population
female_values = female_population

total_male = int(male_population.sum())
total_female = int(female_population.sum())
total_population = total_male + total_female

# ==================================================
# 7. 인구 요약
# ==================================================
st.divider()
st.subheader(f"📊 {selected_sido} {selected_sigung} {selected_dong}")
st.caption(f"기준 연도: {latest_year}년")

m1, m2, m3 = st.columns(3)
m1.metric("전체 인구", f"{total_population:,}명")
m2.metric("남자 인구", f"{total_male:,}명")
m3.metric("여자 인구", f"{total_female:,}명")

# ==================================================
# 8. 인구 피라미드 그래프
# ==================================================
fig = go.Figure()

fig.add_trace(go.Bar(
    y=ages,
    x=male_values,
    name="남자",
    orientation="h",
    marker_color="#D98C68",
    customdata=male_population,
    hovertemplate=(
        "나이: %{y}<br>"
        "남자 인구: %{customdata:,.0f}명"
        "<extra></extra>"
    )
))

fig.add_trace(go.Bar(
    y=ages,
    x=female_values,
    name="여자",
    orientation="h",
    marker_color="#E8A6A1",
    hovertemplate=(
        "나이: %{y}<br>"
        "여자 인구: %{x:,.0f}명"
        "<extra></extra>"
    )
))

max_population = max(
    float(male_population.max()),
    float(female_population.max()),
    1
)
axis_limit = max_population * 1.1

# 가로축 눈금은 음수 대신 절댓값으로 표시
tick_values = np.linspace(-axis_limit, axis_limit, 9)
tick_text = [f"{abs(int(v)):,}" for v in tick_values]

fig.update_layout(
    title={
        "text": f"{selected_dong} 연령별 인구 피라미드",
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
        tickvals=tick_values,
        ticktext=tick_text,
        zeroline=True,
        zerolinecolor="#8C7668",
        zerolinewidth=1.5,
        gridcolor="#EDE2D8"
    ),
    yaxis=dict(
        title="나이",
        # 나이 라벨을 지정한 순서대로 배치
        categoryorder="array",
        categoryarray=ages,
        tickmode="array",
        tickvals=ages,
        ticktext=ages,
        # 명시적으로 전체 축을 반전하지 않음
        autorange=True
    ),
    margin=dict(l=85, r=40, t=100, b=70)
)

st.plotly_chart(fig, use_container_width=True)

# ==================================================
# 9. 그래프 설명
# ==================================================
with st.expander("💡 인구 피라미드 읽는 법"):
    st.markdown("""
    - **왼쪽 주황색:** 남자 인구
    - **오른쪽 분홍색:** 여자 인구
    - **막대 길이:** 해당 나이의 인구수
    - **세로축 아래:** 0세
    - **세로축 위:** 100세 이상
    """)

# ==================================================
# 10. 연령별 인구표
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

st.caption("데이터 출처: yjgj0908/yg-population GitHub 저장소")
