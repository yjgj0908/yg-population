import json
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
    layout="wide"
)

st.title("🗺️ 전국 시군구별 고령화 단계구분도 (2026년)")
st.write("2026년 기준 전국 시군구별 65세 이상 고령 인구 비율(%)을 확인하세요.")

# ==================================================
# 2. 데이터 URL 설정
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


# ==================================================
# 3. 데이터 로드 및 캐싱
# ==================================================
@st.cache_data(show_spinner="전국 인구 데이터를 불러오는 중...")
def load_population_data():
    df = pd.read_csv(POPULATION_DATA_URL, compression="zip")

    # 컬럼 이름 정형화 (공백 제거, BOM 제거)
    df.columns = [
        str(col).replace("\ufeff", "").strip() for col in df.columns
    ]

    # 2026년 데이터만 선택
    df["연도"] = pd.to_numeric(df["연도"], errors="coerce")
    df_2026 = df[df["연도"] == 2026].copy()

    if df_2026.empty:
        # 데이터에 2026년이 없을 경우 가장 최근 연도로 대치
        max_year = df["연도"].max()
        df_2026 = df[df["연도"] == max_year].copy()

    # 행정동 코드를 5자리 시군구 코드로 변환 (문자열 보장 및 0 채우기)
    df_2026["코드"] = df_2026["코드"].astype(str).str.split(".").str[0].str.zfill(8)
    df_2026["시군구코드"] = df_2026["코드"].str[:5]

    # 연령별 열 자동 판별 ('계_'로 시작하는 열 추출)
    total_age_cols = [
        col for col in df_2026.columns
        if col.startswith("계_")
    ]

    # 65세 이상 열 선별 ('계_65세' ~ '계_100세 이상' 등)
    elderly_cols = []
    for col in total_age_cols:
        # 숫자 부분 추출 (예: '계_65세' -> '65')
        age_str = col.replace("계_", "").replace("세", "").replace("이상", "").strip()
        if age_str.isdigit():
            age_num = int(age_str)
            if age_num >= 65:
                elderly_cols.append(col)

    # 인구 수 수치형 변환 (쉼표 제거)
    for col in total_age_cols:
        df_2026[col] = pd.to_numeric(
            df_2026[col].astype(str).str.replace(",", "", regex=False),
            errors="coerce"
        ).fillna(0)

    # 동별 총인구 및 65세 이상 인구 합산
    df_2026["총인구"] = df_2026[total_age_cols].sum(axis=1)
    df_2026["고령인구"] = df_2026[elderly_cols].sum(axis=1)

    # 시군구 코드(5자리) 기준으로 그룹화
    sigungu_grouped = df_2026.groupby("시군구코드").agg({
        "시도": "first",
        "시군구": "first",
        "총인구": "sum",
        "고령인구": "sum"
    }).reset_index()

    # 고령화율 (%) 계산
    sigungu_grouped["고령화율"] = np.where(
        sigungu_grouped["총인구"] > 0,
        (sigungu_grouped["고령인구"] / sigungu_grouped["총인구"]) * 100,
        0.0
    )

    return sigungu_grouped


@st.cache_data(show_spinner="시군구 경계 지도를 불러오는 중...")
def load_geojson():
    response = requests.get(GEOJSON_URL)
    geojson_data = response.json()
    return geojson_data


try:
    sigungu_df = load_population_data()
    geojson = load_geojson()
except Exception as e:
    st.error("데이터를 불러오는 중 오류가 발생했습니다.")
    st.code(str(e))
    st.stop()

# GeoJSON의 속성과 데이터프레임 시군구 이름 보완
geojson_map = {}
for feature in geojson["features"]:
    code = str(feature["properties"].get("코드", "")).zfill(5)
    feature["properties"]["코드"] = code
    sido = feature["properties"].get("시도", "")
    sigungu = feature["properties"].get("시군구", "")
    geojson_map[code] = {"시도": sido, "시군구": sigungu}

# 데이터프레임의 시군구 이름 및 시도 보정
sigungu_df["지역명"] = sigungu_df["시군구코드"].map(
    lambda c: geojson_map.get(c, {}).get("시군구", "")
)
sigungu_df["시도명"] = sigungu_df["시군구코드"].map(
    lambda c: geojson_map.get(c, {}).get("시도", "")
)

# 데이터프레임에 이름이 비어있으면 기존 값 유지
sigungu_df["시군구"] = np.where(
    sigungu_df["지역명"] != "", sigungu_df["지역명"], sigungu_df["시군구"]
)
sigungu_df["시도"] = np.where(
    sigungu_df["시도명"] != "", sigungu_df["시도명"], sigungu_df["시도"]
)

# ==================================================
# 4. 요약 지표 표시
# ==================================================
avg_aging_rate = (
    sigungu_df["고령인구"].sum() / sigungu_df["총인구"].sum() * 100
    if sigungu_df["총인구"].sum() > 0 else 0
)

col1, col2, col3 = st.columns(3)
col1.metric("총 분석 시군구", f"{len(sigungu_df)}개")
col2.metric("전국 평균 고령화율", f"{avg_aging_rate:.1f}%")
max_row = sigungu_df.loc[sigungu_df["고령화율"].idxmax()]
col3.metric(
    "최고 고령화 지역",
    f"{max_row['시도']} {max_row['시군구']}",
    f"{max_row['고령화율']:.1f}%"
)

# ==================================================
# 5. Plotly 단계구분도 (Choropleth)
# ==================================================
st.subheader("📊 전국 시군구 고령화율 지도")

fig = px.choropleth_mapbox(
    sigungu_df,
    geojson=geojson,
    locations="시군구코드",
    featureidkey="properties.코드",
    color="고령화율",
    color_continuous_scale="Reds",
    range_color=(5, 45),
    mapbox_style="white-bg",
    center={"lat": 35.9, "lon": 127.8},
    zoom=6.2,
    hover_name="시군구",
    hover_data={
        "시도": True,
        "시군구코드": False,
        "고령화율": ":.1f%",
        "총인구": ":,명",
        "고령인구": ":,명"
    },
    labels={
        "고령화율": "고령화율 (%)",
        "총인구": "총인구",
        "고령인구": "65세 이상 인구",
        "시도": "시·도"
    }
)

fig.update_traces(
    marker_line_width=0.6,
    marker_line_color="#777777",
    hovertemplate=(
        "<b>%{customdata[0]} %{hovertext}</b><br>"
        "고령화율: <b>%{z:.1f}%</b><br>"
        "총인구: %{customdata[1]:,명}<br>"
        "65세 이상 인구: %{customdata[2]:,명}"
        "<extra></extra>"
    ),
    customdata=sigungu_df[["시도", "총인구", "고령인구"]].values
)

fig.update_layout(
    height=750,
    margin={"r": 0, "t": 20, "l": 0, "b": 0},
    coloraxis_colorbar=dict(
        title="고령화율 (%)",
        ticksuffix="%",
        thickness=18,
        len=0.7
    )
)

st.plotly_chart(fig, use_container_width=True)

# ==================================================
# 6. 상위/하위 10개 지역 표
# ==================================================
with st.expander("📋 시군구별 고령화율 상세 데이터 보기"):
    st.dataframe(
        sigungu_df[["시도", "시군구", "시군구코드", "총인구", "고령인구", "고령화율"]]
        .sort_values(by="고령화율", ascending=False)
        .reset_index(drop=True),
        use_container_width=True,
        hide_index=True
    )

st.caption("데이터 출처: yjgj0908/yg-population (2026년 연령별 인구 및 GeoJSON)")
