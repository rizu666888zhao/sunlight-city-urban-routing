"""
Plot 2: Monthly pedestrian flow exposure box plot
2 plots: shortest route and shadiest route
Weight = (5 × weekday + 2 × weekend) / 7
"""

import csv
import os
import pickle
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

INPUT_DIR  = "../enriched"
PLOT_DIR   = "figure_two_fix_one"
CACHE_FILE = "figure_two_cache.pkl"

INPUT_FILES = {
    "od_enriched_january.csv":   "Jan",
    "od_enriched_february.csv":  "Feb",
    "od_enriched_march.csv":     "Mar",
    "od_enriched_april.csv":     "Apr",
    "od_enriched_may.csv":       "May",
    "od_enriched_june.csv":      "Jun",
    "od_enriched_july.csv":      "Jul",
    "od_enriched_august.csv":    "Aug",
    "od_enriched_september.csv": "Sep",
    "od_enriched_october.csv":   "Oct",
    "od_enriched_november.csv":  "Nov",
    "od_enriched_december.csv":  "Dec",
}

HOUR_START = 5
HOUR_END   = 19
HOURS      = list(range(HOUR_START, HOUR_END + 1))

SUBPLOTS = [
    {
        "exp_type":   "max",
        "title":      "Shortest route (max exposure) — weighted average day",
        "filename":   "figure2_shortest.png",
        "fill_rgb":   (0.98, 0.90, 0.87),
        "border_hex": "#BF360C",
        "median_hex": "#BF360C",
    },
    {
        "exp_type":   "min",
        "title":      "Shadiest route (min exposure) — weighted average day",
        "filename":   "figure2_shadiest.png",
        "fill_rgb":   (0.88, 0.92, 0.98),
        "border_hex": "#0D47A1",
        "median_hex": "#0D47A1",
    },
]

# ══════════════════════════════════════════════════════════════════════════════
#  WEIGHTED PERCENTILE
# ══════════════════════════════════════════════════════════════════════════════

def weighted_percentile(values, weights, perc):
    values  = np.array(values,  dtype=float)
    weights = np.array(weights, dtype=float)
    sorter  = np.argsort(values)
    values  = values[sorter]
    weights = weights[sorter]
    cumsum  = np.cumsum(weights)
    cutoff  = cumsum[-1] * perc / 100.0
    idx     = np.searchsorted(cumsum, cutoff)
    idx     = min(idx, len(values) - 1)
    return float(values[idx])

# ══════════════════════════════════════════════════════════════════════════════
#  LOAD ONE MONTH
# ══════════════════════════════════════════════════════════════════════════════

def load_month(filepath, exp_type):
    values  = []
    weights = []

    if not os.path.exists(filepath):
        print(f"  [SKIP] Not found: {filepath}")
        return values, weights

    row_count = 0
    with open(filepath, newline='') as f:
        for row in csv.DictReader(f):
            for h in HOURS:
                wkdy = float(row[f"wkdy_{h}"])
                wknd = float(row[f"wknd_{h}"])
                w    = (5 * wkdy + 2 * wknd) / 7.0
                if w <= 0:
                    continue

                wkdy_e = float(row[f"{exp_type}_wkdy_{h}"])
                wknd_e = float(row[f"{exp_type}_wknd_{h}"])
                e      = (5 * wkdy * wkdy_e + 2 * wknd * wknd_e) / (5 * wkdy + 2 * wknd)

                values.append(e)
                weights.append(w)

            row_count += 1
            if row_count % 100_000 == 0:
                print(f"    {row_count:,} rows...", flush=True)

    print(f"    {row_count:,} rows → {len(values):,} valid trip-hour points")
    return values, weights

# ══════════════════════════════════════════════════════════════════════════════
#  CACHE
# ══════════════════════════════════════════════════════════════════════════════

def load_or_compute(cache_file):
    if os.path.exists(cache_file):
        print(f"  Loading from cache: {cache_file}", flush=True)
        with open(cache_file, 'rb') as f:
            return pickle.load(f)

    print("  Cache not found — computing from CSVs ...", flush=True)
    # cache structure:
    # { fname: { 'month': str, 'max': (values, weights), 'min': (values, weights) } }
    cache = {}
    for fname, month in INPUT_FILES.items():
        fpath = os.path.join(INPUT_DIR, fname)
        print(f"\n  {month}:", flush=True)
        max_v, max_w = load_month(fpath, "max")
        min_v, min_w = load_month(fpath, "min")
        cache[fname] = {
            'month': month,
            'max':   (max_v, max_w),
            'min':   (min_v, min_w),
        }

    with open(cache_file, 'wb') as f:
        pickle.dump(cache, f)
    print(f"\n  Cache saved: {cache_file}", flush=True)
    return cache

# ══════════════════════════════════════════════════════════════════════════════
#  COMPUTE BOX STATS
# ══════════════════════════════════════════════════════════════════════════════

def compute_box_stats(values, weights):
    if not values:
        return None
    return {
        'whislo': weighted_percentile(values, weights,  5),
        'q1':     weighted_percentile(values, weights, 25),
        'med':    weighted_percentile(values, weights, 50),
        'q3':     weighted_percentile(values, weights, 75),
        'whishi': weighted_percentile(values, weights, 95),
        'fliers': [],
    }

# ADD this function to your script (paste after compute_box_stats)

def print_stats(cfg, cache):
    """Print weighted percentile stats for each month."""
    print(f"\n{'═'*60}")
    print(f"  Stats for: {cfg['title']}")
    print(f"{'═'*60}")
    print(f"  {'Month':<8} {'P5':>8} {'Q1':>8} {'Median':>8} {'Q3':>8} {'P95':>8}")
    print(f"  {'-'*48}")

    for fname, data in cache.items():
        month = data['month']
        values, weights = data[cfg['exp_type']]
        stats = compute_box_stats(values, weights)
        if stats:
            print(f"  {month:<8} "
                  f"{stats['whislo']:>8.1f} "
                  f"{stats['q1']:>8.1f} "
                  f"{stats['med']:>8.1f} "
                  f"{stats['q3']:>8.1f} "
                  f"{stats['whishi']:>8.1f}")
        else:
            print(f"  {month:<8} {'NO DATA':>8}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  PLOT
# ══════════════════════════════════════════════════════════════════════════════

def plot_combined(cache):
    all_boxes_max = []
    all_boxes_min = []
    positions_max = []
    positions_min = []
    valid_labels  = []

    for i, (fname, data) in enumerate(cache.items()):
        month = data['month']
        max_v, max_w = data['max']
        min_v, min_w = data['min']
        stats_max = compute_box_stats(max_v, max_w)
        stats_min = compute_box_stats(min_v, min_w)
        if stats_max and stats_min:
            all_boxes_max.append(stats_max)
            all_boxes_min.append(stats_min)
            positions_max.append(i * 2.2)
            positions_min.append(i * 2.2 + 0.8)
            valid_labels.append(month)

    fig, ax = plt.subplots(figsize=(12, 8))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')

    bp_max = ax.bxp(all_boxes_max, positions=positions_max, showfliers=False,
                    showmeans=False, widths=0.6, patch_artist=True,
                    boxprops=dict(facecolor=(0.98, 0.90, 0.87), color='#BF360C', linewidth=1.8),
                    medianprops=dict(color='#BF360C', linewidth=3.5, solid_capstyle='butt'),
                    whiskerprops=dict(color='#BF360C', linewidth=1.2, linestyle='-'),
                    capprops=dict(color='#BF360C', linewidth=1.8))
    for patch in bp_max['boxes']:
        patch.set_facecolor((0.98, 0.90, 0.87))
        patch.set_alpha(1.0)

    bp_min = ax.bxp(all_boxes_min, positions=positions_min, showfliers=False,
                    showmeans=False, widths=0.6, patch_artist=True,
                    boxprops=dict(facecolor=(0.88, 0.92, 0.98), color='#0D47A1', linewidth=1.8),
                    medianprops=dict(color='#0D47A1', linewidth=3.5, solid_capstyle='butt'),
                    whiskerprops=dict(color='#0D47A1', linewidth=1.2, linestyle='-'),
                    capprops=dict(color='#0D47A1', linewidth=1.8))
    for patch in bp_min['boxes']:
        patch.set_facecolor((0.88, 0.92, 0.98))
        patch.set_alpha(1.0)

    tick_positions = [i * 2.2 + 0.4 for i in range(len(valid_labels))]
    ax.set_xlim(-0.5, len(valid_labels) * 2.2+0.3)
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(valid_labels, rotation=0, ha='center', fontsize=24)
    # ax.set_xlim(-0.5, len(valid_labels) * 1.6 - 0.5)

    ax.set_ylabel("Exposed cells per trip", fontsize=32)
    ax.tick_params(axis='y', labelsize=24)
    ax.tick_params(axis='x', labelsize=24)
    ax.grid(axis='y', alpha=0.25, linewidth=0.7, color='#aaaaaa')
    ax.set_ylim(bottom=-5, top=400)
    ax.set_yticks(np.arange(0, 401, 50))
    ax.set_axisbelow(True)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_edgecolor('#cccccc')
    ax.spines['bottom'].set_edgecolor('#cccccc')

    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(facecolor=(0.98, 0.90, 0.87), edgecolor='#BF360C', label='Shortest route'),
        Patch(facecolor=(0.88, 0.92, 0.98), edgecolor='#0D47A1', label='Shadiest route'),
    ], fontsize=26)

    plt.tight_layout()
    out_path = os.path.join(PLOT_DIR, "figure2_combined.png")
    plt.savefig(out_path, dpi=300, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f"\n  Saved: {out_path}")

if __name__ == "__main__":
    os.makedirs(PLOT_DIR, exist_ok=True)
    cache = load_or_compute(CACHE_FILE)
    plot_combined(cache)
    for cfg in SUBPLOTS:
        print_stats(cfg, cache)
    print(f"\n{'═'*60}")
    print(f"  All done. Saved to ./{PLOT_DIR}/")
    print(f"{'═'*60}\n")