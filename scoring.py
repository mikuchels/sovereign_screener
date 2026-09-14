"""
Stage 3 — Scoring Engine

Reads clean macro data, normalises each indicator to a 0-10 sub-score,
computes a weighted composite, ranks countries per year, and assigns
a letter-grade credit band.

Usage:
    python scoring.py
"""

import pandas as pd
import numpy as np
import os
from config import (
    INDICATORS, CLEAN_DATA_PATH, SCORED_DATA_PATH,
)

# ── Scoring direction ──────────────────────────────────────────────
# "higher_better"  → higher raw value = higher score  (e.g. GDP growth)
# "lower_better"   → lower raw value  = higher score  (e.g. inflation, debt)
SCORE_DIRECTION = {
    "NY.GDP.MKTP.KD.ZG": "higher_better",   # GDP Growth
    "FP.CPI.TOTL.ZG":    "lower_better",    # Inflation
    "BN.CAB.XOKA.GD.ZS": "higher_better",   # Current Account / GDP
    "FI.RES.TOTL.MO":    "higher_better",    # FX Reserves Cover (months)
    "GC.DOD.TOTL.GD.ZS": "lower_better",    # Govt Debt / GDP
    "NY.GNS.ICTR.ZS":    "higher_better",   # Gross Savings / GDP
}

# ── Weights (must sum to 1.0) ─────────────────────────────────────
WEIGHTS = {
    "NY.GDP.MKTP.KD.ZG": 0.20,
    "FP.CPI.TOTL.ZG":    0.15,
    "BN.CAB.XOKA.GD.ZS": 0.15,
    "FI.RES.TOTL.MO":    0.15,
    "GC.DOD.TOTL.GD.ZS": 0.20,
    "NY.GNS.ICTR.ZS":    0.15,
}

# ── Credit bands ──────────────────────────────────────────────────
CREDIT_BANDS = [
    (8.0, "AAA"),
    (7.0, "AA"),
    (6.0, "A"),
    (5.0, "BBB"),
    (4.0, "BB"),
    (3.0, "B"),
    (0.0, "CCC"),
]


def _normalise_column(series: pd.Series, direction: str) -> pd.Series:
    """
    Min-max normalise a series to the 0–10 range.
    Handles the case where min == max (returns 5.0 for all).
    NaN values are preserved (not filled).
    """
    s_min = series.min()
    s_max = series.max()

    if s_max == s_min:
        return pd.Series(5.0, index=series.index)

    if direction == "higher_better":
        return 10 * (series - s_min) / (s_max - s_min)
    else:  # lower_better
        return 10 * (s_max - series) / (s_max - s_min)


def compute_sub_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each indicator, normalise within each year to a 0-10 sub-score.
    Adds columns like  score_NY.GDP.MKTP.KD.ZG  etc.
    """
    indicator_cols = list(INDICATORS.keys())

    for col in indicator_cols:
        score_col = f"score_{col}"
        direction = SCORE_DIRECTION[col]
        df[score_col] = df.groupby("year")[col].transform(
            _normalise_column, direction=direction
        )

    return df


def compute_composite_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Weighted average of sub-scores → composite_score (0–10).

    Key fix: if some sub-scores are NaN (e.g. missing Govt Debt data),
    we compute the weighted average over the *available* sub-scores only,
    re-normalising the weights so they still sum to 1.
    """
    score_cols = [f"score_{col}" for col in INDICATORS.keys()]
    weight_vals = [WEIGHTS[col] for col in INDICATORS.keys()]

    weights_arr = np.array(weight_vals)  # shape (n_indicators,)

    def _weighted_mean_row(row):
        """Compute weighted mean for a single row, skipping NaN sub-scores."""
        values = row.values.astype(float)
        mask = ~np.isnan(values)
        if mask.sum() == 0:
            return np.nan
        w = weights_arr[mask]
        v = values[mask]
        return np.average(v, weights=w)

    df["composite_score"] = df[score_cols].apply(_weighted_mean_row, axis=1)

    # Rank within each year (1 = best).  NaN composites get NaN rank.
    df["rank"] = (
        df.groupby("year")["composite_score"]
        .rank(ascending=False, method="min", na_option="keep")
    )

    # Safe cast: use nullable Int64 so NaN ranks don't crash
    df["rank"] = df["rank"].astype("Int64")

    return df


def assign_credit_band(score):
    """Map a composite score to a letter grade. NaN → 'NR' (not rated)."""
    if pd.isna(score):
        return "NR"
    for threshold, band in CREDIT_BANDS:
        if score >= threshold:
            return band
    return "CCC"


def run_scoring() -> pd.DataFrame:
    """Main scoring entry point."""
    print("=" * 55)
    print("  ASEAN Sovereign Credit — Scoring")
    print("=" * 55)

    df = pd.read_csv(CLEAN_DATA_PATH)

    # 1. Sub-scores
    print("\n[1/3] Computing sub-scores ...")
    df = compute_sub_scores(df)

    # 2. Composite + rank
    print("[2/3] Computing composite scores & ranks ...")
    df = compute_composite_score(df)

    # 3. Credit band
    print("[3/3] Assigning credit bands ...")
    df["credit_band"] = df["composite_score"].apply(assign_credit_band)

    # Save
    os.makedirs("data", exist_ok=True)
    df.to_csv(SCORED_DATA_PATH, index=False)
    print(f"\n  ✓ Scored data saved → {SCORED_DATA_PATH}")

    # Preview latest year
    latest_year = df["year"].max()
    preview_cols = ["country_name", "year", "composite_score", "rank", "credit_band"]
    preview = (
        df[df["year"] == latest_year][preview_cols]
        .sort_values("rank")
        .reset_index(drop=True)
    )
    print(f"\n  Latest year ({latest_year}):")
    print(preview.to_string(index=False))

    # Warn about missing data
    nr_count = (df["credit_band"] == "NR").sum()
    if nr_count > 0:
        print(f"\n  ⚠ {nr_count} country-year rows rated 'NR' due to missing data.")

    return df


if __name__ == "__main__":
    run_scoring()