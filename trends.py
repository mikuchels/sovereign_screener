"""
Stage 5 — Trend Analysis & Flags

Computes year-on-year changes, rolling 3-year trends, and
assigns traffic-light flags to each country.

Flags:
    🟢 IMPROVING      3Y rolling trend > +0.20
    🟡 STABLE         between -0.20 and +0.20
    🔴 DETERIORATING  3Y rolling trend < -0.20

Updated for:
  - Step 1:  10 indicators (defensive column checks)
  - Step 2:  Extended date range (2005+) — more trend history
  - Step 9:  Trend coverage reporting

Usage:
    python trends.py
"""

import pandas as pd
from config import INDICATORS, COUNTRIES, SCORES_PATH, TRENDS_PATH


def compute_yoy_changes(df: pd.DataFrame) -> pd.DataFrame:
    """YoY change in composite score and each indicator score."""
    df = df.sort_values(["country_code", "year"])

    df["composite_yoy"] = (
        df.groupby("country_code")["composite_score"].diff().round(2)
    )

    for code in INDICATORS:
        score_col = f"score_{code}"
        if score_col not in df.columns:
            continue
        df[f"{code}_yoy"] = (
            df.groupby("country_code")[score_col].diff().round(2)
        )
    return df


def compute_rolling_trend(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    """
    Rolling 3-year average of YoY composite change.
    Smooths out one-off shocks (COVID 2020) and shows structural direction.
    """
    df = df.sort_values(["country_code", "year"])
    df["composite_trend_3y"] = (
        df.groupby("country_code")["composite_yoy"]
        .transform(lambda x: x.rolling(window, min_periods=2).mean())
        .round(2)
    )
    return df


def assign_trend_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Assign traffic-light flags based on 3Y rolling trend."""

    def _flag(val):
        if pd.isna(val):
            return "N/A"
        if val > 0.20:
            return "IMPROVING"
        if val < -0.20:
            return "DETERIORATING"
        return "STABLE"

    df["trend_flag"] = df["composite_trend_3y"].apply(_flag)
    return df


def identify_weakening_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each country-year, list individual indicators whose score
    dropped by more than 0.5 points YoY.
    """
    # Only include indicators that actually have YoY columns
    yoy_cols = {}
    for code, meta in INDICATORS.items():
        col = f"{code}_yoy"
        if col in df.columns:
            yoy_cols[col] = meta["name"]

    def _find_weak(row):
        weak = []
        for col, name in yoy_cols.items():
            if pd.notna(row.get(col)) and row[col] < -0.5:
                weak.append(f"{name} ({row[col]:+.1f})")
        return "; ".join(weak) if weak else "None"

    df["weakening_indicators"] = df.apply(_find_weak, axis=1)
    return df


def identify_strengthening_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each country-year, list individual indicators whose score
    improved by more than 0.5 points YoY.
    Mirror of weakening — useful for the dashboard.
    """
    yoy_cols = {}
    for code, meta in INDICATORS.items():
        col = f"{code}_yoy"
        if col in df.columns:
            yoy_cols[col] = meta["name"]

    def _find_strong(row):
        strong = []
        for col, name in yoy_cols.items():
            if pd.notna(row.get(col)) and row[col] > 0.5:
                strong.append(f"{name} ({row[col]:+.1f})")
        return "; ".join(strong) if strong else "None"

    df["strengthening_indicators"] = df.apply(_find_strong, axis=1)
    return df


def compute_indicator_trends(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    """
    Compute 3-year rolling trend for EACH indicator sub-score
    (not just the composite). Useful for radar chart trend overlays.
    """
    df = df.sort_values(["country_code", "year"])

    for code in INDICATORS:
        yoy_col = f"{code}_yoy"
        trend_col = f"{code}_trend_3y"
        if yoy_col not in df.columns:
            continue
        df[trend_col] = (
            df.groupby("country_code")[yoy_col]
            .transform(lambda x: x.rolling(window, min_periods=2).mean())
            .round(2)
        )

    return df


def get_trend_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a tidy summary table for the latest year.
    Used by the Streamlit dashboard.
    """
    latest_year = df["year"].max()
    latest = df[df["year"] == latest_year].copy()

    summary_rows = []
    for _, r in latest.iterrows():
        name = COUNTRIES.get(r["country_code"], r["country_code"])
        row = {
            "country_code":    r["country_code"],
            "country_name":    name,
            "composite_score": round(r["composite_score"], 2) if pd.notna(r.get("composite_score")) else None,
            "composite_yoy":   r.get("composite_yoy"),
            "trend_3y":        r.get("composite_trend_3y"),
            "trend_flag":      r.get("trend_flag", "N/A"),
            "weakening":       r.get("weakening_indicators", "None"),
            "strengthening":   r.get("strengthening_indicators", "None"),
        }

        # Credit band if available
        if "credit_band" in r.index:
            row["credit_band"] = r["credit_band"]

        summary_rows.append(row)

    return pd.DataFrame(summary_rows)


def print_trend_summary(df: pd.DataFrame):
    latest = df[df["year"] == df["year"].max()].sort_values("rank")
    icons = {"IMPROVING": "🟢", "STABLE": "🟡", "DETERIORATING": "🔴", "N/A": "⚪"}

    n_indicators = sum(1 for c in INDICATORS if f"score_{c}" in df.columns)

    print(f"\n  --- Trend Summary (Latest Year) ---")
    print(f"  Tracking {n_indicators} indicators across {len(COUNTRIES)} countries\n")

    for _, r in latest.iterrows():
        name = COUNTRIES.get(r["country_code"], r["country_code"])
        icon = icons.get(r["trend_flag"], "⚪")
        yoy = r["composite_yoy"]
        yoy_str = f"{yoy:+.2f}" if pd.notna(yoy) else "N/A"
        t3 = r["composite_trend_3y"]
        t3_str = f"{t3:+.2f}" if pd.notna(t3) else "N/A"

        print(f"    {icon}  {name}")
        print(f"       Score: {r['composite_score']:.2f}  |  "
              f"YoY: {yoy_str}  |  3Y Trend: {t3_str}")
        print(f"       Flag: {r['trend_flag']}")
        if r.get("weakening_indicators", "None") != "None":
            print(f"       ⚠ Weakening:      {r['weakening_indicators']}")
        if r.get("strengthening_indicators", "None") != "None":
            print(f"       ✦ Strengthening:  {r['strengthening_indicators']}")
        print()


def run_trend_analysis() -> pd.DataFrame:
    print("=" * 55)
    print("  ASEAN Sovereign Credit — Trend Analysis")
    print("=" * 55)

    df = pd.read_csv(SCORES_PATH)

    # Step 9: Report coverage
    n_indicators = sum(1 for c in INDICATORS if f"score_{c}" in df.columns)
    n_total = len(INDICATORS)
    year_range = f"{df['year'].min()}–{df['year'].max()}"
    print(f"\n  Data range: {year_range}")
    print(f"  Indicators scored: {n_indicators}/{n_total}")

    if n_indicators < n_total:
        missing = [
            INDICATORS[c]["name"]
            for c in INDICATORS
            if f"score_{c}" not in df.columns
        ]
        print(f"  ⚠  Missing: {', '.join(missing)}")

    print("\n[1/5] Computing YoY changes ...")
    df = compute_yoy_changes(df)

    print("[2/5] Computing 3-year rolling composite trend ...")
    df = compute_rolling_trend(df)

    print("[3/5] Assigning trend flags ...")
    df = assign_trend_flags(df)

    print("[4/5] Identifying weakening & strengthening indicators ...")
    df = identify_weakening_indicators(df)
    df = identify_strengthening_indicators(df)

    print("[5/5] Computing per-indicator rolling trends ...")
    df = compute_indicator_trends(df)

    print_trend_summary(df)

    df.to_csv(TRENDS_PATH, index=False)
    print(f"\n  ✓ Trends saved → {TRENDS_PATH}")
    return df


if __name__ == "__main__":
    run_trend_analysis()