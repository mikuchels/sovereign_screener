"""
Runs stages 2-5 sequentially.
After this completes, launch the dashboard with:  streamlit run app.py
"""

from data_pipeline import run_pipeline
from scoring import run_scoring
from trends import run_trend_analysis
from ratings import run_ratings_comparison


def main():
    print("\n" + "=" * 55)
    print("  RUNNING FULL PIPELINE")
    print("=" * 55 + "\n")

    run_pipeline()
    print()
    run_scoring()
    print()
    run_trend_analysis()
    print()
    run_ratings_comparison()

    print("\n" + "=" * 55)
    print("  ✓ ALL STAGES COMPLETE")
    print("  Launch dashboard:  streamlit run app.py")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()