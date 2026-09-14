"""
Stage 3 — Scoring Engine

Reads clean macro data, normalises each indicator to a 1-10 sub-score
using absolute benchmarks (from config), computes a weighted composite,
ranks countries per year, and assigns a letter-grade credit band.

Updated for:
  - Step 1:  10 indicators (incl. moderate_better direction)
  - Step 4:  Accepts optional custom weights (for sidebar sliders)
  - Step 9:  Reports scoring coverage gaps

Usage:
    python scoring.py
"""

import pandas as pd
import numpy as np
import os
from config import (
    INDICATORS, CLEAN_DATA_PATH, SCORED_DATA_PATH, CREDIT_SCALE,
)


# ══════════════════════════════════════════════════════════════
# Scoring helpers
# ══════════════════════════════════════════════════════════════

def _score_value(value: float, meta: dict) -> float:
    """
    Score a single raw value on a 1-10 scale using absolute benchmarks.

    Supports three direction types:
      - higher_better:   bench_min → 1, bench_max → 10
      - lower_better:    bench_min → 10, bench_max → 1
      - moderate_better: bench_target → 10, distance from target penalised

    Returns NaN if input is NaN.
    Scores are clipped to [1, 10].
    """
    if pd.isna(value):
        return np.nan

    direction = meta["direction"]
    b_min = meta["bench_min"]
    b_max = meta["bench_max"]

    if direction == "higher_better":
        # Linear: bench_min → 1, bench_max → 10
        if b_max == b_min:
            return 5.5
        raw = 1 + 9 * (value - b_min) / (b_max - b_min)

    elif direction == "lower_better":
        # Linear: bench_min → 10, bench_max → 1
        if b_max == b_min:
            return 5.5
        raw = 1 + 9 * (b_max - value) / (b_max - b_min)

    elif direction == "moderate_better":
        # Peak at bench_target, drops off symmetrically
        target = meta.get("bench_target", (b_min + b_max) / 2)
        max_dist = max(abs(b_max - target), abs(b_min - target))
        if max_dist == 0:
            return 5.5
        dist = abs(value - target)
        raw = 10 - 9 * (dist / max_dist)

    else:
        raise ValueError(f"Unknown direction: {direction}")

    return float(np.clip(raw, 1.0, 10.0))


def compute_sub_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each indicator, score every row using absolute benchmarks.
    Adds columns like  score_NY.GDP.MKTP.KD.ZG  etc.

    Unlike the old min-max approach (relative to peers in the same year),
    absolute benchmarks make scores comparable across years — essential
    for the backtest (Step 2).
    """
    indicator_cols = [c for c in INDICATORS.keys() if c in df.columns]

    for col in indicator_cols:
        meta = INDICATORS[col]
        score_col = f"score_{col}"
        df[score_col] = df[col].apply(lambda v: _score_value(v, meta))

    return df


def compute_composite_score(
    df: pd.DataFrame,
    custom_weights: dict = None,
) -> pd.DataFrame:
    """
    Weighted average of sub-scores → composite_score (1 to 10).

    Parameters
    ----------
    df : DataFrame with score_ columns already computed
    custom_weights : dict mapping indicator_code → weight (0-1).
                     If None, uses default weights from config.
                     Weights are auto-normalised to sum to 1.0.

    Key behaviour: if some sub-scores are NaN (e.g. missing data),
    the weighted average is computed over *available* sub-scores only,
    re-normalising weights so they still sum to 1.
    """
    # Determine which indicators have score columns in the DataFrame
    available = [c for c in INDICATORS.keys() if f"score_{c}" in df.columns]

    # Build weight vector
    if custom_weights is not None:
        raw_weights = {c: custom_weights.get(c, INDICATORS[c]["weight"])
                       for c in available}
    else:
        raw_weights = {c: INDICATORS[c]["weight"] for c in available}

    # Normalise so available weights sum to 1
    total_w = sum(raw_weights.values())
    if total_w > 0:
        norm_weights = {c: w / total_w for c, w in raw_weights.items()}
    else:
        norm_weights = {c: 1.0 / len(available) for c in available}

    score_cols = [f"score_{c}" for c in available]
    weight_arr = np.array([norm_weights[c] for c in available])

    def _weighted_mean_row(row):
        """Compute weighted mean for a single row, skipping NaN sub-scores."""
        values = row.values.astype(float)
        mask = ~np.isnan(values)
        if mask.sum() == 0:
            return np.nan
        w = weight_arr[mask]
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


# ══════════════════════════════════════════════════════════════
# Credit band mapping  (uses CREDIT_SCALE from config)
# ══════════════════════════════════════════════════════════════

def assign_credit_band(score: float) -> str:
    """Map a composite score to an S&P letter grade. NaN → 'NR'."""
    if pd.isna(score):
        return "NR"
    for low, high, band, _ in CREDIT_SCALE:
        if low <= score < high:
            return band
    # Edge cases
    if score >= 10:
        return "AAA"
    return "CCC-"


def assign_credit_numeric(score: float) -> float:
    """Map a composite score to a numeric rating (21 = AAA). NaN → NaN."""
    if pd.isna(score):
        return np.nan
    for low, high, _, numeric in CREDIT_SCALE:
        if low <= score < high:
            return numeric
    if score >= 10:
        return 21
    return 3


# ══════════════════════════════════════════════════════════════
# Main pipeline entry point
# ══════════════════════════════════════════════════════════════

def run_scoring(custom_weights: dict = None) -> pd.DataFrame:
    """
    Main scoring entry point.

    Parameters
    ----------
    custom_weights : optional dict of indicator_code → weight.
                     Passed through to compute_composite_score().
                     Used by the Streamlit sidebar (Step 4).
    """
    print("=" * 55)
    print("  ASEAN Sovereign Credit — Scoring")
    print("=" * 55)

    n_indicators = len(INDICATORS)
    print(f"  {n_indicators} indicators, benchmarks from config.py")
    if custom_weights:
        print("  ⚙  Using custom weights (sidebar override)")
    else:
        print("  ⚖  Using default weights from config")

    df = pd.read_csv(CLEAN_DATA_PATH)

    # 1. Sub-scores (absolute benchmarks)
    print(f"\n[1/4] Computing sub-scores ({n_indicators} indicators) ...")
    df = compute_sub_scores(df)

    # 2. Composite + rank
    print("[2/4] Computing composite scores & ranks ...")
    df = compute_composite_score(df, custom_weights=custom_weights)

    # 3. Credit band + numeric
    print("[3/4] Assigning credit bands ...")
    df["credit_band"]    = df["composite_score"].apply(assign_credit_band)
    df["credit_numeric"] = df["composite_score"].apply(assign_credit_numeric)

    # 4. Coverage report (Step 9)
    print("[4/4] Scoring coverage check ...")
    indicator_cols = [c for c in INDICATORS.keys() if c in df.columns]
    for col in indicator_cols:
        score_col = f"score_{col}"
        if score_col in df.columns:
            missing = df[score_col].isna().sum()
            total = len(df)
            name = INDICATORS[col]["name"]
            status = "✓" if missing == 0 else "⚠"
            print(f"    {status} {name}: {total - missing}/{total} scored")

    # Save
    os.makedirs("data", exist_ok=True)
    df.to_csv(SCORED_DATA_PATH, index=False)
    print(f"\n  ✓ Scored data saved → {SCORED_DATA_PATH}")

    # Preview latest year
    latest_year = df["year"].max()
    preview_cols = [
        "country_name", "year", "composite_score",
        "rank", "credit_band", "credit_numeric",
    ]
    preview_cols = [c for c in preview_cols if c in df.columns]
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