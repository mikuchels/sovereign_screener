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
#   - short_name:    abbreviated label (for radar charts — Step 5)
#   - unit:          display unit
#   - direction:     'higher_better', 'lower_better', or 'moderate_better'
#   - weight:        default weight in composite (must sum to 1.0)
#   - bench_min/max: absolute anchors for 1-10 scoring
#   - bench_target:  (only for 'moderate_better') optimal value
#
# Benchmark rationale (original 6):
#   GDP Growth     -2% (recession) → 8% (strong EM growth)
#   Inflation       0% (deflationary risk) → 10% (high inflation)
#   Current Acct   -5% (large deficit) → 20% (large surplus, e.g. SGP)
#   FX Reserves     2 months (thin) → 12 months (very comfortable)
#   Govt Debt       20% (very low) → 80% (high for EM)
#   Gross Savings   15% (low) → 50% (high, e.g. SGP)
#
# Benchmark rationale (new 4 — Step 1):
#   External Debt   10% (very low) → 100% (dangerously high)
#   GDP per Capita  $1,000 (low income) → $65,000 (advanced economy)
#   Real Int. Rate  optimal ~2.5%; extremes penalised (moderate_better)
#   Fiscal Balance  -10% (deep deficit) → 5% (healthy surplus)

INDICATORS = {
    # ── Original 6 indicators ──────────────────────────────────
    "NY.GDP.MKTP.KD.ZG": {
        "name": "GDP Growth",
        "short_name": "GDP Growth",
        "unit": "%",
        "direction": "higher_better",
        "weight": 0.10,
        "bench_min": -2.0,
        "bench_max": 8.0,
    },
    "FP.CPI.TOTL.ZG": {
        "name": "Inflation",
        "short_name": "Inflation",
        "unit": "%",
        "direction": "lower_better",
        "weight": 0.10,
        "bench_min": 0.0,
        "bench_max": 10.0,
    },
    "BN.CAB.XOKA.GD.ZS": {
        "name": "Current Account / GDP",
        "short_name": "Curr Acct",
        "unit": "% of GDP",
        "direction": "higher_better",
        "weight": 0.12,
        "bench_min": -5.0,
        "bench_max": 20.0,
    },
    "FI.RES.TOTL.MO": {
        "name": "FX Reserves Cover",
        "short_name": "FX Reserves",
        "unit": "months of imports",
        "direction": "higher_better",
        "weight": 0.10,
        "bench_min": 2.0,
        "bench_max": 12.0,
    },
    "GC.DOD.TOTL.GD.ZS": {
        "name": "Govt Debt / GDP",
        "short_name": "Govt Debt",
        "unit": "% of GDP",
        "direction": "lower_better",
        "weight": 0.12,
        "bench_min": 20.0,
        "bench_max": 80.0,
    },
    "NY.GNS.ICTR.ZS": {
        "name": "Gross Savings / GDP",
        "short_name": "Savings",
        "unit": "% of GDP",
        "direction": "higher_better",
        "weight": 0.08,
        "bench_min": 15.0,
        "bench_max": 50.0,
    },

    # ── Step 1: 4 NEW indicators ───────────────────────────────
    "DT.DOD.DECT.GD.ZS": {
        "name": "External Debt / GDP",
        "short_name": "Ext Debt",
        "unit": "% of GDP",
        "direction": "lower_better",
        "weight": 0.10,
        "bench_min": 10.0,
        "bench_max": 100.0,
    },
    "NY.GDP.PCAP.CD": {
        "name": "GDP per Capita",
        "short_name": "GDP/Cap",
        "unit": "USD",
        "direction": "higher_better",
        "weight": 0.10,
        "bench_min": 1000.0,
        "bench_max": 65000.0,
    },
    "FR.INR.RINR": {
        "name": "Real Interest Rate",
        "short_name": "Real Rate",
        "unit": "%",
        "direction": "moderate_better",        # ← NEW direction type
        "weight": 0.08,
        "bench_min": -5.0,
        "bench_max": 15.0,
        "bench_target": 2.5,                   # optimal value
    },
    "GC.BAL.CASH.GD.ZS": {
        "name": "Fiscal Balance / GDP",
        "short_name": "Fiscal Bal",
        "unit": "% of GDP",
        "direction": "higher_better",
        "weight": 0.10,
        "bench_min": -10.0,
        "bench_max": 5.0,
    },
}

# ── Verify weights sum to 1.0 ─────────────────────────────────
_wt_sum = sum(v["weight"] for v in INDICATORS.values())
assert abs(_wt_sum - 1.0) < 1e-9, f"Weights sum to {_wt_sum}, expected 1.0"

# ── Time range ─────────────────────────────────────────────────
START_YEAR = 2005          # ← extended back for backtest (was 2014)
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

# ── Step 2: Historical S&P ratings for backtest ────────────────
# ⚠️  Approximate annual snapshots — verify against S&P press releases
# Used in the Backtest tab to compare model-implied vs actual over time
RATING_HISTORY = {
    "IDN": [
        (2005, "BB-"), (2006, "BB-"), (2007, "BB-"), (2008, "BB-"),
        (2009, "BB-"), (2010, "BB"),  (2011, "BB+"), (2012, "BB+"),
        (2013, "BB+"), (2014, "BB+"), (2015, "BB+"), (2016, "BB+"),
        (2017, "BBB-"),(2018, "BBB-"),(2019, "BBB"), (2020, "BBB"),
        (2021, "BBB"), (2022, "BBB"), (2023, "BBB"),
    ],
    "MYS": [
        (2005, "A-"), (2006, "A-"), (2007, "A-"), (2008, "A-"),
        (2009, "A-"), (2010, "A-"), (2011, "A-"), (2012, "A-"),
        (2013, "A-"), (2014, "A-"), (2015, "A-"), (2016, "A-"),
        (2017, "A-"), (2018, "A-"), (2019, "A-"), (2020, "A-"),
        (2021, "A-"), (2022, "A-"), (2023, "A-"),
    ],
    "THA": [
        (2005, "BBB+"), (2006, "BBB+"), (2007, "BBB+"), (2008, "BBB+"),
        (2009, "BBB+"), (2010, "BBB+"), (2011, "BBB+"), (2012, "BBB+"),
        (2013, "BBB+"), (2014, "BBB+"), (2015, "BBB+"), (2016, "BBB+"),
        (2017, "BBB+"), (2018, "BBB+"), (2019, "BBB+"), (2020, "BBB+"),
        (2021, "BBB+"), (2022, "BBB+"), (2023, "BBB+"),
    ],
    "PHL": [
        (2005, "BB-"), (2006, "BB-"), (2007, "BB-"), (2008, "BB-"),
        (2009, "BB-"), (2010, "BB"),  (2011, "BB"),  (2012, "BB+"),
        (2013, "BBB-"),(2014, "BBB"), (2015, "BBB"), (2016, "BBB"),
        (2017, "BBB"), (2018, "BBB"), (2019, "BBB+"),(2020, "BBB+"),
        (2021, "BBB+"),(2022, "BBB+"),(2023, "BBB+"),
    ],
    "SGP": [(y, "AAA") for y in range(2005, 2024)],
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

# ── Composite score → S&P credit band mapping ─────────────────
# Used to translate the 1-10 composite into an implied rating
CREDIT_SCALE = [
    # (score_low, score_high, band, numeric)
    (9.0, 10.01, "AAA",  21),
    (8.5,  9.0,  "AA+",  20),
    (8.0,  8.5,  "AA",   19),
    (7.5,  8.0,  "AA-",  18),
    (7.0,  7.5,  "A+",   17),
    (6.5,  7.0,  "A",    16),
    (6.0,  6.5,  "A-",   15),
    (5.5,  6.0,  "BBB+", 14),
    (5.0,  5.5,  "BBB",  13),
    (4.5,  5.0,  "BBB-", 12),
    (4.0,  4.5,  "BB+",  11),
    (3.5,  4.0,  "BB",   10),
    (3.0,  3.5,  "BB-",   9),
    (2.5,  3.0,  "B+",    8),
    (2.0,  2.5,  "B",     7),
    (1.5,  2.0,  "B-",    6),
    (1.0,  1.5,  "CCC+",  5),
    (0.5,  1.0,  "CCC",   4),
    (0.0,  0.5,  "CCC-",  3),
]

# ── File paths ─────────────────────────────────────────────────
RAW_DATA_PATH = "data/raw_macro.csv"
CLEAN_DATA_PATH = "data/clean_macro.csv"
SCORES_PATH = "data/scored_macro.csv"
TRENDS_PATH = "data/trends.csv"
RATINGS_PATH = "data/ratings_comparison.csv"
SCORED_DATA_PATH = "data/scored_macro.csv"