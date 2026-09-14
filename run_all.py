"""
Runs stages 2-5 sequentially.
After this completes, launch the dashboard with:  streamlit run app.py

Updated for:
  - 10 indicators (Step 1)
  - Extended date range 2005-2024 (Step 2 backtest)
  - Timing per stage
  - Error handling (continues pipeline even if one stage fails)
"""

import time
import sys
from data_pipeline import run_pipeline
from scoring import run_scoring
from trends import run_trend_analysis
from ratings import run_ratings_comparison
from config import COUNTRIES, INDICATORS, START_YEAR, END_YEAR


def _run_stage(name: str, func, *args, **kwargs):
    """Run a single stage with timing and error handling."""
    start = time.time()
    try:
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"\n  ✓ {name} completed in {elapsed:.1f}s")
        return result, True
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n  ✗ {name} FAILED after {elapsed:.1f}s: {e}")
        print(f"    Continuing with remaining stages...\n")
        return None, False


def main():
    total_start = time.time()

    print("\n" + "=" * 55)
    print("  RUNNING FULL PIPELINE")
    print("=" * 55)
    print(f"  Countries:  {len(COUNTRIES)}  ({', '.join(COUNTRIES.values())})")
    print(f"  Indicators: {len(INDICATORS)}")
    print(f"  Date range: {START_YEAR}–{END_YEAR}")
    print("=" * 55 + "\n")

    results = {}

    # Stage 2: Data Pipeline
    results["data"], _ = _run_stage(
        "Stage 2 — Data Pipeline", run_pipeline
    )
    print()

    # Stage 3: Scoring
    results["scores"], _ = _run_stage(
        "Stage 3 — Scoring", run_scoring
    )
    print()

    # Stage 4: Trend Analysis
    results["trends"], _ = _run_stage(
        "Stage 4 — Trend Analysis", run_trend_analysis
    )
    print()

    # Stage 5: Ratings Comparison & Backtest
    results["ratings"], _ = _run_stage(
        "Stage 5 — Ratings Comparison & Backtest", run_ratings_comparison
    )

    # ── Final summary ─────────────────────────────────────────
    total_elapsed = time.time() - total_start
    succeeded = sum(1 for _, ok in [_check_result(r) for r in results.values()])
    total_stages = len(results)

    print("\n" + "=" * 55)
    print("  PIPELINE SUMMARY")
    print("=" * 55)

    stage_names = {
        "data":    "Data Pipeline",
        "scores":  "Scoring",
        "trends":  "Trend Analysis",
        "ratings": "Ratings & Backtest",
    }
    for key, name in stage_names.items():
        status = "✓" if results[key] is not None else "✗ FAILED"
        print(f"    {status}  {name}")

    print(f"\n  Total time: {total_elapsed:.1f}s")
    print(f"\n  Output files:")
    print(f"    data/raw_macro.csv          — Raw World Bank data")
    print(f"    data/clean_macro.csv        — Cleaned & gap-filled")
    print(f"    data/scored_macro.csv       — Sub-scores + composite")
    print(f"    data/trends.csv             — YoY changes & flags")
    print(f"    data/ratings_comparison.csv  — Model vs agency ratings")

    if all(v is not None for v in results.values()):
        print(f"\n  ✓ ALL STAGES COMPLETE")
    else:
        failed = [name for key, name in stage_names.items()
                  if results[key] is None]
        print(f"\n  ⚠ {len(failed)} stage(s) failed: {', '.join(failed)}")
        print(f"    Check errors above and re-run.")

    print(f"\n  Launch dashboard:  streamlit run app.py")
    print("=" * 55 + "\n")


def _check_result(result):
    """Helper to count successes."""
    return result, result is not None


if __name__ == "__main__":
    main()