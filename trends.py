"""
Stage 5 — Trend Analysis & Flags

Computes year-on-year changes, rolling 3-year trends, and
assigns traffic-light flags to each country.

Flags:
    🟢 IMPROVING      3Y rolling trend > +0.20
    🟡 STABLE         between -0.20 and +0.20
    🔴 DETERIORATING  3Y rolling trend < -0.20

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
    yoy_cols = {f"{code}_yoy": meta["name"] for code, meta in INDICATORS.items()}

    def _find(row):
        weak = []
        for col, name in yoy_cols.items():
            if pd.notna(row.get(col)) and row[col] < -0.5:
                weak.append(f"{name} ({row[col]:+.1f})")
        return "; ".join(weak) if weak else "None"

    df["weakening_indicators"] = df.apply(_find, axis=1)
    return df


def print_trend_summary(df: pd.DataFrame):
    latest = df[df["year"] == df["year"].max()].sort_values("rank")
    icons = {"IMPROVING": "🟢", "STABLE": "🟡", "DETERIORATING": "🔴", "N/A": "⚪"}

    print("\n  --- Trend Summary (Latest Year) ---")
    for _, r in latest.iterrows():
        name = COUNTRIES.get(r["country_code"], r["country_code"])
        icon = icons.get(r["trend_flag"], "⚪")
        yoy = r["composite_yoy"]
        yoy_str = f"{yoy:+.2f}" if pd.notna(yoy) else "N/A"
        t3 = r["composite_trend_3y"]
        t3_str = f"{t3:+.2f}" if pd.notna(t3) else "N/A"

        print(f"\n    {icon}  {name}")
        print(f"       Score: {r['composite_score']:.2f}  |  "
              f"YoY: {yoy_str}  |  3Y Trend: {t3_str}")
        print(f"       Flag: {r['trend_flag']}")
        if r["weakening_indicators"] != "None":
            print(f"       ⚠ Weakening: {r['weakening_indicators']}")


def run_trend_analysis() -> pd.DataFrame:
    print("=" * 55)
    print("  ASEAN Sovereign Credit — Trend Analysis")
    print("=" * 55)

    df = pd.read_csv(SCORES_PATH)
    df = compute_yoy_changes(df)
    df = compute_rolling_trend(df)
    df = assign_trend_flags(df)
    df = identify_weakening_indicators(df)

    print_trend_summary(df)

    df.to_csv(TRENDS_PATH, index=False)
    print(f"\n  ✓ Trends saved → {TRENDS_PATH}")
    return df


if __name__ == "__main__":
    run_trend_analysis()