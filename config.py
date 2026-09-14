"""
ASEAN Sovereign Credit Risk Scorecard — Configuration

Defines the country universe, macro indicators (with World Bank API codes),
scoring benchmarks, weights, and actual sovereign ratings for comparison.
"""

# ── Country universe (ISO3 codes) ──────────────────────────────
COUNTRIES = {
    "MYS": "Malaysia",
    "SGP": "Singapore",
    "THA": "Thailand",
    "IDN": "Indonesia",
    "PHL": "Philippines",
}

# ── World Bank indicators ──────────────────────────────────────
# Each entry:
#   - name:          human-readable label
#   - unit:          display unit
#   - direction:     'higher_better' or 'lower_better'
#   - weight:        portfolio weight in composite (must sum to 1.0)
#   - bench_min/max: absolute anchors for 1-10 scoring
#
# Benchmark rationale:
#   GDP Growth     -2% (recession) → 8% (strong EM growth)
#   Inflation       0% (deflationary risk) → 10% (high inflation)
#   Current Acct   -5% (large deficit) → 20% (large surplus, e.g. SGP)
#   FX Reserves     2 months (thin) → 12 months (very comfortable)
#   Govt Debt       20% (very low) → 80% (high for EM)
#   Gross Savings   15% (low) → 50% (high, e.g. SGP)

INDICATORS = {
    "NY.GDP.MKTP.KD.ZG": {
        "name": "GDP Growth",
        "unit": "%",
        "direction": "higher_better",
        "weight": 0.15,
        "bench_min": -2.0,
        "bench_max": 8.0,
    },
    "FP.CPI.TOTL.ZG": {
        "name": "Inflation",
        "unit": "%",
        "direction": "lower_better",
        "weight": 0.15,
        "bench_min": 0.0,
        "bench_max": 10.0,
    },
    "BN.CAB.XOKA.GD.ZS": {
        "name": "Current Account / GDP",
        "unit": "% of GDP",
        "direction": "higher_better",
        "weight": 0.20,
        "bench_min": -5.0,
        "bench_max": 20.0,
    },
    "FI.RES.TOTL.MO": {
        "name": "FX Reserves Cover",
        "unit": "months of imports",
        "direction": "higher_better",
        "weight": 0.15,
        "bench_min": 2.0,
        "bench_max": 12.0,
    },
    "GC.DOD.TOTL.GD.ZS": {
        "name": "Govt Debt / GDP",
        "unit": "% of GDP",
        "direction": "lower_better",
        "weight": 0.20,
        "bench_min": 20.0,
        "bench_max": 80.0,
    },
    "NY.GNS.ICTR.ZS": {
        "name": "Gross Savings / GDP",
        "unit": "% of GDP",
        "direction": "higher_better",
        "weight": 0.15,
        "bench_min": 15.0,
        "bench_max": 50.0,
    },
}

# ── Time range ─────────────────────────────────────────────────
START_YEAR = 2014
END_YEAR = 2024

# ── Actual sovereign ratings (verify / update before use) ──────
# Sources: S&P, Moody's, Fitch websites (as of early 2025)
#
# NOTE on Singapore debt data:
#   World Bank reports SGP central govt debt at ~130% of GDP because
#   it includes CPF (mandatory pension) balances and Special Singapore
#   Government Securities. These are *internal* obligations backed by
#   massive reserves — not external market debt. The model will
#   penalise SGP on this metric, creating a divergence vs. its AAA
#   rating. This is deliberate: it demonstrates why quantitative
#   models need qualitative overlay. Great interview talking point.

SOVEREIGN_RATINGS = {
    "MYS": {"S&P": "A-", "Moodys": "A3", "Fitch": "BBB+"},
    "SGP": {"S&P": "AAA", "Moodys": "Aaa", "Fitch": "AAA"},
    "THA": {"S&P": "BBB+", "Moodys": "Baa1", "Fitch": "BBB+"},
    "IDN": {"S&P": "BBB", "Moodys": "Baa2", "Fitch": "BBB"},
    "PHL": {"S&P": "BBB+", "Moodys": "Baa2", "Fitch": "BBB"},
}

# Numerical mapping (higher = better credit quality)
RATING_TO_NUMERIC = {
    "AAA": 21, "Aaa": 21,
    "AA+": 20, "Aa1": 20,
    "AA": 19, "Aa2": 19,
    "AA-": 18, "Aa3": 18,
    "A+": 17, "A1": 17,
    "A": 16, "A2": 16,
    "A-": 15, "A3": 15,
    "BBB+": 14, "Baa1": 14,
    "BBB": 13, "Baa2": 13,
    "BBB-": 12, "Baa3": 12,
    "BB+": 11, "Ba1": 11,
    "BB": 10, "Ba2": 10,
    "BB-": 9, "Ba3": 9,
    "B+": 8, "B1": 8,
    "B": 7, "B2": 7,
    "B-": 6, "B3": 6,
    "CCC+": 5, "Caa1": 5,
    "CCC": 4, "Caa2": 4,
    "CCC-": 3, "Caa3": 3,
    "CC": 2, "Ca": 2,
    "C": 1,
    "D": 0,
}

# ── File paths ─────────────────────────────────────────────────
RAW_DATA_PATH = "data/raw_macro.csv"
CLEAN_DATA_PATH = "data/clean_macro.csv"
SCORES_PATH = "data/scored_macro.csv"
TRENDS_PATH = "data/trends.csv"
RATINGS_PATH = "data/ratings_comparison.csv"
SCORED_DATA_PATH = "data/scored_macro.csv"