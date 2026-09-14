"""
Stage 4 — Ratings Comparison

Compares model-implied scores against actual S&P / Moody's / Fitch
sovereign ratings.  Rescales the model's 1-10 composite to the
agency numeric scale (0-21) so the gap is directly interpretable.

Usage:
    python ratings.py
"""

import pandas as pd
from config import (
    SOVEREIGN_RATINGS, RATING_TO_NUMERIC, COUNTRIES,
    SCORES_PATH, RATINGS_PATH,
)


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

    # Linear map: score 1 → 0, score 10 → 21
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


def print_comparison(comparison: pd.DataFrame):
    print("\n" + "=" * 70)
    print("  MODEL vs AGENCY RATINGS")
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


def run_ratings_comparison() -> pd.DataFrame:
    print("=" * 55)
    print("  ASEAN Sovereign Credit — Ratings Comparison")
    print("=" * 55)

    scores_df = pd.read_csv(SCORES_PATH)
    comparison = compare_ratings(scores_df)
    print_comparison(comparison)

    comparison.to_csv(RATINGS_PATH, index=False)
    print(f"\n  ✓ Comparison saved → {RATINGS_PATH}")
    return comparison


if __name__ == "__main__":
    run_ratings_comparison()