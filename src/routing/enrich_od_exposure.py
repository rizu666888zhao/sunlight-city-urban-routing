"""
Enrich OD CSV with min/max exposure AND min/max distance per hour by looking up pareto CSVs.
Processes multiple month directories and outputs a separate enriched CSV per month.
"""

import csv
import os
import glob
from collections import defaultdict

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

INPUT_CSV  = "od_all_hourly_unity_filtered.csv"
OUTPUT_DIR = "enriched"

PARETO_DIRS = {
    "jan":    "january",
    "feb":    "february",
    "march":  "march",
    "april":  "april",
    "may":    "may",
    "june":   "june",
    "july2":  "july",
    "august": "august",
    "sept":   "september",
    "oct":    "october",
    "nov":    "november",
    "dec":    "december",
}

HOUR_START = 3
HOUR_END   = 20

# ══════════════════════════════════════════════════════════════════════════════
#  Pareto filename helper
# ══════════════════════════════════════════════════════════════════════════════

def wp_csv_path(pareto_dir, source_wp, target_wp, run_date):
    src = str(source_wp).replace('-', '_')
    tgt = str(target_wp).replace('-', '_')
    return os.path.join(pareto_dir, f"pareto_{src}--{tgt}--{run_date}.csv")

# ══════════════════════════════════════════════════════════════════════════════
#  Load pareto exposure AND distance for a waypoint pair
#  Returns dict: start_time_min -> (max_exposure, min_exposure, max_dist, min_dist)
#  rank 1       = shortest duration = highest exposure = shortest distance
#  last rank    = longest duration  = lowest exposure  = longest distance
# ══════════════════════════════════════════════════════════════════════════════

def load_pareto_data(pareto_dir, source_wp, target_wp, run_date):
    fpath = wp_csv_path(pareto_dir, source_wp, target_wp, run_date)
    if not os.path.exists(fpath):
        return {}

    by_time = defaultdict(list)
    with open(fpath, newline='') as f:
        for row in csv.DictReader(f):
            st     = int(row['start_time_min'])
            rank   = int(row['rank'])
            exp    = float(row['exposure'])
            length = float(row['length_m'])
            by_time[st].append((rank, exp, length))

    result = {}
    for st, entries in by_time.items():
        entries.sort(key=lambda x: x[0])
        max_exp  = entries[0][1]   # rank 1 = shortest = max exposure
        max_dist = entries[0][2]   # rank 1 = shortest route distance
        min_exp  = entries[-1][1]  # last rank = shadiest = min exposure
        min_dist = entries[-1][2]  # last rank = shadiest route distance
        result[st] = (max_exp, min_exp, max_dist, min_dist)
    return result

# ══════════════════════════════════════════════════════════════════════════════
#  Process one month directory -> one output CSV
# ══════════════════════════════════════════════════════════════════════════════

def process_month(pareto_dir, month_name, rows, fieldnames, hours, new_cols):
    sample_files = glob.glob(os.path.join(pareto_dir, "pareto_*.csv"))
    if not sample_files:
        print(f"  [SKIP] No pareto CSV files found in '{pareto_dir}'")
        return

    sample_date = os.path.basename(sample_files[0]).rsplit('--', 1)[-1].replace('.csv', '')

    print(f"\n{'═'*60}")
    print(f"  Month : {month_name}  |  Folder: {pareto_dir}  |  Date: {sample_date}")
    print(f"{'═'*60}")

    pareto_cache = {}
    out_rows     = []
    missing      = 0

    for i, row in enumerate(rows):
        src = row['source_wp']
        tgt = row['target_wp']
        key = (src, tgt)

        if key not in pareto_cache:
            pareto_cache[key] = load_pareto_data(pareto_dir, src, tgt, sample_date)

        data = pareto_cache[key]
        if not data:
            missing += 1

        out_row = dict(row)
        for prefix in ['wkdy', 'wknd']:
            for h in hours:
                st = h * 60
                if st in data:
                    max_exp, min_exp, max_dist, min_dist = data[st]
                else:
                    max_exp = min_exp = max_dist = min_dist = ''

                out_row[f"min_{prefix}_{h}"]          = round(min_exp,  4) if min_exp  != '' else ''
                out_row[f"max_{prefix}_{h}"]          = round(max_exp,  4) if max_exp  != '' else ''
                out_row[f"max_distance_{prefix}_{h}"] = round(max_dist, 4) if max_dist != '' else ''
                out_row[f"min_distance_{prefix}_{h}"] = round(min_dist, 4) if min_dist != '' else ''

        out_rows.append(out_row)

        if (i + 1) % 50_000 == 0 or (i + 1) == len(rows):
            print(f"  {i+1:,} / {len(rows):,} rows done  (cache: {len(pareto_cache):,})", flush=True)

    print(f"  Missing pareto files: {missing:,} rows")

    output_csv = os.path.join(OUTPUT_DIR, f"od_enriched_{month_name}.csv")
    with open(output_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames) + new_cols)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"  Saved: {output_csv}  ({len(out_rows):,} rows, {len(new_cols)} new columns)")

# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    hours    = list(range(HOUR_START, HOUR_END + 1))
    new_cols = []
    for prefix in ['wkdy', 'wknd']:
        for h in hours:
            new_cols.append(f"min_{prefix}_{h}")
            new_cols.append(f"max_{prefix}_{h}")
            new_cols.append(f"max_distance_{prefix}_{h}")
            new_cols.append(f"min_distance_{prefix}_{h}")

    print(f"\n{'═'*60}")
    print(f"  Reading {INPUT_CSV}...")
    print(f"{'═'*60}")

    with open(INPUT_CSV, newline='') as f:
        reader     = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows       = list(reader)

    print(f"  Loaded {len(rows):,} rows")

    for pareto_dir, month_name in PARETO_DIRS.items():
        process_month(pareto_dir, month_name, rows, fieldnames, hours, new_cols)

    print(f"\n{'═'*60}")
    print(f"  All done. Outputs in: ./{OUTPUT_DIR}/")
    print(f"{'═'*60}\n")