#!/usr/bin/env python3
"""
generate_solar_data.py — Generate solar position data (azimuth + apparent elevation)
at 1-minute intervals for every minute of the year, using pvlib.

Outputs binary files directly into Assets/StreamingAssets/SolarData/<City>/sun_pos_YYYY.bin
matching the format consumed by SolarDataLoader.cs (see SolarDataPreprocessor.cs for spec).

Optionally also writes the intermediate CSV into Assets/Resources/SolarData/<City>/.

Binary format (little-endian):
  Header  16 bytes: magic "SLRD"(4) + version(int16) + year(int16)
                    + totalMinutes(int32) + reserved(int32)
  Data    N×8 bytes: azimuth(float32) + elevation(float32) per minute
  Index:  (dayOfYear-1) × 1440 + minuteOfDay

Usage:
  python generate_solar_data.py                          # all cities, current year
  python generate_solar_data.py --cities Manhattan       # one city
  python generate_solar_data.py --cities all --years 2026 2027
  python generate_solar_data.py --years 2025 2026 --csv  # also keep CSV files

City definitions live in the Cities dict below.
"""

import argparse
import calendar
import os
import struct
import sys
import time

import numpy as np
import pandas as pd
import pvlib

Cities = {
    "Manhattan": {
        "latitude": 40.7826,
        "longitude": -73.9656,
        "altitude": 33, # Meters
        "timezone": "America/New_York"
    }
}


# ---------------------------------------------------------------------------
# Paths (relative to this script, which lives at project root)
# ---------------------------------------------------------------------------
SCRIPT_DIR       = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR       = os.path.join(SCRIPT_DIR, "Assets")
RESOURCES_DIR    = os.path.join(ASSETS_DIR, "Resources", "SolarData")
STREAMING_DIR    = os.path.join(ASSETS_DIR, "StreamingAssets", "SolarData")

# Binary format constants (must match SolarDataPreprocessor.cs / SolarDataLoader.cs)
MAGIC            = b"SLRD"
VERSION          = 1
MINUTES_PER_DAY  = 1440


# ---------------------------------------------------------------------------
# Core: compute solar positions for an entire year at 1-min resolution
# ---------------------------------------------------------------------------
def compute_solar_positions(latitude: float, longitude: float,
                            altitude: float, timezone: str,
                            year: int) -> pd.DataFrame:
    """
    Return a DataFrame with columns ['azimuth', 'apparent_elevation']
    indexed by timezone-aware DatetimeIndex at 1-minute frequency for the
    full calendar year.  The index format matches the existing CSV convention:
        "2026-01-01 00:00:00-05:00"
    """
    # Build a full-year 1-minute DatetimeIndex in the city's local timezone.
    start = pd.Timestamp(f"{year}-01-01", tz=timezone)
    end   = pd.Timestamp(f"{year}-12-31 23:59:00", tz=timezone)
    times = pd.date_range(start, end, freq="1min")

    print(f"    Computing {len(times):,} sun positions …", end=" ", flush=True)
    t0 = time.time()

    # pvlib.solarposition.get_solarposition returns many columns;
    # we only need 'azimuth' and 'apparent_elevation'.
    solpos = pvlib.solarposition.get_solarposition(
        times, latitude, longitude, altitude=altitude,
        method="nrel_numpy"  # fast vectorised NREL SPA implementation
    )

    elapsed = time.time() - t0
    print(f"done in {elapsed:.1f}s")

    return solpos[["azimuth", "apparent_elevation"]]


# ---------------------------------------------------------------------------
# Binary writer (mirrors SolarDataPreprocessor.ConvertCsvToBinary)
# ---------------------------------------------------------------------------
def write_binary(df: pd.DataFrame, path: str, year: int) -> int:
    """
    Write the DataFrame to a binary file matching the Unity loader format.
    Returns the number of entries written.
    """
    is_leap = calendar.isleap(year)
    expected_minutes = (366 if is_leap else 365) * MINUTES_PER_DAY

    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "wb") as f:
        # --- Header (16 bytes) ---
        f.write(MAGIC)                                          # 4 bytes
        f.write(struct.pack("<h", VERSION))                     # int16
        f.write(struct.pack("<h", year))                        # int16
        f.write(struct.pack("<i", expected_minutes))            # int32
        f.write(struct.pack("<i", 0))                           # reserved int32

        # --- Data: azimuth(f32) + elevation(f32) per minute ---
        azimuths   = df["azimuth"].values.astype(np.float32)
        elevations = df["apparent_elevation"].values.astype(np.float32)

        # Interleave into [az0, el0, az1, el1, …] and write in one shot
        interleaved = np.empty(len(azimuths) * 2, dtype=np.float32)
        interleaved[0::2] = azimuths
        interleaved[1::2] = elevations
        f.write(interleaved.tobytes())

    count = len(df)
    if count != expected_minutes:
        print(f"    ⚠  Expected {expected_minutes:,} rows but got {count:,}. "
              "File may be incomplete.")
    return count


# ---------------------------------------------------------------------------
# Optional CSV writer (same format the C# preprocessor expects)
# ---------------------------------------------------------------------------
def write_csv(df: pd.DataFrame, path: str) -> None:
    """
    Write a CSV identical in format to the existing sun_pos_YYYY.csv files.
    Header: ,azimuth,apparent_elevation
    Rows:   <tz-aware datetime>,<azimuth>,<apparent_elevation>
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path)  # index=True gives the datetime as first column


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate solar position data for Unity SunPath simulation."
    )
    p.add_argument(
        "--cities", nargs="+", default=["all"],
        help='City names from data_script.py, or "all" (default: all).'
    )
    p.add_argument(
        "--years", nargs="+", type=int,
        default=[pd.Timestamp.now().year],
        help="Year(s) to generate (default: current year)."
    )
    p.add_argument(
        "--csv", action="store_true",
        help="Also write CSV files into Resources/SolarData/<City>/. "
             "By default only binary files are written."
    )
    return p.parse_args()


def resolve_cities(requested: list[str]) -> dict:
    """Return the subset of Cities matching the request, or all."""
    if "all" in [c.lower() for c in requested]:
        return Cities

    selected = {}
    for name in requested:
        # Case-insensitive lookup
        match = {k: v for k, v in Cities.items() if k.lower() == name.lower()}
        if not match:
            print(f"⚠  Unknown city '{name}'. Available: {', '.join(Cities.keys())}")
            sys.exit(1)
        selected.update(match)
    return selected


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    args = parse_args()
    cities = resolve_cities(args.cities)
    years  = args.years

    print(f"Cities : {', '.join(cities.keys())}")
    print(f"Years  : {', '.join(str(y) for y in years)}")
    print(f"Output : binary → {STREAMING_DIR}")
    if args.csv:
        print(f"         csv    → {RESOURCES_DIR}")
    print()

    total_files = 0

    for city_name, info in cities.items():
        for year in years:
            print(f"  [{city_name} {year}]")

            df = compute_solar_positions(
                latitude  = info["latitude"],
                longitude = info["longitude"],
                altitude  = info["altitude"],
                timezone  = info["timezone"],
                year      = year,
            )

            # --- Binary (always) ---
            bin_path = os.path.join(STREAMING_DIR, city_name, f"sun_pos_{year}.bin")
            n = write_binary(df, bin_path, year)
            size_mb = os.path.getsize(bin_path) / (1024 * 1024)
            print(f"    Binary: {n:,} entries → {bin_path}  ({size_mb:.1f} MB)")

            # --- CSV (optional) ---
            if args.csv:
                csv_path = os.path.join(RESOURCES_DIR, city_name, f"sun_pos_{year}.csv")
                write_csv(df, csv_path)
                csv_mb = os.path.getsize(csv_path) / (1024 * 1024)
                print(f"    CSV:    {csv_path}  ({csv_mb:.1f} MB)")

            total_files += 1

    print(f"\nDone. Generated {total_files} binary file(s).")


if __name__ == "__main__":
    main()
