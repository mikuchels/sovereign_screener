"""
Stage 2 — Data Pipeline (hardened)

Pulls macro data from the World Bank API v2, with retry logic and
extended timeouts to handle slow/flaky connections.

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
    """
    countries_str = ";".join(country_codes)
    url = (
        f"http://api.worldbank.org/v2/country/{countries_str}"
        f"/indicator/{indicator_code}"
        f"?date={start_year}:{end_year}"
        f"&format=json&per_page=1000"
    )

    try:
        response = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"  ✗  Failed to fetch {indicator_code}: {e}")
        print(f"     Will continue — this indicator will have missing data.")
        return pd.DataFrame(columns=["country_code", "year", "value"])

    data = response.json()

    # API returns [metadata_dict, records_list]
    if len(data) < 2 or data[1] is None:
        print(f"  ⚠  No data returned for {indicator_code}")
        return pd.DataFrame(columns=["country_code", "year", "value"])

    records = []
    for entry in data[1]:
        records.append(
            {
                "country_code": entry["countryiso3code"],
                "year": int(entry["date"]),
                "value": entry["value"],
            }
        )

    df = pd.DataFrame(records)
    df = df.sort_values(["country_code", "year"]).reset_index(drop=True)
    return df


def fetch_all_indicators() -> pd.DataFrame:
    """
    Pull every indicator for every country.
    Returns a wide DataFrame indexed by (country_code, year).
    """
    country_codes = list(COUNTRIES.keys())
    frames = []

    for code, meta in INDICATORS.items():
        print(f"  Fetching: {meta['name']} ({code}) ...")
        df = fetch_world_bank(code, country_codes, START_YEAR, END_YEAR)
        df = df.rename(columns={"value": code})
        frames.append(df)
        time.sleep(1.0)  # more polite spacing between calls

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
    indicator_cols = list(INDICATORS.keys())

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


def run_pipeline() -> pd.DataFrame:
    """Main pipeline: fetch → clean → save."""
    os.makedirs("data", exist_ok=True)

    print("=" * 55)
    print("  ASEAN Sovereign Credit — Data Pipeline")
    print("=" * 55)

    # 1. Fetch
    print("\n[1/3] Fetching from World Bank API...")
    raw = fetch_all_indicators()
    raw = add_country_names(raw)
    raw.to_csv(RAW_DATA_PATH, index=False)
    print(f"\n  ✓ Raw data saved → {RAW_DATA_PATH}  (shape: {raw.shape})")

    # 2. Clean
    print("\n[2/3] Cleaning...")
    clean = clean_data(raw.copy())
    clean.to_csv(CLEAN_DATA_PATH, index=False)
    print(f"\n  ✓ Clean data saved → {CLEAN_DATA_PATH}")

    # 3. Preview
    print("\n[3/3] Preview (latest year):")
    latest = clean[clean["year"] == clean["year"].max()]
    print(latest.to_string(index=False))

    return clean


if __name__ == "__main__":
    run_pipeline()