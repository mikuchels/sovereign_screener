"""
Stage 6 — Streamlit Dashboard

Run with:
    streamlit run app.py

Pages:
    1. Overview        — ranked table, bar chart, score evolution
    2. Country Detail  — indicator breakdown, time series, score history
    3. Comparison      — overlay two countries, radar chart, side-by-side
    4. vs Agencies     — model scores vs S&P/Moody's/Fitch, scatter, divergences
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from config import COUNTRIES, INDICATORS, SOVEREIGN_RATINGS, RATING_TO_NUMERIC
from scoring import (
    compute_sub_scores,
    compute_composite_score,
    assign_credit_band,
)
from trends import (
    compute_yoy_changes,
    compute_rolling_trend,
    assign_trend_flags,
    identify_weakening_indicators,
)
from ratings import get_agency_scores, compare_ratings


# ── Page config ────────────────────────────────────────────────
st.set_page_config(
    page_title="ASEAN Sovereign Credit Scorecard",
    page_icon="🏦",
    layout="wide",
)


# ── Load & process data (cached) ──────────────────────────────
@st.cache_data
def load_data():
    df = pd.read_csv("data/clean_macro.csv")
    df = compute_sub_scores(df)
    df = compute_composite_score(df)
    df["credit_band"] = df["composite_score"].apply(assign_credit_band)
    df = compute_yoy_changes(df)
    df = compute_rolling_trend(df)
    df = assign_trend_flags(df)
    df = identify_weakening_indicators(df)
    df["country_name"] = df["country_code"].map(COUNTRIES)
    return df


df = load_data()
latest_year = int(df["year"].max())


# ── Sidebar navigation ────────────────────────────────────────
st.sidebar.title("🏦 ASEAN Sovereign Credit")
st.sidebar.caption(f"Data through {latest_year}")
st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Country Detail", "Comparison", "vs Agencies"],
)


# ================================================================
#  PAGE 1 — OVERVIEW
# ================================================================
if page == "Overview":
    st.title("ASEAN Sovereign Credit Risk Scorecard")

    latest = df[df["year"] == latest_year].sort_values("rank").copy()

    # ── Ranked table ──
    st.subheader("Current Rankings")

    def _flag_label(flag):
        icons = {"IMPROVING": "🟢", "STABLE": "🟡", "DETERIORATING": "🔴"}
        return f"{icons.get(flag, '⚪')} {flag}"

    latest["Trend"] = latest["trend_flag"].apply(_flag_label)

    st.dataframe(
        latest[["rank", "country_name", "composite_score", "credit_band", "Trend"]]
        .rename(
            columns={
                "rank": "Rank",
                "country_name": "Country",
                "composite_score": "Score (1-10)",
                "credit_band": "Implied Rating",
            }
        )
        .set_index("Rank"),
        use_container_width=True,
    )

    # ── Horizontal bar chart ──
    st.subheader("Composite Scores")
    fig = px.bar(
        latest.sort_values("composite_score", ascending=True),
        x="composite_score",
        y="country_name",
        orientation="h",
        color="composite_score",
        color_continuous_scale="RdYlGn",
        range_color=[3, 9],
        labels={"composite_score": "Score", "country_name": ""},
    )
    fig.update_layout(showlegend=False, height=350, coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    # ── Score evolution over time ──
    st.subheader("Score Evolution")
    fig2 = px.line(
        df, x="year", y="composite_score", color="country_name",
        markers=True,
        labels={"composite_score": "Composite Score", "year": "Year", "country_name": ""},
    )
    fig2.update_layout(height=420)
    st.plotly_chart(fig2, use_container_width=True)


# ================================================================
#  PAGE 2 — COUNTRY DETAIL
# ================================================================
elif page == "Country Detail":
    st.title("Country Drill-Down")

    code = st.selectbox(
        "Select country",
        list(COUNTRIES.keys()),
        format_func=lambda x: COUNTRIES[x],
    )
    cdf = df[df["country_code"] == code].sort_values("year")
    row = cdf[cdf["year"] == latest_year].iloc[0]

    # ── KPI cards ──
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Score", f"{row['composite_score']:.2f}")
    c2.metric("Rank", f"#{int(row['rank'])} / 5")
    c3.metric("Implied", row["credit_band"])
    c4.metric("Trend", row["trend_flag"])
    st.markdown("---")

    # ── Indicator scores (latest year) ──
    st.subheader(f"Indicator Scores — {COUNTRIES[code]} ({latest_year})")
    ind_data = pd.DataFrame(
        [
            {"Indicator": meta["name"], "Score": row[f"score_{c}"]}
            for c, meta in INDICATORS.items()
        ]
    )
    fig = px.bar(
        ind_data.sort_values("Score", ascending=True),
        x="Score", y="Indicator", orientation="h",
        color="Score", color_continuous_scale="RdYlGn",
        range_color=[1, 10], range_x=[0, 10],
    )
    fig.update_layout(height=350, showlegend=False, coloraxis_showscale=False, yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)

    # ── Raw indicator time series ──
    st.subheader("Indicator Time Series (Raw)")
    sel = st.selectbox(
        "Select indicator",
        list(INDICATORS.keys()),
        format_func=lambda x: INDICATORS[x]["name"],
    )
    meta = INDICATORS[sel]
    fig2 = px.line(
        cdf, x="year", y=sel, markers=True,
        title=f"{meta['name']} — {COUNTRIES[code]}",
        labels={sel: f"{meta['name']} ({meta['unit']})", "year": "Year"},
    )
    fig2.update_layout(height=350)
    st.plotly_chart(fig2, use_container_width=True)

    # ── Composite score history ──
    st.subheader("Composite Score History")
    fig3 = px.line(
        cdf, x="year", y="composite_score", markers=True,
        labels={"composite_score": "Score", "year": "Year"},
    )
    fig3.update_layout(height=300)
    st.plotly_chart(fig3, use_container_width=True)


# ================================================================
#  PAGE 3 — COUNTRY COMPARISON
# ================================================================
elif page == "Comparison":
    st.title("Country Comparison")

    c1, c2 = st.columns(2)
    with c1:
        ca = st.selectbox("Country A", list(COUNTRIES.keys()),
                          format_func=lambda x: COUNTRIES[x], index=0)
    with c2:
        cb = st.selectbox("Country B", list(COUNTRIES.keys()),
                          format_func=lambda x: COUNTRIES[x], index=3)

    da = df[df["country_code"] == ca].sort_values("year")
    db = df[df["country_code"] == cb].sort_values("year")
    ra = da[da["year"] == latest_year].iloc[0]
    rb = db[db["year"] == latest_year].iloc[0]

    # ── Composite overlay ──
    st.subheader("Composite Score Over Time")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=da["year"], y=da["composite_score"],
        mode="lines+markers", name=COUNTRIES[ca],
    ))
    fig.add_trace(go.Scatter(
        x=db["year"], y=db["composite_score"],
        mode="lines+markers", name=COUNTRIES[cb],
    ))
    fig.update_layout(height=400, yaxis_title="Score", xaxis_title="Year")
    st.plotly_chart(fig, use_container_width=True)

    # ── Radar chart ──
    st.subheader(f"Indicator Breakdown ({latest_year})")
    cats = [INDICATORS[c]["name"] for c in INDICATORS]
    va = [ra[f"score_{c}"] for c in INDICATORS]
    vb = [rb[f"score_{c}"] for c in INDICATORS]

    fig2 = go.Figure()
    fig2.add_trace(go.Scatterpolar(
        r=va + [va[0]], theta=cats + [cats[0]],
        fill="toself", name=COUNTRIES[ca], opacity=0.5,
    ))
    fig2.add_trace(go.Scatterpolar(
        r=vb + [vb[0]], theta=cats + [cats[0]],
        fill="toself", name=COUNTRIES[cb], opacity=0.5,
    ))
    fig2.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
        height=500,
    )
    st.plotly_chart(fig2, use_container_width=True)

    # ── Side-by-side table ──
    st.subheader("Side-by-Side (Raw + Scores)")
    rows = []
    for c, meta in INDICATORS.items():
        raw_a = f"{ra[c]:.2f}" if pd.notna(ra[c]) else "N/A"
        raw_b = f"{rb[c]:.2f}" if pd.notna(rb[c]) else "N/A"
        rows.append(
            {
                "Indicator": meta["name"],
                f"{COUNTRIES[ca]} Raw": f"{raw_a} {meta['unit']}",
                f"{COUNTRIES[ca]} Score": f"{ra[f'score_{c}']:.1f}",
                f"{COUNTRIES[cb]} Raw": f"{raw_b} {meta['unit']}",
                f"{COUNTRIES[cb]} Score": f"{rb[f'score_{c}']:.1f}",
            }
        )
    st.dataframe(pd.DataFrame(rows).set_index("Indicator"), use_container_width=True)


# ================================================================
#  PAGE 4 — MODEL vs AGENCIES
# ================================================================
elif page == "vs Agencies":
    st.title("Model vs Agency Ratings")
    st.markdown(
        "Compares the model's composite score (rescaled to the agency numeric "
        "scale 0–21) against the average of S&P, Moody's, and Fitch ratings."
    )

    # After — ensure credit_band exists
    if "credit_band" not in df.columns:
        df["credit_band"] = df["composite_score"].apply(assign_credit_band)
    comp = compare_ratings(df)
    comp = comp.sort_values("rank")

    # ── Table ──
    st.subheader("Comparison Table")
    st.dataframe(
        comp[
            [
                "country_name", "composite_score", "credit_band",
                "sp_rating", "moodys_rating", "fitch_rating",
                "model_numeric_rescaled", "agency_avg_numeric", "gap", "signal",
            ]
        ]
        .rename(
            columns={
                "country_name": "Country",
                "composite_score": "Model (1-10)",
                "credit_band": "Implied",
                "sp_rating": "S&P",
                "moodys_rating": "Moody's",
                "fitch_rating": "Fitch",
                "model_numeric_rescaled": "Model (rescaled)",
                "agency_avg_numeric": "Agency Avg",
                "gap": "Gap",
                "signal": "Signal",
            }
        )
        .set_index("Country"),
        use_container_width=True,
    )

    # ── Scatter plot ──
    st.subheader("Scatter: Model vs Agency")
    fig = px.scatter(
        comp, x="agency_avg_numeric", y="model_numeric_rescaled",
        text="country_name", size_max=15,
        labels={
            "agency_avg_numeric": "Agency Average (numeric)",
            "model_numeric_rescaled": "Model (rescaled)",
        },
    )
    # 45-degree reference line
    mx = max(comp["agency_avg_numeric"].max(), comp["model_numeric_rescaled"].max()) + 2
    fig.add_trace(go.Scatter(
        x=[0, mx], y=[0, mx],
        mode="lines", line=dict(dash="dash", color="grey"),
        showlegend=False,
    ))
    fig.update_traces(textposition="top center", selector=dict(mode="markers+text"))
    fig.update_layout(height=500)
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Above the line → model more optimistic than agencies. "
        "Below → model more bearish."
    )

    # ── Divergence commentary ──
    st.subheader("Divergence Notes")
    for _, r in comp.iterrows():
        if r["signal"] != "ALIGNED":
            direction = "more bullish" if r["gap"] > 0 else "more bearish"
            st.markdown(
                f"**{r['country_name']}** — Model is **{direction}** than agencies "
                f"(gap: {r['gap']:+.2f}). Potential drivers: differences in fiscal vs "
                f"external weighting, or qualitative factors (governance, institutional "
                f"quality, political stability) that agencies incorporate but this "
                f"model does not."
            )

    st.markdown("---")
    st.caption(
        "⚠ Singapore's central government debt includes CPF (mandatory pension) "
        "balances, inflating the Govt Debt / GDP metric. These are internal "
        "obligations backed by substantial reserves — not external market debt. "
        "This explains why the model may score Singapore lower than its AAA "
        "rating warrants."
    )