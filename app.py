import streamlit as st
import pandas as pd
import altair as alt
import plotly.graph_objects as go
import numpy as np
from supabase import create_client

st.set_page_config(page_title="한국 주식 투자 지표", layout="wide", page_icon="📈")

# ── 데이터 로드 ──────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data():
    client = create_client(st.secrets["SUPABASE_URL"].rstrip("/"), st.secrets["SUPABASE_KEY"])
    response = client.table("investment_dashboard").select("*").execute()
    df = pd.DataFrame(response.data)
    df = df.rename(columns={"eps": "EPS", "추정per": "추정PER", "psr": "PSR", "eps수익률": "EPS수익률(%)"})
    df = df.dropna(subset=["회사명"])
    df["적자여부"] = df["EPS"] < 0
    df["PER유효"] = (df["추정PER"] > 0) & (df["추정PER"] < 150)
    return df

df = load_data()

# ── 헤더 ─────────────────────────────────────────────────────────
st.title("📈 한국 주식 투자 지표 대시보드")
st.caption("기준일: 2026년 6월 3일 종가 | 추정PER = 현재주가 ÷ 2026년 말 예상EPS (FnGuide 컨센서스)")

# ── 사이드바 ─────────────────────────────────────────────────────
with st.sidebar:
    st.header("필터")
    selected = st.multiselect(
        "종목 선택",
        options=df["회사명"].tolist(),
        default=df["회사명"].tolist(),
    )
    show_loss = st.checkbox("적자 종목 포함", value=True)
    per_limit = st.slider("추정PER 상한 (차트용)", 0, 150, 60)
    st.divider()
    st.caption("추정PER이 비정상적으로 높은 종목(적자 전환·일시적 이익 축소)은 차트에서 제외할 수 있습니다.")

filtered = df[df["회사명"].isin(selected)]
if not show_loss:
    filtered = filtered[~filtered["적자여부"]]

# ── 요약 KPI ─────────────────────────────────────────────────────
st.subheader("요약 지표")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("종목 수", f"{len(filtered)}개")
k2.metric("평균 주가", f"{filtered['주가'].mean():,.0f}원")
k3.metric("평균 EPS", f"{filtered['EPS'].mean():,.0f}원")
valid_per = filtered[filtered["PER유효"] & (filtered["추정PER"] <= per_limit)]
k4.metric("평균 추정PER", f"{valid_per['추정PER'].mean():.1f}배" if len(valid_per) else "N/A")
k5.metric("평균 매출액", f"{filtered['매출액'].mean():,.0f}억")

st.divider()

# ── 탭 레이아웃 ───────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["주가 & EPS", "추정PER", "PSR & 매출액", "전체 데이터"])

# ── 탭1: 주가 & EPS ───────────────────────────────────────────────
with tab1:
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**종목별 주가 (원)**")
        c = (
            alt.Chart(filtered)
            .mark_bar()
            .encode(
                x=alt.X("주가:Q", title="주가 (원)"),
                y=alt.Y("회사명:N", sort="-x", title=None),
                color=alt.condition(
                    alt.datum["적자여부"] == True,
                    alt.value("#e05252"),
                    alt.value("#4c8bf5"),
                ),
                tooltip=["회사명", alt.Tooltip("주가:Q", format=","), "추정PER"],
            )
            .properties(height=500)
        )
        st.altair_chart(c, use_container_width=True)

    with col_b:
        st.markdown("**종목별 EPS — 2026년 예상 (원)**")
        eps_df = filtered.copy()
        c2 = (
            alt.Chart(eps_df)
            .mark_bar()
            .encode(
                x=alt.X("EPS:Q", title="EPS (원)"),
                y=alt.Y("회사명:N", sort="-x", title=None),
                color=alt.condition(
                    alt.datum["EPS"] < 0,
                    alt.value("#e05252"),
                    alt.value("#34a853"),
                ),
                tooltip=["회사명", alt.Tooltip("EPS:Q", format=","), "추정PER"],
            )
            .properties(height=500)
        )
        st.altair_chart(c2, use_container_width=True)

# ── 탭2: 추정PER ──────────────────────────────────────────────────
with tab2:
    per_df = filtered[filtered["추정PER"] > 0].copy()
    per_chart_df = per_df[per_df["추정PER"] <= per_limit]

    if len(per_df) < len(filtered):
        excluded = filtered[~(filtered["추정PER"] > 0)]["회사명"].tolist()
        st.info(f"추정PER 미산출(적자) 종목 제외: {', '.join(excluded)}")

    over_limit = per_df[per_df["추정PER"] > per_limit]["회사명"].tolist()
    if over_limit:
        st.warning(f"PER 상한({per_limit}배) 초과로 차트 미표시: {', '.join(over_limit)}")

    st.markdown(f"**종목별 추정PER (≤ {per_limit}배)**")
    bar_per = (
        alt.Chart(per_chart_df)
        .mark_bar()
        .encode(
            x=alt.X("회사명:N", sort="-y", title=None),
            y=alt.Y("추정PER:Q", title="추정PER (배)"),
            color=alt.Color(
                "추정PER:Q",
                scale=alt.Scale(scheme="redyellowgreen", reverse=True),
                legend=alt.Legend(title="PER"),
            ),
            tooltip=["회사명", alt.Tooltip("추정PER:Q", format=".2f"), alt.Tooltip("주가:Q", format=",")],
        )
        .properties(height=420)
    )

    # PER=10 기준선
    rule = alt.Chart(pd.DataFrame({"y": [10]})).mark_rule(
        color="gray", strokeDash=[6, 3]
    ).encode(y="y:Q")

    st.altair_chart(bar_per + rule, use_container_width=True)
    st.caption("회색 점선 = PER 10배 기준선")

    # BCG 매트릭스: EPS수익률 vs 추정PER (Plotly)
    st.markdown("**BCG 매트릭스 (EPS수익률 vs 추정PER)**")
    scatter_df = per_chart_df[per_chart_df["EPS수익률(%)"] > 0].copy()

    YIELD_MID = 5.0   # EPS수익률 고정 기준선: 5%
    per_mid   = float(scatter_df["추정PER"].median())
    x_max_val = float(scatter_df["EPS수익률(%)"].max()) * 1.15
    y_max_val = float(scatter_df["추정PER"].max()) * 1.2

    # 버블 크기 정규화 (15~45px)
    rev_range = scatter_df["매출액"].max() - scatter_df["매출액"].min()
    scatter_df["msize"] = 15 + 30 * (scatter_df["매출액"] - scatter_df["매출액"].min()) / (rev_range if rev_range > 0 else 1)

    # 사분면별 버블 색상
    def quad_color(row):
        hi = row["EPS수익률(%)"] >= YIELD_MID
        lo = row["추정PER"] < per_mid
        if hi and lo:      return "#27ae60"  # 가치 우량주 - 초록
        if hi and not lo:  return "#2980b9"  # 우량 성장주 - 파랑
        if not hi and lo:  return "#e67e22"  # 물음표 - 주황
        return "#e74c3c"                     # 위험 - 빨강
    scatter_df["bcolor"] = scatter_df.apply(quad_color, axis=1)

    fig = go.Figure()

    # 4분면 배경 사각형
    for x0, x1, y0, y1, fill in [
        (0,         YIELD_MID, 0,       per_mid,   "rgba(255,243,180,0.45)"),  # 물음표 - 노랑
        (YIELD_MID, x_max_val, 0,       per_mid,   "rgba(180,235,180,0.45)"),  # 가치 우량주 - 초록
        (0,         YIELD_MID, per_mid, y_max_val, "rgba(255,180,180,0.45)"),  # 위험 - 빨강
        (YIELD_MID, x_max_val, per_mid, y_max_val, "rgba(180,210,255,0.45)"),  # 우량 성장주 - 파랑
    ]:
        fig.add_shape(type="rect", xref="x", yref="y",
                      x0=x0, x1=x1, y0=y0, y1=y1,
                      fillcolor=fill, line_width=0, layer="below")

    # 기준선
    fig.add_vline(x=YIELD_MID, line_dash="dash", line_color="#999", line_width=1.5)
    fig.add_hline(y=per_mid,   line_dash="dash", line_color="#999", line_width=1.5)

    # 버블 + 회사명
    fig.add_trace(go.Scatter(
        x=scatter_df["EPS수익률(%)"],
        y=scatter_df["추정PER"],
        mode="markers+text",
        text=scatter_df["회사명"],
        textposition="top center",
        textfont=dict(size=11, color="#1a1a1a", family="Arial"),
        marker=dict(
            size=scatter_df["msize"].tolist(),
            color=scatter_df["bcolor"].tolist(),
            opacity=0.88,
            line=dict(color="white", width=2),
        ),
        customdata=scatter_df[["주가", "EPS", "EPS수익률(%)", "추정PER", "매출액"]].values,
        hovertemplate=(
            "<b>%{text}</b><br>"
            "주가: %{customdata[0]:,.0f}원<br>"
            "EPS: %{customdata[1]:,.0f}원<br>"
            "EPS수익률: %{customdata[2]:.2f}%<br>"
            "추정PER: %{customdata[3]:.2f}배<br>"
            "매출액: %{customdata[4]:,.0f}억"
            "<extra></extra>"
        ),
    ))

    # 사분면 코너 라벨
    for x, y, xanchor, yanchor, color, label in [
        (0.02, 0.97, "left",  "top",    "#c0392b", "⚠ 위험<br><sup>저수익률 · 고PER</sup>"),
        (0.98, 0.97, "right", "top",    "#1a5276", "💎 우량 성장주<br><sup>고수익률 · 고PER</sup>"),
        (0.02, 0.03, "left",  "bottom", "#784212", "❓ 물음표<br><sup>저수익률 · 저PER</sup>"),
        (0.98, 0.03, "right", "bottom", "#1e8449", "🌟 가치 우량주<br><sup>고수익률 · 저PER</sup>"),
    ]:
        fig.add_annotation(
            x=x, y=y, xref="paper", yref="paper",
            text=label, showarrow=False,
            font=dict(size=13, color=color, family="Arial"),
            align="center", xanchor=xanchor, yanchor=yanchor,
            bgcolor="rgba(255,255,255,0.75)", borderpad=5,
        )

    fig.update_layout(
        xaxis=dict(
            title="EPS 수익률 (%) = EPS ÷ 현재주가 × 100  →  높을수록 저평가",
            range=[0, x_max_val],
            gridcolor="#eeeeee", showgrid=True,
        ),
        yaxis=dict(
            title="추정 PER (배)  →  낮을수록 저평가",
            range=[0, y_max_val],
            gridcolor="#eeeeee", showgrid=True,
        ),
        height=620,
        paper_bgcolor="white",
        plot_bgcolor="white",
        showlegend=False,
        margin=dict(l=60, r=40, t=50, b=60),
        title=dict(
            text=f"기준선: EPS수익률 {YIELD_MID}% (고정) / 추정PER 중앙값 {per_mid:.1f}배",
            font=dict(size=12, color="gray"), x=0.5,
        ),
    )

    st.plotly_chart(fig, use_container_width=True)
    st.caption("버블 크기 = 매출액 규모 | X축: EPS수익률(%) 높을수록 수익성 우수 | Y축: PER 낮을수록 저평가")

# ── 탭3: PSR & 매출액 ─────────────────────────────────────────────
with tab3:
    col_c, col_d = st.columns(2)

    with col_c:
        st.markdown("**종목별 PSR**")
        c3 = (
            alt.Chart(filtered)
            .mark_bar(color="#f4a261")
            .encode(
                x=alt.X("PSR:Q", title="PSR"),
                y=alt.Y("회사명:N", sort="-x", title=None),
                tooltip=["회사명", "PSR", alt.Tooltip("주가:Q", format=",")],
            )
            .properties(height=500)
        )
        st.altair_chart(c3, use_container_width=True)

    with col_d:
        st.markdown("**종목별 매출액 (억원)**")
        c4 = (
            alt.Chart(filtered)
            .mark_bar(color="#457b9d")
            .encode(
                x=alt.X("매출액:Q", title="매출액 (억원)"),
                y=alt.Y("회사명:N", sort="-x", title=None),
                tooltip=["회사명", alt.Tooltip("매출액:Q", format=",")],
            )
            .properties(height=500)
        )
        st.altair_chart(c4, use_container_width=True)

# ── 탭4: 전체 데이터 ─────────────────────────────────────────────
with tab4:
    sort_col = st.selectbox("정렬 기준", ["주가", "EPS", "추정PER", "PSR", "매출액"], index=0)
    asc = st.checkbox("오름차순", value=False)

    table_df = (
        filtered[["회사명", "주가", "EPS", "추정PER", "PSR", "매출액"]]
        .sort_values(sort_col, ascending=asc)
        .reset_index(drop=True)
    )

    def fmt_per(v):
        if v <= 0:
            return "N/A (적자)"
        if v >= 150:
            return f"{v:.1f}배 ⚠️"
        return f"{v:.1f}배"

    display = table_df.copy()
    display["주가"] = display["주가"].apply(lambda x: f"{x:,}원")
    display["EPS"] = display["EPS"].apply(lambda x: f"{x:,}원")
    display["추정PER"] = display["추정PER"].apply(fmt_per)
    display["PSR"] = display["PSR"].apply(lambda x: f"{x:.1f}배")
    display["매출액"] = display["매출액"].apply(lambda x: f"{x:,}억")

    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption("⚠️ 추정PER 150배 이상: 일시적 이익 축소 또는 적자 전환 종목")
