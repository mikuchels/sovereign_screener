"""
Stage 2 — Data Pipeline (hardened)

Pulls macro data from the World Bank API v2, with retry logic and
extended timeouts to handle slow/flaky connections.

Now supports:
  - 10 indicators (Step 1 expansion)
  - Extended date range 2005-2024 (Step 2 backtest support)
  - Data freshness reporting (Step 9)
  - Pagination for larger result sets

Usage:
    python data_pipeline.py
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
import time
import os
from config import (
    COUNTRIES, INDICATORS, START_YEAR, END_YEAR,
    RAW_DATA_PATH, CLEAN_DATA_PATH,
)


def _get_session() -> requests.Session:
    """
    Build a requests Session with automatic retries and longer timeouts.
    Retries on 429 (rate-limit), 500, 502, 503, 504 with exponential backoff.
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=5,                    # up to 5 retries
        backoff_factor=2,           # waits 2, 4, 8, 16, 32 seconds
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# Module-level session (reused across calls)
SESSION = _get_session()
REQUEST_TIMEOUT = (30, 120)  # (connect_timeout, read_timeout) in seconds


def fetch_world_bank(
    indicator_code: str,
    country_codes: list,
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    """
    Fetch a single indicator from the World Bank API v2.
    Returns DataFrame with columns: country_code, year, value.

    Now handles pagination — if the API returns more than one page
    of results, all pages are fetched and concatenated.
    """
    countries_str = ";".join(country_codes)
    per_page = 1000
    page = 1
    all_records = []

    while True:
        url = (
            f"http://api.worldbank.org/v2/country/{countries_str}"
            f"/indicator/{indicator_code}"
            f"?date={start_year}:{end_year}"
            f"&format=json&per_page={per_page}&page={page}"
        )

        try:
            response = SESSION.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"  ✗  Failed to fetch {indicator_code} (page {page}): {e}")
            print(f"     Will continue — this indicator will have missing data.")
            break

        data = response.json()

        # API returns [metadata_dict, records_list]
        if len(data) < 2 or data[1] is None:
            if page == 1:
                print(f"  ⚠  No data returned for {indicator_code}")
            break

        for entry in data[1]:
            all_records.append(
                {
                    "country_code": entry["countryiso3code"],
                    "year": int(entry["date"]),
                    "value": entry["value"],
                }
            )

        # Check if there are more pages
        meta = data[0]
        total_pages = meta.get("pages", 1)
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.5)  # polite pause between pages

    if not all_records:
        return pd.DataFrame(columns=["country_code", "year", "value"])

    df = pd.DataFrame(all_records)
    df = df.sort_values(["country_code", "year"]).reset_index(drop=True)
    return df


def fetch_all_indicators() -> pd.DataFrame:
    """
    Pull every indicator for every country.
    Returns a wide DataFrame indexed by (country_code, year).
    """
    country_codes = list(COUNTRIES.keys())
    frames = []
    total = len(INDICATORS)

    for i, (code, meta) in enumerate(INDICATORS.items(), 1):
        print(f"  [{i}/{total}] Fetching: {meta['name']} ({code}) ...")
        df = fetch_world_bank(code, country_codes, START_YEAR, END_YEAR)
        df = df.rename(columns={"value": code})
        frames.append(df)
        time.sleep(1.0)  # polite spacing between calls

    # Merge all indicators on (country_code, year)
    merged = frames[0]
    for df in frames[1:]:
        merged = merged.merge(df, on=["country_code", "year"], how="outer")

    merged = merged.sort_values(["country_code", "year"]).reset_index(drop=True)
    return merged


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Handle gaps: forward-fill within each country, then back-fill.
    Prints a coverage report so you know what's missing.
    """
    indicator_cols = [c for c in INDICATORS.keys() if c in df.columns]

    df = df.sort_values(["country_code", "year"])
    for col in indicator_cols:
        df[col] = df.groupby("country_code")[col].transform(
            lambda x: x.ffill().bfill()
        )

    # Coverage report
    print("\n  --- Data Coverage ---")
    for col in indicator_cols:
        name = INDICATORS[col]["name"]
        missing = df[col].isna().sum()
        total = len(df)
        pct = (total - missing) / total * 100
        status = "✓" if missing == 0 else "⚠"
        print(f"    {status} {name}: {total - missing}/{total} ({pct:.0f}%)")

    return df


def add_country_names(df: pd.DataFrame) -> pd.DataFrame:
    df["country_name"] = df["country_code"].map(COUNTRIES)
    return df


# ── Step 9: Data freshness helper ──────────────────────────────
def get_data_freshness(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each country × indicator, find the most recent year that
    has a non-null value.  Returns a tidy summary DataFrame.

    Used in the Streamlit dashboard to show data-staleness warnings.
    """
    indicator_cols = [c for c in INDICATORS.keys() if c in df.columns]
    rows = []

    for country in df["country_code"].unique():
        cdf = df[df["country_code"] == country]
        for col in indicator_cols:
            non_null = cdf.dropna(subset=[col])
            latest_year = int(non_null["year"].max()) if not non_null.empty else None
            rows.append({
                "country_code": country,
                "country_name": COUNTRIES.get(country, country),
                "indicator_code": col,
                "indicator_name": INDICATORS[col]["name"],
                "latest_year": latest_year,
                "is_stale": latest_year is not None and latest_year < (END_YEAR - 2),
            })

    return pd.DataFrame(rows)


def get_freshness_summary(df: pd.DataFrame) -> dict:
    """
    Quick summary: the most recent year with ANY non-null data per country.
    Returns dict like {'SGP': 2023, 'IDN': 2023, ...}
    """
    indicator_cols = [c for c in INDICATORS.keys() if c in df.columns]
    summary = {}
    for country in df["country_code"].unique():
        cdf = df[df["country_code"] == country].dropna(
            subset=indicator_cols, how="all"
        )
        summary[country] = int(cdf["year"].max()) if not cdf.empty else None
    return summary


def run_pipeline() -> pd.DataFrame:
    """Main pipeline: fetch → clean → save."""
    os.makedirs("data", exist_ok=True)

    n_indicators = len(INDICATORS)
    n_countries = len(COUNTRIES)
    n_years = END_YEAR - START_YEAR + 1

    print("=" * 55)
    print("  ASEAN Sovereign Credit — Data Pipeline")
    print("=" * 55)
    print(f"  {n_countries} countries × {n_indicators} indicators × {n_years} years")
    print(f"  Range: {START_YEAR}–{END_YEAR}")
    print()

    # 1. Fetch
    print("[1/4] Fetching from World Bank API...")
    raw = fetch_all_indicators()
    raw = add_country_names(raw)
    raw.to_csv(RAW_DATA_PATH, index=False)
    print(f"\n  ✓ Raw data saved → {RAW_DATA_PATH}  (shape: {raw.shape})")

    # 2. Clean
    print("\n[2/4] Cleaning...")
    clean = clean_data(raw.copy())
    clean.to_csv(CLEAN_DATA_PATH, index=False)
    print(f"\n  ✓ Clean data saved → {CLEAN_DATA_PATH}")

    # 3. Freshness report  (Step 9)
    print("\n[3/4] Data freshness check...")
    freshness = get_freshness_summary(clean)
    for country, latest in freshness.items():
        name = COUNTRIES.get(country, country)
        flag = "✓" if latest and latest >= END_YEAR - 2 else "⚠ STALE"
        print(f"    {flag} {name}: latest data = {latest}")

    # Also save detailed freshness for the dashboard
    freshness_detail = get_data_freshness(clean)
    stale = freshness_detail[freshness_detail["is_stale"]]
    if not stale.empty:
        print(f"\n  ⚠  {len(stale)} country×indicator pairs are stale (>2 yr old):")
        for _, row in stale.iterrows():
            print(f"     {row['country_name']} / {row['indicator_name']} → {row['latest_year']}")

    # 4. Preview
    print(f"\n[4/4] Preview (latest year):")
    latest = clean[clean["year"] == clean["year"].max()]
    print(latest.to_string(index=False))

    return clean


if __name__ == "__main__":
    run_pipeline()