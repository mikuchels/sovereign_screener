"""
Stage 6 — Streamlit Dashboard

Run with:
    streamlit run app.py

Pages:
    1. Overview        — ranked table, bar chart, score evolution
    2. Country Detail  — indicator breakdown, time series, score history
    3. Comparison      — overlay two countries, radar chart, side-by-side
    4. vs Agencies     — model scores vs S&P/Moody's/Fitch, scatter, divergences
    5. Backtest        — (Step 2) model vs S&P year-by-year with divergence chart
    6. Radar Profiles  — (Step 5) multi-country radar with year slider
    7. Methodology     — (Step 3) full scoring documentation

Sidebar:
    - (Step 4) Adjustable weights with live re-scoring
    - (Step 9) Data freshness badge
    - (Step 10) Full dataset export (CSV / Excel)
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import io

from config import (
    COUNTRIES, INDICATORS, SOVEREIGN_RATINGS, RATING_TO_NUMERIC,
    RATING_HISTORY, CREDIT_SCALE,
)
from scoring import (
    compute_sub_scores,
    compute_composite_score,
    assign_credit_band,
    assign_credit_numeric,
)
from trends import (
    compute_yoy_changes,
    compute_rolling_trend,
    assign_trend_flags,
    identify_weakening_indicators,
    identify_strengthening_indicators,
    get_trend_summary,
)
from ratings import (
    get_agency_scores,
    compare_ratings,
    get_backtest_df,
    get_backtest_stats,
    detect_rating_actions,
)
from data_pipeline import get_freshness_summary, get_data_freshness


# ── Page config ────────────────────────────────────────────────
st.set_page_config(
    page_title="ASEAN Sovereign Credit Scorecard",
    page_icon="🏦",
    layout="wide",
)


# ══════════════════════════════════════════════════════════════
# SIDEBAR — Step 4: Adjustable Weights
# ══════════════════════════════════════════════════════════════
st.sidebar.title("🏦 ASEAN Sovereign Credit")

st.sidebar.markdown("---")
st.sidebar.header("⚖️ Model Weights")
st.sidebar.caption(
    "Drag sliders to adjust — weights are auto-normalised to 100%."
)

custom_weights = {}
for code, meta in INDICATORS.items():
    label = meta.get("short_name", meta["name"])
    default_w = meta["weight"]
    custom_weights[code] = st.sidebar.slider(
        label, 0.0, 1.0, default_w, 0.01, key=f"w_{code}"
    )

# Normalise
total_w = sum(custom_weights.values())
if total_w > 0:
    norm_weights = {k: v / total_w for k, v in custom_weights.items()}
else:
    norm_weights = {k: meta["weight"] for k, meta in INDICATORS.items()}

# Show effective weights
with st.sidebar.expander("Effective weights"):
    for code, w in norm_weights.items():
        name = INDICATORS[code].get("short_name", INDICATORS[code]["name"])
        st.caption(f"{name}: **{w:.0%}**")

# Check if weights differ from defaults
weights_changed = any(
    abs(custom_weights[c] - INDICATORS[c]["weight"]) > 0.005
    for c in INDICATORS
)


# ══════════════════════════════════════════════════════════════
# LOAD & PROCESS DATA (cached, weight-aware)
# ══════════════════════════════════════════════════════════════

@st.cache_data
def load_clean_data():
    """Load the clean CSV once (independent of weights)."""
    return pd.read_csv("data/clean_macro.csv")


def process_data(df_clean: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """
    Score, composite, band, trends — rerun when weights change.
    We separate this from load_clean_data so the API fetch isn't repeated.
    """
    df = df_clean.copy()
    df = compute_sub_scores(df)
    df = compute_composite_score(df, custom_weights=weights)
    df["credit_band"] = df["composite_score"].apply(assign_credit_band)
    df["credit_numeric"] = df["composite_score"].apply(assign_credit_numeric)
    df = compute_yoy_changes(df)
    df = compute_rolling_trend(df)
    df = assign_trend_flags(df)
    df = identify_weakening_indicators(df)
    df = identify_strengthening_indicators(df)
    df["country_name"] = df["country_code"].map(COUNTRIES)
    return df


# Create a hashable key from weights so Streamlit caches per weight config
weight_key = tuple(sorted(norm_weights.items()))


@st.cache_data
def get_processed_data(_clean_df, _weight_key):
    """Cached wrapper — re-scores only when weights change."""
    weights_dict = dict(_weight_key)
    return process_data(_clean_df, weights_dict)


df_clean = load_clean_data()
df = get_processed_data(df_clean, weight_key)
latest_year = int(df["year"].max())


# ══════════════════════════════════════════════════════════════
# SIDEBAR — Step 9: Data Freshness
# ══════════════════════════════════════════════════════════════
freshness = get_freshness_summary(df_clean)
freshness_latest = max(v for v in freshness.values() if v) if freshness else "N/A"

st.sidebar.markdown("---")
st.sidebar.caption(
    f"📅 **Data through {freshness_latest}** · World Bank API · "
    f"Refreshed {pd.Timestamp.now().strftime('%Y-%m-%d')}"
)

if weights_changed:
    st.sidebar.info("⚙️ Custom weights active — scores differ from defaults.")


# ══════════════════════════════════════════════════════════════
# SIDEBAR — Step 10: Full Dataset Export
# ══════════════════════════════════════════════════════════════
st.sidebar.markdown("---")
st.sidebar.subheader("📥 Export")

st.sidebar.download_button(
    "Download Full Dataset (CSV)",
    df.round(4).to_csv(index=False),
    "sovereign_screener_full.csv",
    "text/csv",
)

# Excel export (requires openpyxl)
try:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.round(4).to_excel(writer, sheet_name="Scored Data", index=False)
        # Add backtest sheet
        bt_df = get_backtest_df(df)
        if not bt_df.empty:
            bt_df.round(2).to_excel(writer, sheet_name="Backtest", index=False)
        # Add comparison sheet
        try:
            comp_df = compare_ratings(df)
            comp_df.round(2).to_excel(writer, sheet_name="Agency Comparison", index=False)
        except Exception:
            pass
    st.sidebar.download_button(
        "Download Full Dataset (Excel)",
        buf.getvalue(),
        "sovereign_screener.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
except ImportError:
    st.sidebar.caption("Install `openpyxl` for Excel export.")


# ══════════════════════════════════════════════════════════════
# NAVIGATION
# ══════════════════════════════════════════════════════════════
st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Navigate",
    [
        "Overview",
        "Country Detail",
        "Comparison",
        "vs Agencies",
        "🕐 Backtest",
        "🕸️ Radar Profiles",
        "📖 Methodology",
    ],
)


# ================================================================
#  PAGE 1 — OVERVIEW
# ================================================================
if page == "Overview":
    st.title("ASEAN Sovereign Credit Risk Scorecard")

    # Step 9: Freshness badge
    st.caption(
        f"📅 Data through **{freshness_latest}** · "
        f"{len(INDICATORS)} indicators · {len(COUNTRIES)} countries"
    )

    latest = df[df["year"] == latest_year].sort_values("rank").copy()

    # ── Ranked table ──
    st.subheader("Current Rankings")

    def _flag_label(flag):
        icons = {"IMPROVING": "🟢", "STABLE": "🟡", "DETERIORATING": "🔴"}
        return f"{icons.get(flag, '⚪')} {flag}"

    latest["Trend"] = latest["trend_flag"].apply(_flag_label)

    display_df = (
        latest[["rank", "country_name", "composite_score", "credit_band", "Trend"]]
        .rename(columns={
            "rank": "Rank",
            "country_name": "Country",
            "composite_score": "Score (1-10)",
            "credit_band": "Implied Rating",
        })
        .set_index("Rank")
    )
    st.dataframe(display_df, use_container_width=True)

    # Step 10: Export
    st.download_button(
        "📥 Download Rankings Table",
        display_df.reset_index().to_csv(index=False),
        "rankings.csv",
        "text/csv",
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
        labels={
            "composite_score": "Composite Score",
            "year": "Year",
            "country_name": "",
        },
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
    c2.metric("Rank", f"#{int(row['rank'])} / {len(COUNTRIES)}")
    c3.metric("Implied", row["credit_band"])
    c4.metric("Trend", row["trend_flag"])
    st.markdown("---")

    # ── Indicator scores (latest year) ──
    st.subheader(f"Indicator Scores — {COUNTRIES[code]} ({latest_year})")
    ind_data = []
    for c, meta in INDICATORS.items():
        score_col = f"score_{c}"
        if score_col in row.index and pd.notna(row[score_col]):
            ind_data.append({
                "Indicator": meta["name"],
                "Score": row[score_col],
            })
    ind_df = pd.DataFrame(ind_data)

    if not ind_df.empty:
        fig = px.bar(
            ind_df.sort_values("Score", ascending=True),
            x="Score", y="Indicator", orientation="h",
            color="Score", color_continuous_scale="RdYlGn",
            range_color=[1, 10], range_x=[0, 10],
        )
        fig.update_layout(
            height=max(300, len(ind_df) * 40),
            showlegend=False,
            coloraxis_showscale=False,
            yaxis_title="",
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Raw indicator time series ──
    st.subheader("Indicator Time Series (Raw)")
    available = [c for c in INDICATORS if c in cdf.columns]
    sel = st.selectbox(
        "Select indicator",
        available,
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

    # ── Weakening / Strengthening (latest year) ──
    if row.get("weakening_indicators", "None") != "None":
        st.warning(f"⚠️ **Weakening:** {row['weakening_indicators']}")
    if row.get("strengthening_indicators", "None") != "None":
        st.success(f"✦ **Strengthening:** {row['strengthening_indicators']}")

    # Step 10: Export
    st.download_button(
        f"📥 Download {COUNTRIES[code]} Data",
        cdf.round(4).to_csv(index=False),
        f"sovereign_{code}.csv",
        "text/csv",
    )


# ================================================================
#  PAGE 3 — COUNTRY COMPARISON
# ================================================================
elif page == "Comparison":
    st.title("Country Comparison")

    c1, c2 = st.columns(2)
    with c1:
        ca = st.selectbox(
            "Country A", list(COUNTRIES.keys()),
            format_func=lambda x: COUNTRIES[x], index=0,
        )
    with c2:
        cb = st.selectbox(
            "Country B", list(COUNTRIES.keys()),
            format_func=lambda x: COUNTRIES[x], index=3,
        )

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
    available_ind = [c for c in INDICATORS if f"score_{c}" in ra.index]
    cats = [INDICATORS[c].get("short_name", INDICATORS[c]["name"])
            for c in available_ind]
    va = [ra[f"score_{c}"] if pd.notna(ra.get(f"score_{c}")) else 0
          for c in available_ind]
    vb = [rb[f"score_{c}"] if pd.notna(rb.get(f"score_{c}")) else 0
          for c in available_ind]

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
        raw_a = f"{ra[c]:.2f}" if c in ra.index and pd.notna(ra[c]) else "N/A"
        raw_b = f"{rb[c]:.2f}" if c in rb.index and pd.notna(rb[c]) else "N/A"
        sc_a = f"{ra[f'score_{c}']:.1f}" if f"score_{c}" in ra.index and pd.notna(ra.get(f"score_{c}")) else "N/A"
        sc_b = f"{rb[f'score_{c}']:.1f}" if f"score_{c}" in rb.index and pd.notna(rb.get(f"score_{c}")) else "N/A"
        rows.append({
            "Indicator": meta["name"],
            f"{COUNTRIES[ca]} Raw": f"{raw_a} {meta['unit']}",
            f"{COUNTRIES[ca]} Score": sc_a,
            f"{COUNTRIES[cb]} Raw": f"{raw_b} {meta['unit']}",
            f"{COUNTRIES[cb]} Score": sc_b,
        })
    sbs_df = pd.DataFrame(rows).set_index("Indicator")
    st.dataframe(sbs_df, use_container_width=True)

    # Step 10: Export
    st.download_button(
        "📥 Download Comparison Table",
        sbs_df.reset_index().to_csv(index=False),
        f"comparison_{ca}_vs_{cb}.csv",
        "text/csv",
    )


# ================================================================
#  PAGE 4 — MODEL vs AGENCIES
# ================================================================
elif page == "vs Agencies":
    st.title("Model vs Agency Ratings")
    st.markdown(
        "Compares the model's composite score (rescaled to the agency numeric "
        "scale 0–21) against the average of S&P, Moody's, and Fitch ratings."
    )

    # Ensure credit_band exists
    if "credit_band" not in df.columns:
        df["credit_band"] = df["composite_score"].apply(assign_credit_band)
    comp = compare_ratings(df)
    comp = comp.sort_values("rank")

    # ── Table ──
    st.subheader("Comparison Table")
    display_cols = [
        "country_name", "composite_score", "credit_band",
        "sp_rating", "moodys_rating", "fitch_rating",
        "model_numeric_rescaled", "agency_avg_numeric", "gap", "signal",
    ]
    display_cols = [c for c in display_cols if c in comp.columns]

    comp_display = (
        comp[display_cols]
        .rename(columns={
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
        })
        .set_index("Country")
    )
    st.dataframe(comp_display, use_container_width=True)

    # Step 10: Export
    st.download_button(
        "📥 Download Agency Comparison",
        comp_display.reset_index().to_csv(index=False),
        "agency_comparison.csv",
        "text/csv",
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
    mx = max(
        comp["agency_avg_numeric"].max(),
        comp["model_numeric_rescaled"].max(),
    ) + 2
    fig.add_trace(go.Scatter(
        x=[0, mx], y=[0, mx],
        mode="lines", line=dict(dash="dash", color="grey"),
        showlegend=False,
    ))
    fig.update_traces(
        textposition="top center",
        selector=dict(mode="markers+text"),
    )
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


# ================================================================
#  PAGE 5 — BACKTEST  (Step 2)
# ================================================================
elif page == "🕐 Backtest":
    st.title("🕐 Backtest: Model vs S&P Over Time")
    st.markdown(
        "Did the model's implied rating lead or lag actual S&P actions?  "
        "Divergences suggest the model detected shifts before (or after) "
        "the agency moved."
    )

    backtest_df = get_backtest_df(df)

    if backtest_df.empty:
        st.warning(
            "No overlapping years between model data and RATING_HISTORY.  \n"
            f"Model data range: {df['year'].min()}–{df['year'].max()}.  \n"
            "Ensure `START_YEAR` in config.py is ≤ 2005."
        )
    else:
        # Country selector
        bt_country = st.selectbox(
            "Country",
            list(RATING_HISTORY.keys()),
            format_func=lambda x: COUNTRIES.get(x, x),
            key="bt_country",
        )
        bt = backtest_df[
            backtest_df["country_code"] == bt_country
        ].sort_values("year")

        if bt.empty:
            st.info("No backtest data for this country.")
        else:
            # ── Dual-line chart ──
            fig = go.Figure()

            fig.add_trace(go.Scatter(
                x=bt["year"], y=bt["model_numeric"],
                mode="lines+markers",
                name="Model Implied",
                line=dict(color="#636EFA", width=3),
                marker=dict(size=8),
            ))
            fig.add_trace(go.Scatter(
                x=bt["year"], y=bt["actual_numeric"],
                mode="lines+markers",
                name="S&P Actual",
                line=dict(color="#EF553B", width=3, dash="dash"),
                marker=dict(size=8, symbol="diamond"),
            ))

            # Y-axis → rating labels
            num_to_rating = {v: k for k, v in RATING_TO_NUMERIC.items()
                            if not k[0].isupper() or k == k.upper()
                            or "a" not in k.lower()
                            or k in ["AAA","AA+","AA","AA-","A+","A","A-",
                                     "BBB+","BBB","BBB-","BB+","BB","BB-",
                                     "B+","B","B-","CCC+","CCC","CCC-","CC","C","D"]}
            # Simpler: use S&P scale only
            sp_map = {}
            for k, v in RATING_TO_NUMERIC.items():
                # Skip Moody's names (contain lowercase)
                if k == k.upper() or k in ["D", "C"]:
                    sp_map[v] = k

            all_nums = sorted(set(
                bt["model_numeric"].dropna().tolist()
                + bt["actual_numeric"].dropna().tolist()
            ))
            lo = max(int(min(all_nums)) - 2, 0)
            hi = int(max(all_nums)) + 2
            tvals = list(range(lo, hi + 1))
            ttext = [sp_map.get(v, "") for v in tvals]

            fig.update_layout(
                title=f"Backtest — {COUNTRIES.get(bt_country, bt_country)}",
                xaxis_title="Year",
                yaxis_title="Rating (S&P scale)",
                yaxis=dict(tickvals=tvals, ticktext=ttext),
                height=500,
                hovermode="x unified",
                legend=dict(yanchor="bottom", y=0.01, xanchor="right", x=0.99),
            )
            st.plotly_chart(fig, use_container_width=True)

            # ── Metrics row ──
            clean_bt = bt.dropna(subset=["difference"])
            if not clean_bt.empty:
                worst = clean_bt.loc[clean_bt["difference"].abs().idxmax()]
                m1, m2, m3 = st.columns(3)
                m1.metric("Avg Δ (notches)", f"{clean_bt['difference'].mean():+.1f}")
                m2.metric(
                    "Max divergence",
                    f"{worst['difference']:+.0f}  ({int(worst['year'])})",
                )
                m3.metric("Latest model band", clean_bt.iloc[-1]["model_band"])

            # ── Rating actions table ──
            events_df = detect_rating_actions(backtest_df)
            country_events = events_df[
                events_df["country_code"] == bt_country
            ] if not events_df.empty else pd.DataFrame()

            if not country_events.empty:
                st.subheader("Rating Actions & Model Signal")
                st.dataframe(
                    country_events[[
                        "year", "action", "from_rating", "to_rating",
                        "model_band", "model_led",
                    ]].rename(columns={
                        "year": "Year",
                        "action": "Action",
                        "from_rating": "From",
                        "to_rating": "To",
                        "model_band": "Model at Time",
                        "model_led": "Model Led?",
                    }),
                    hide_index=True,
                    use_container_width=True,
                )

            # ── Full table (expandable) ──
            with st.expander("📋 Full Backtest Table"):
                st.dataframe(
                    bt[["year", "actual_rating", "actual_numeric",
                        "model_band", "model_numeric", "composite_score",
                        "difference"]].round(2),
                    hide_index=True,
                    use_container_width=True,
                )

        # ── Cross-country accuracy stats ──
        st.markdown("---")
        st.subheader("Cross-Country Accuracy Summary")
        stats_df = get_backtest_stats(backtest_df)
        if not stats_df.empty:
            st.dataframe(
                stats_df.rename(columns={
                    "country_name": "Country",
                    "n_years": "Years",
                    "mean_diff": "Mean Δ",
                    "abs_mean_diff": "Avg |Δ|",
                    "max_abs_diff": "Max |Δ|",
                    "exact_match_pct": "Exact %",
                    "within_1_notch_pct": "Within 1 %",
                    "within_2_notch_pct": "Within 2 %",
                }).drop(columns=["country_code"], errors="ignore"),
                hide_index=True,
                use_container_width=True,
            )

        # Step 10: Export
        st.download_button(
            "📥 Download Backtest Data",
            backtest_df.round(2).to_csv(index=False),
            "backtest_results.csv",
            "text/csv",
        )


# ================================================================
#  PAGE 6 — RADAR PROFILES  (Step 5)
# ================================================================
elif page == "🕸️ Radar Profiles":
    st.title("🕸️ Country Risk Profiles")
    st.markdown(
        "Radar charts show each country's score across all indicators.  \n"
        "**Larger area = stronger credit profile.**"
    )

    # ── Controls ──
    radar_countries = st.multiselect(
        "Countries",
        list(COUNTRIES.keys()),
        default=list(COUNTRIES.keys()),
        format_func=lambda x: COUNTRIES[x],
    )

    avail_years = sorted(df["year"].dropna().unique())
    radar_year = st.select_slider(
        "Year",
        options=[int(y) for y in avail_years],
        value=int(avail_years[-1]),
    )

    # ── Build radar ──
    available_ind = [c for c in INDICATORS if f"score_{c}" in df.columns]
    theta = [INDICATORS[c].get("short_name", INDICATORS[c]["name"])
             for c in available_ind]

    colors = px.colors.qualitative.Set2
    fig = go.Figure()

    for i, country in enumerate(radar_countries):
        row_data = df[
            (df["country_code"] == country) & (df["year"] == radar_year)
        ]
        if row_data.empty:
            continue

        row = row_data.iloc[0]
        vals = [
            row[f"score_{c}"] if pd.notna(row.get(f"score_{c}")) else 0
            for c in available_ind
        ]
        vals_closed = vals + [vals[0]]
        theta_closed = theta + [theta[0]]

        fig.add_trace(go.Scatterpolar(
            r=vals_closed,
            theta=theta_closed,
            fill="toself",
            name=COUNTRIES[country],
            line=dict(color=colors[i % len(colors)]),
            opacity=0.65,
        ))

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
        showlegend=True,
        height=600,
        title=f"Risk Profile Comparison — {int(radar_year)}",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Score breakdown table ──
    with st.expander("📋 Score Breakdown"):
        bd = []
        for country in radar_countries:
            row_data = df[
                (df["country_code"] == country) & (df["year"] == radar_year)
            ]
            if row_data.empty:
                continue
            row = row_data.iloc[0]
            d = {"Country": COUNTRIES[country]}
            for c in available_ind:
                label = INDICATORS[c].get("short_name", INDICATORS[c]["name"])
                d[label] = round(row[f"score_{c}"], 2) if pd.notna(row.get(f"score_{c}")) else None
            d["Composite"] = round(row["composite_score"], 2) if pd.notna(row.get("composite_score")) else None
            d["Band"] = row.get("credit_band", "NR")
            bd.append(d)
        if bd:
            st.dataframe(pd.DataFrame(bd), hide_index=True, use_container_width=True)

    # ── Year-over-year radar animation ──
    st.subheader("Year-over-Year Shift")
    st.caption("Compare the same country across two years to see what moved.")

    yr1, yr2 = st.columns(2)
    with yr1:
        yoy_y1 = st.selectbox("Year 1", avail_years, index=max(0, len(avail_years)-2))
    with yr2:
        yoy_y2 = st.selectbox("Year 2", avail_years, index=len(avail_years)-1)
    yoy_country = st.selectbox(
        "Country",
        list(COUNTRIES.keys()),
        format_func=lambda x: COUNTRIES[x],
        key="radar_yoy_country",
    )

    r1 = df[(df["country_code"] == yoy_country) & (df["year"] == yoy_y1)]
    r2 = df[(df["country_code"] == yoy_country) & (df["year"] == yoy_y2)]

    if not r1.empty and not r2.empty:
        r1, r2 = r1.iloc[0], r2.iloc[0]
        v1 = [r1[f"score_{c}"] if pd.notna(r1.get(f"score_{c}")) else 0
              for c in available_ind]
        v2 = [r2[f"score_{c}"] if pd.notna(r2.get(f"score_{c}")) else 0
              for c in available_ind]

        fig2 = go.Figure()
        fig2.add_trace(go.Scatterpolar(
            r=v1 + [v1[0]], theta=theta + [theta[0]],
            fill="toself", name=f"{int(yoy_y1)}",
            line=dict(dash="dash"), opacity=0.5,
        ))
        fig2.add_trace(go.Scatterpolar(
            r=v2 + [v2[0]], theta=theta + [theta[0]],
            fill="toself", name=f"{int(yoy_y2)}",
            opacity=0.7,
        ))
        fig2.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
            height=500,
            title=f"{COUNTRIES[yoy_country]}: {int(yoy_y1)} vs {int(yoy_y2)}",
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Insufficient data for the selected years.")


# ================================================================
#  PAGE 7 — METHODOLOGY  (Step 3)
# ================================================================
elif page == "📖 Methodology":
    st.title("📖 Methodology")

    st.markdown("""
    ## Overview

    This screener uses a **quantitative scoring model** to assess sovereign
    creditworthiness for ASEAN-5 economies. Each macroeconomic indicator is
    converted to a **1–10 score** using absolute benchmarks, combined via
    user-adjustable weights, and mapped to an implied credit rating on the
    **S&P 21-notch scale**.

    The approach draws on the framework used by major rating agencies
    (S&P, Moody's, Fitch), which assess sovereigns across five pillars:

    | Pillar | Our Indicators |
    |--------|----------------|
    | **Economic strength** | GDP Growth, GDP per Capita |
    | **Institutional quality** | GDP per Capita (proxy) |
    | **Fiscal position** | Govt Debt / GDP, Fiscal Balance / GDP |
    | **External position** | Current Account, FX Reserves, External Debt |
    | **Monetary credibility** | Inflation, Real Interest Rate, Gross Savings |
    """)

    st.markdown("---")
    st.markdown("## Indicator Details")

    # Auto-generate table from config
    ind_rows = []
    for code, meta in INDICATORS.items():
        direction_map = {
            "higher_better": "↑ Higher is better",
            "lower_better": "↓ Lower is better",
            "moderate_better": f"≈ Optimal near {meta.get('bench_target', 'mid')}",
        }
        ind_rows.append({
            "Indicator": meta["name"],
            "WB Code": f"`{code}`",
            "Unit": meta["unit"],
            "Direction": direction_map.get(meta["direction"], meta["direction"]),
            "Bench Min": meta["bench_min"],
            "Bench Max": meta["bench_max"],
            "Default Weight": f"{meta['weight']:.0%}",
        })
    st.dataframe(pd.DataFrame(ind_rows), hide_index=True, use_container_width=True)

    st.markdown("""
    ---

    ## Scoring Logic

    **`higher_better`** (e.g. GDP Growth):
    ```
    score = 1 + 9 × (value − bench_min) / (bench_max − bench_min)
    ```

    **`lower_better`** (e.g. Inflation, Debt):
    ```
    score = 1 + 9 × (bench_max − value) / (bench_max − bench_min)
    ```

    **`moderate_better`** (e.g. Real Interest Rate):
    ```
    score = 10 − 9 × |value − target| / max_distance
    ```
    Peaks at `bench_target` and penalises both too-high and too-low values.

    All scores are **clipped to [1, 10]**.

    ---

    ## Composite Score & Credit Band

    The **composite score** is a weighted average of individual indicator scores.
    Weights can be adjusted via the sidebar — they are auto-normalised to sum
    to 100%.

    If an indicator has missing data, its weight is redistributed proportionally
    across the remaining indicators (NaN-safe re-normalisation).

    The composite (1–10) maps to the S&P 21-notch scale:
    """)

    # Credit scale table
    band_df = pd.DataFrame(
        [(band, f"{lo:.1f} – {hi:.1f}", num)
         for lo, hi, band, num in CREDIT_SCALE],
        columns=["Rating", "Score Range", "Numeric"],
    )
    st.dataframe(band_df, hide_index=True, use_container_width=False)

    st.markdown("""
    ---

    ## Backtest Methodology

    The backtest compares model-implied ratings against actual **S&P sovereign
    ratings** from 2005 to 2023 (where data is available).

    Key metrics:
    - **Mean Δ**: Average notch difference (positive = model more bullish)
    - **Within 1/2 notches**: Percentage of years where the model was close
    - **Model Led?**: For each actual S&P upgrade/downgrade, did the model
      already reflect the direction beforehand?

    ⚠️ Historical S&P ratings are approximate annual snapshots. Verify against
    [S&P press releases](https://disclosure.spglobal.com) for precision.

    ---

    ## Known Limitations & Extensions

    | Limitation | Possible Extension |
    |------------|--------------------|
    | Backward-looking only | Add nowcasting with PMI / high-frequency data |
    | No governance data | Integrate World Governance Indicators (WGI) |
    | No market data | Overlay CDS spreads / EMBI+ spreads |
    | No default probability | Build a structural (Merton) or logistic model |
    | Data publication lag (1–2 yrs) | Use IMF WEO forecasts for current year |
    | Only 5 countries | Expand to full ASEAN-10 + frontier markets |
    | Singapore debt anomaly | CPF-inclusive debt inflates Govt Debt / GDP |
    | Relative vs absolute scoring | ✅ Resolved — now uses absolute benchmarks |

    ---

    ## Data Sources

    - **World Bank Open Data API** — All macroeconomic indicators
    - **S&P Global** — Sovereign Rating Methodology (Dec 2017)
    - **Moody's** — Rating Methodology: Sovereign Bond Ratings (Nov 2018)
    - **Fitch Ratings** — Sovereign Rating Criteria (Mar 2023)
    - Cantor & Packer (1996), *"Determinants and Impact of Sovereign
      Credit Ratings"*, FRBNY Economic Policy Review
    """)

    # Step 9: Data freshness detail
    st.markdown("---")
    st.subheader("📅 Data Freshness Detail")
    st.caption("Most recent non-null year per country × indicator.")
    freshness_detail = get_data_freshness(df_clean)
    # Pivot for readability
    pivot = freshness_detail.pivot(
        index="indicator_name", columns="country_name", values="latest_year"
    )
    st.dataframe(pivot, use_container_width=True)

    stale = freshness_detail[freshness_detail["is_stale"]]
    if not stale.empty:
        st.warning(
            f"⚠️ {len(stale)} indicator-country pairs have data older than "
            f"2 years. These may affect scoring accuracy."
        )