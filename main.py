
import re
import requests
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ==================================================
# 1. 기본 화면 설정
# ==================================================
st.set_page_config(
    page_title="전국 고령화 단계구분도 (2026)",
    page_icon="🗺️",
    layout="wide",
)

st.title("🗺️ 전국 시군구별 고령화 단계구분도")
st.caption("2026년 기준 · 시군구별 65세 이상 인구 비율")

# ==================================================
# 2. 데이터 URL
# ==================================================
POPULATION_DATA_URL = (
    "https://raw.githubusercontent.com/"
    "yjgj0908/yg-population/main/"
    "population_ts_yearly_gender.zip"
)

GEOJSON_URL = (
    "https://raw.githubusercontent.com/"
    "yjgj0908/yg-population/main/"
    "sigungu_kr.geojson.txt"
)

TARGET_YEAR = 2026


# ==================================================
# 3. 공통 함수
# ==================================================
def normalize_code(value, length=5):
    """행정구역 코드를 숫자 문자열로 정규화합니다."""
    if pd.isna(value):
        return ""

    value = str(value).strip()

    # CSV에서 11110.0 형태로 읽힌 경우 처리
    if re.fullmatch(r"\d+\.0+", value):
        value = value.split(".")[0]

    # 숫자 이외 문자가 포함된 코드 방어
    digits = re.sub(r"\D", "", value)

    if not digits:
        return ""

    return digits.zfill(length)


def parse_number(series):
    """쉼표가 있는 인구 데이터를 숫자로 변환합니다."""
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.strip(),
        errors="coerce",
    ).fillna(0)


# ==================================================
# 4. 인구 데이터 로드 및 전처리
# ==================================================
@st.cache_data(show_spinner="전국 인구 데이터를 불러오는 중...")
def load_population_data():
    response = requests.get(
        POPULATION_DATA_URL,
        timeout=60,
    )
    response.raise_for_status()

    from io import BytesIO

    df = pd.read_csv(
        BytesIO(response.content),
        compression="zip",
        dtype={"코드": str},
        low_memory=False,
    )

    # 컬럼명 정리
    df.columns = [
        str(col).replace("\ufeff", "").strip()
        for col in df.columns
    ]

    required_columns = {"연도", "코드", "시도", "시군구"}

    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(
            f"인구 데이터에 필요한 컬럼이 없습니다: {sorted(missing)}"
        )

    # 연도 처리
    df["연도"] = pd.to_numeric(df["연도"], errors="coerce")

    available_years = sorted(
        df["연도"].dropna().astype(int).unique().tolist()
    )

    if not available_years:
        raise ValueError("인구 데이터에서 유효한 연도를 찾지 못했습니다.")

    selected_year = (
        TARGET_YEAR
        if TARGET_YEAR in available_years
        else max(available_years)
    )

    year_df = df[df["연도"] == selected_year].copy()

    if year_df.empty:
        raise ValueError(f"{selected_year}년 데이터가 없습니다.")

    # 행정구역 코드 정리
    year_df["코드"] = year_df["코드"].apply(
        lambda x: normalize_code(x, 8)
    )
    year_df = year_df[year_df["코드"] != ""].copy()
    year_df["시군구코드"] = year_df["코드"].str[:5]

    # '계_'로 시작하는 연령별 총인구 열 찾기
    age_columns = [
        col for col in year_df.columns
        if col.startswith("계_")
    ]

    if not age_columns:
        raise ValueError(
            "연령별 인구 컬럼을 찾을 수 없습니다. "
            "데이터의 실제 컬럼명을 확인하세요."
        )

    # 65세 이상 열 선택
    elderly_columns = []

    for col in age_columns:
        age_label = col.replace("계_", "").strip()

        match = re.match(r"^(\d+)\s*세", age_label)

        if match and int(match.group(1)) >= 65:
            elderly_columns.append(col)

    if not elderly_columns:
        raise ValueError(
            "65세 이상 인구 컬럼을 찾지 못했습니다. "
            "연령별 컬럼명이 예상 형식과 다른지 확인하세요."
        )

    # 인구 열 숫자 변환
    for col in age_columns:
        year_df[col] = parse_number(year_df[col])

    # 동별 총인구 및 고령인구 계산
    year_df["총인구"] = year_df[age_columns].sum(axis=1)
    year_df["고령인구"] = year_df[elderly_columns].sum(axis=1)

    # 시군구별 집계
    grouped = (
        year_df.groupby("시군구코드", as_index=False)
        .agg(
            시도=("시도", "first"),
            시군구=("시군구", "first"),
            총인구=("총인구", "sum"),
            고령인구=("고령인구", "sum"),
        )
    )

    # 고령화율 계산
    grouped["고령화율"] = np.where(
        grouped["총인구"] > 0,
        grouped["고령인구"] / grouped["총인구"] * 100,
        np.nan,
    )

    grouped["기준연도"] = selected_year

    return grouped, selected_year


# ==================================================
# 5. GeoJSON 지도 로드
# ==================================================
@st.cache_data(show_spinner="시군구 경계 지도를 불러오는 중...")
def load_geojson():
    response = requests.get(GEOJSON_URL, timeout=60)
    response.raise_for_status()

    data = response.json()

    if data.get("type") != "FeatureCollection":
        raise ValueError(
            "지도 파일이 올바른 GeoJSON FeatureCollection 형식이 아닙니다."
        )

    if not data.get("features"):
        raise ValueError("GeoJSON에 지도 경계 데이터가 없습니다.")

    # 지도 코드 통일
    for feature in data["features"]:
        properties = feature.setdefault("properties", {})

        code = normalize_code(properties.get("코드"), 5)

        if not code:
            code = normalize_code(feature.get("id"), 5)

        properties["코드"] = code

    return data


# ==================================================
# 6. 데이터 로드
# ==================================================
try:
    sigungu_df, selected_year = load_population_data()
    geojson = load_geojson()

except Exception as e:
    st.error("데이터를 불러오는 중 오류가 발생했습니다.")
    st.exception(e)
    st.stop()

# 코드가 없는 지도 경계 제외
geojson["features"] = [
    feature
    for feature in geojson["features"]
    if feature.get("properties", {}).get("코드")
]

# 지도에 있는 코드 기준으로 지역명 보정
geojson_map = {}

for feature in geojson["features"]:
    properties = feature["properties"]
    code = properties["코드"]

    geojson_map[code] = {
        "시도": properties.get("시도", ""),
        "시군구": properties.get("시군구", ""),
    }

sigungu_df["지역명"] = sigungu_df["시군구코드"].map(
    lambda code: geojson_map.get(code, {}).get("시군구", "")
)

sigungu_df["시도명"] = sigungu_df["시군구코드"].map(
    lambda code: geojson_map.get(code, {}).get("시도", "")
)

sigungu_df["시군구"] = sigungu_df["지역명"].where(
    sigungu_df["지역명"] != "",
    sigungu_df["시군구"],
)

sigungu_df["시도"] = sigungu_df["시도명"].where(
    sigungu_df["시도명"] != "",
    sigungu_df["시도"],
)

# 지도에 표시할 수 있는 데이터만 사용
map_codes = {
    feature["properties"]["코드"]
    for feature in geojson["features"]
}

map_df = sigungu_df[
    sigungu_df["시군구코드"].isin(map_codes)
    & sigungu_df["고령화율"].notna()
].copy()

if map_df.empty:
    st.error(
        "인구 데이터와 지도 경계의 시군구 코드가 일치하지 않습니다. "
        "CSV의 코드와 GeoJSON의 properties['코드']를 확인하세요."
    )
    st.stop()


# ==================================================
# 7. 요약 지표
# ==================================================
total_population = sigungu_df["총인구"].sum()
total_elderly = sigungu_df["고령인구"].sum()

avg_aging_rate = (
    total_elderly / total_population * 100
    if total_population > 0
    else 0
)

max_row = sigungu_df.loc[
    sigungu_df["고령화율"].idxmax()
]

col1, col2, col3 = st.columns(3)

col1.metric(
    "총 분석 시군구",
    f"{len(sigungu_df):,}개",
)

col2.metric(
    "전국 평균 고령화율",
    f"{avg_aging_rate:.1f}%",
)

col3.metric(
    "최고 고령화 지역",
    f"{max_row['시도']} {max_row['시군구']}",
    f"{max_row['고령화율']:.1f}%",
)

if selected_year != TARGET_YEAR:
    st.warning(
        f"요청한 {TARGET_YEAR}년 데이터가 없어 "
        f"가장 최근 제공 연도인 {selected_year}년 데이터를 표시합니다."
    )
else:
    st.caption(f"분석 기준 연도: {selected_year}년")


# ==================================================
# 8. 시군구 고령화율 단계구분도
# ==================================================
st.subheader("📊 전국 시군구 고령화율 지도")

try:
    # 최신 Plotly 지도 API 사용
    fig = px.choropleth_map(
        map_df,
        geojson=geojson,
        locations="시군구코드",
        featureidkey="properties.코드",
        color="고령화율",
        color_continuous_scale="Reds",
        range_color=(5, 45),
        map_style="white-bg",
        center={"lat": 36.0, "lon": 127.8},
        zoom=5.5,
        opacity=0.78,
        hover_name="시군구",
        hover_data={
            "시도": True,
            "시군구코드": False,
            "고령화율": ":.1f",
            "총인구": ":,",
            "고령인구": ":,",
        },
        labels={
            "고령화율": "고령화율 (%)",
            "총인구": "총인구",
            "고령인구": "65세 이상 인구",
            "시도": "시·도",
        },
    )

    fig.update_traces(
        marker_line_width=0.5,
        marker_line_color="#777777",
        hovertemplate=(
            "<b>%{customdata[0]} %{hovertext}</b><br>"
            "고령화율: <b>%{z:.1f}%</b><br>"
            "총인구: %{customdata[1]:,.0f}명<br>"
            "65세 이상 인구: %{customdata[2]:,.0f}명"
            "<extra></extra>"
        ),
        customdata=map_df[
            ["시도", "총인구", "고령인구"]
        ].to_numpy(),
    )

    fig.update_layout(
        height=750,
        margin={"r": 0, "t": 10, "l": 0, "b": 0},
        coloraxis_colorbar={
            "title": {"text": "고령화율 (%)"},
            "ticksuffix": "%",
            "thickness": 18,
            "len": 0.7,
        },
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displayModeBar": True, "scrollZoom": True},
    )

except Exception as e:
    st.error("지도 생성 중 오류가 발생했습니다.")
    st.exception(e)


# ==================================================
# 9. 상위·하위 지역 및 상세 데이터
# ==================================================
st.subheader("🏆 고령화율 상위·하위 지역")

valid_df = sigungu_df.dropna(subset=["고령화율"]).copy()

tab1, tab2 = st.tabs(["고령화율 상위 10개", "고령화율 하위 10개"])

with tab1:
    top10 = valid_df.nlargest(10, "고령화율")[
        ["시도", "시군구", "총인구", "고령인구", "고령화율"]
    ].reset_index(drop=True)

    st.dataframe(
        top10.style.format({
            "총인구": "{:,.0f}",
            "고령인구": "{:,.0f}",
            "고령화율": "{:.1f}%",
        }),
        use_container_width=True,
        hide_index=True,
    )

with tab2:
    bottom10 = valid_df.nsmallest(10, "고령화율")[
        ["시도", "시군구", "총인구", "고령인구", "고령화율"]
    ].reset_index(drop=True)

    st.dataframe(
        bottom10.style.format({
            "총인구": "{:,.0f}",
            "고령인구": "{:,.0f}",
            "고령화율": "{:.1f}%",
        }),
        use_container_width=True,
        hide_index=True,
    )

with st.expander("📋 전국 시군구 상세 데이터 보기"):
    detail_df = valid_df[
        ["시도", "시군구", "시군구코드", "총인구", "고령인구", "고령화율"]
    ].sort_values(
        "고령화율",
        ascending=False,
    ).reset_index(drop=True)

    st.dataframe(
        detail_df.style.format({
            "총인구": "{:,.0f}",
            "고령인구": "{:,.0f}",
            "고령화율": "{:.1f}%",
        }),
        use_container_width=True,
        hide_index=True,
    )

    csv_data = detail_df.to_csv(
        index=False,
        encoding="utf-8-sig",
    )

    st.download_button(
        "📥 CSV 다운로드",
        data=csv_data,
        file_name=f"전국_시군구_고령화율_{selected_year}.csv",
        mime="text/csv",
    )

st.caption(
    "데이터 출처: yjgj0908/yg-population "
    "| 연령별 인구 및 시군구 GeoJSON"
)
