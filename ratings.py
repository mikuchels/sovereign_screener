"""
Stage 4 — Ratings Comparison & Backtest

Compares model-implied scores against actual S&P / Moody's / Fitch
sovereign ratings.  Rescales the model's 1-10 composite to the
agency numeric scale (0-21) so the gap is directly interpretable.

Updated for:
  - Step 2:  Historical backtest (model vs S&P year-by-year)
  - Step 9:  Reports which years have sufficient data for comparison
  - Step 10: Backtest DataFrame exportable to CSV

Usage:
    python ratings.py
"""

import pandas as pd
import numpy as np
from config import (
    SOVEREIGN_RATINGS, RATING_TO_NUMERIC, RATING_HISTORY,
    CREDIT_SCALE, COUNTRIES,
    SCORES_PATH, RATINGS_PATH,
)


# ══════════════════════════════════════════════════════════════
# Credit-band helpers (used by backtest)
# ══════════════════════════════════════════════════════════════

def map_credit_band(score: float) -> str:
    """Map a composite score (1-10) to an S&P letter grade."""
    if pd.isna(score):
        return "NR"
    for low, high, band, _ in CREDIT_SCALE:
        if low <= score < high:
            return band
    if score >= 10:
        return "AAA"
    return "CCC-"


def map_credit_numeric(score: float) -> float:
    """Map a composite score (1-10) to numeric (21 = AAA)."""
    if pd.isna(score):
        return np.nan
    for low, high, _, numeric in CREDIT_SCALE:
        if low <= score < high:
            return numeric
    if score >= 10:
        return 21
    return 3


# ══════════════════════════════════════════════════════════════
# Current snapshot: Model vs all 3 agencies
# ══════════════════════════════════════════════════════════════

def get_agency_scores() -> pd.DataFrame:
    """
    Convert letter ratings to numeric scores and compute an
    average across the three agencies.
    """
    rows = []
    for iso, ratings in SOVEREIGN_RATINGS.items():
        sp_num = RATING_TO_NUMERIC.get(ratings["S&P"])
        mo_num = RATING_TO_NUMERIC.get(ratings["Moodys"])
        fi_num = RATING_TO_NUMERIC.get(ratings["Fitch"])

        nums = [x for x in [sp_num, mo_num, fi_num] if x is not None]
        avg = round(sum(nums) / len(nums), 2) if nums else None

        rows.append(
            {
                "country_code": iso,
                "country_name": COUNTRIES[iso],
                "sp_rating": ratings["S&P"],
                "moodys_rating": ratings["Moodys"],
                "fitch_rating": ratings["Fitch"],
                "sp_numeric": sp_num,
                "moodys_numeric": mo_num,
                "fitch_numeric": fi_num,
                "agency_avg_numeric": avg,
            }
        )
    return pd.DataFrame(rows)


def compare_ratings(scores_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge latest-year model scores with agency ratings.
    Rescale composite (1-10) → agency scale (0-21).
    Compute gap and directional signal.
    """
    agency = get_agency_scores()

    latest_year = scores_df["year"].max()
    model = scores_df[scores_df["year"] == latest_year][
        ["country_code", "composite_score", "credit_band", "rank"]
    ].copy()

    # Use CREDIT_SCALE-based numeric if available, else linear rescale
    if "credit_numeric" in scores_df.columns:
        model_latest = scores_df[scores_df["year"] == latest_year]
        model["model_numeric_rescaled"] = model_latest["credit_numeric"].values
    else:
        # Fallback: linear map score 1 → 0, score 10 → 21
        model["model_numeric_rescaled"] = (
            (model["composite_score"] - 1) / 9 * 21
        ).round(2)

    comparison = model.merge(agency, on="country_code", how="left")

    # Positive gap = model more bullish than agencies
    comparison["gap"] = (
        comparison["model_numeric_rescaled"] - comparison["agency_avg_numeric"]
    ).round(2)

    comparison["signal"] = comparison["gap"].apply(
        lambda x: (
            "MODEL MORE BULLISH"
            if x > 1.5
            else ("MODEL MORE BEARISH" if x < -1.5 else "ALIGNED")
        )
    )
    return comparison


# ══════════════════════════════════════════════════════════════
# Step 2: Historical Backtest — Model vs S&P over time
# ══════════════════════════════════════════════════════════════

def get_backtest_df(scored_data: pd.DataFrame) -> pd.DataFrame:
    """
    Build a tidy DataFrame comparing model-implied ratings against
    actual S&P ratings for every year in RATING_HISTORY.

    Returns columns:
        country_code, country_name, year,
        actual_rating, actual_numeric,
        model_band, model_numeric, composite_score,
        difference (model_numeric - actual_numeric)
    """
    rows = []

    for country, history in RATING_HISTORY.items():
        for year, actual_rating in history:
            # Find matching model output
            match = scored_data[
                (scored_data["country_code"] == country)
                & (scored_data["year"] == year)
            ]

            if match.empty:
                continue

            comp = match["composite_score"].values[0]

            # Use pre-computed credit_numeric if available
            if "credit_numeric" in match.columns:
                m_num = match["credit_numeric"].values[0]
            else:
                m_num = map_credit_numeric(comp)

            if "credit_band" in match.columns:
                m_band = match["credit_band"].values[0]
            else:
                m_band = map_credit_band(comp)

            a_num = RATING_TO_NUMERIC.get(actual_rating, np.nan)

            diff = np.nan
            if not pd.isna(m_num) and not pd.isna(a_num):
                diff = m_num - a_num

            rows.append({
                "country_code":   country,
                "country_name":   COUNTRIES.get(country, country),
                "year":           year,
                "actual_rating":  actual_rating,
                "actual_numeric": a_num,
                "model_band":     m_band,
                "model_numeric":  m_num,
                "composite_score": comp,
                "difference":     diff,
            })

    return pd.DataFrame(rows)


def get_backtest_stats(backtest_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-country accuracy stats from the backtest.

    Returns columns:
        country_code, country_name, n_years,
        mean_diff, abs_mean_diff, max_abs_diff,
        exact_match_pct, within_1_notch_pct, within_2_notch_pct
    """
    if backtest_df.empty:
        return pd.DataFrame()

    rows = []
    for country in backtest_df["country_code"].unique():
        cdf = backtest_df[backtest_df["country_code"] == country].dropna(
            subset=["difference"]
        )
        if cdf.empty:
            continue

        n = len(cdf)
        diffs = cdf["difference"]
        abs_diffs = diffs.abs()

        rows.append({
            "country_code":      country,
            "country_name":      COUNTRIES.get(country, country),
            "n_years":           n,
            "mean_diff":         round(diffs.mean(), 2),
            "abs_mean_diff":     round(abs_diffs.mean(), 2),
            "max_abs_diff":      round(abs_diffs.max(), 2),
            "exact_match_pct":   round((abs_diffs == 0).sum() / n * 100, 1),
            "within_1_notch_pct": round((abs_diffs <= 1).sum() / n * 100, 1),
            "within_2_notch_pct": round((abs_diffs <= 2).sum() / n * 100, 1),
        })

    return pd.DataFrame(rows)


def detect_rating_actions(backtest_df: pd.DataFrame) -> pd.DataFrame:
    """
    Identify years where S&P actually changed its rating (upgrade/downgrade)
    and check whether the model's implied rating was already signalling
    the move beforehand ("model led").

    Returns a DataFrame of rating-change events.
    """
    if backtest_df.empty:
        return pd.DataFrame()

    events = []

    for country in backtest_df["country_code"].unique():
        cdf = backtest_df[
            backtest_df["country_code"] == country
        ].sort_values("year")

        prev_rating = None
        for _, row in cdf.iterrows():
            if prev_rating is not None and row["actual_rating"] != prev_rating:
                prev_num = RATING_TO_NUMERIC.get(prev_rating, np.nan)
                curr_num = row["actual_numeric"]

                if not pd.isna(prev_num) and not pd.isna(curr_num):
                    direction = "⬆️ Upgrade" if curr_num > prev_num else "⬇️ Downgrade"

                    # Did the model already reflect this direction?
                    model_led = False
                    if direction.startswith("⬆️") and row["model_numeric"] > curr_num:
                        model_led = True
                    elif direction.startswith("⬇️") and row["model_numeric"] < curr_num:
                        model_led = True

                    events.append({
                        "country_code":  country,
                        "country_name":  COUNTRIES.get(country, country),
                        "year":          int(row["year"]),
                        "action":        direction,
                        "from_rating":   prev_rating,
                        "to_rating":     row["actual_rating"],
                        "model_band":    row["model_band"],
                        "model_numeric": row["model_numeric"],
                        "model_led":     "✅" if model_led else "❌",
                    })

            prev_rating = row["actual_rating"]

    return pd.DataFrame(events)


# ══════════════════════════════════════════════════════════════
# Console output
# ══════════════════════════════════════════════════════════════

def print_comparison(comparison: pd.DataFrame):
    """Pretty-print the current model vs agency snapshot."""
    print("\n" + "=" * 70)
    print("  MODEL vs AGENCY RATINGS (Latest Year)")
    print("=" * 70)

    for _, row in comparison.sort_values("rank").iterrows():
        print(f"\n  {row['country_name']} ({row['country_code']})")
        print(
            f"    Model:   {row['composite_score']:.2f}/10  →  "
            f"Implied: {row['credit_band']}"
        )
        print(
            f"    Actual:  S&P {row['sp_rating']}  |  "
            f"Moody's {row['moodys_rating']}  |  "
            f"Fitch {row['fitch_rating']}"
        )
        print(f"    Gap:     {row['gap']:+.2f}  →  {row['signal']}")


def print_backtest_summary(stats_df: pd.DataFrame, events_df: pd.DataFrame):
    """Pretty-print the backtest results."""
    print("\n" + "=" * 70)
    print("  BACKTEST: MODEL vs S&P HISTORICAL RATINGS")
    print("=" * 70)

    if stats_df.empty:
        print("\n  ⚠  No backtest data available.")
        return

    for _, row in stats_df.iterrows():
        print(f"\n  {row['country_name']}:")
        print(f"    Years compared:     {row['n_years']}")
        print(f"    Mean gap (notches): {row['mean_diff']:+.2f}")
        print(f"    Avg |gap|:          {row['abs_mean_diff']:.2f}")
        print(f"    Within 1 notch:     {row['within_1_notch_pct']:.0f}%")
        print(f"    Within 2 notches:   {row['within_2_notch_pct']:.0f}%")

    if not events_df.empty:
        print(f"\n  --- Rating Actions ({len(events_df)} events) ---")
        for _, ev in events_df.iterrows():
            print(
                f"    {ev['country_name']} {ev['year']}: "
                f"{ev['action']}  {ev['from_rating']} → {ev['to_rating']}  "
                f"(model: {ev['model_band']})  {ev['model_led']}"
            )


# ══════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════

def run_ratings_comparison() -> pd.DataFrame:
    """Run both the current snapshot comparison and the historical backtest."""
    print("=" * 55)
    print("  ASEAN Sovereign Credit — Ratings Comparison")
    print("=" * 55)

    scores_df = pd.read_csv(SCORES_PATH)

    # ── Part 1: Current snapshot ──
    print("\n[1/2] Current model vs agency ratings...")
    comparison = compare_ratings(scores_df)
    print_comparison(comparison)

    comparison.to_csv(RATINGS_PATH, index=False)
    print(f"\n  ✓ Comparison saved → {RATINGS_PATH}")

    # ── Part 2: Historical backtest (Step 2) ──
    print("\n[2/2] Running historical backtest...")
    backtest_df = get_backtest_df(scores_df)

    if not backtest_df.empty:
        stats_df  = get_backtest_stats(backtest_df)
        events_df = detect_rating_actions(backtest_df)
        print_backtest_summary(stats_df, events_df)

        # Save backtest outputs
        backtest_path = RATINGS_PATH.replace(".csv", "_backtest.csv")
        backtest_df.to_csv(backtest_path, index=False)
        print(f"\n  ✓ Backtest data saved → {backtest_path}")
    else:
        print("\n  ⚠  No overlapping years between model data and RATING_HISTORY.")
        print(f"     Model data range: {scores_df['year'].min()}–{scores_df['year'].max()}")
        print(f"     Ensure START_YEAR in config.py is ≤ 2005.")
        stats_df = pd.DataFrame()
        events_df = pd.DataFrame()

    return comparison


if __name__ == "__main__":
    run_ratings_comparison()