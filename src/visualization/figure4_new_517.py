import os
import pickle
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════
INPUT_DIR = "../enriched"
V1_DIR = "figure_four_v1"
V2_DIR = "figure_four_v2"

# Same cache as figure 3 — run figure_three.py first to build it
CACHE_FILE = "enriched_cache.pkl"

INPUT_FILES = {
    "od_enriched_january.csv":   "January",
    "od_enriched_february.csv":  "February",
    "od_enriched_march.csv":     "March",
    "od_enriched_april.csv":     "April",
    "od_enriched_may.csv":       "May",
    "od_enriched_june.csv":      "June",
    "od_enriched_july.csv":      "July",
    "od_enriched_august.csv":    "August",
    "od_enriched_september.csv": "September",
    "od_enriched_october.csv":   "October",
    "od_enriched_november.csv":  "November",
    "od_enriched_december.csv":  "December",
}

HOURS = list(range(4, 21))

Y_MIN   = -0.4
Y_MAX   =  1.0
Y_TICKS = [-0.4, -0.2, 0.0, 0.2, 0.4, 0.6, 0.8, 1.0]


def get_ratio_data(filepath, prefix):
    """Compute ratio data from CSV — only called if cache missing."""
    import csv
    if not os.path.exists(filepath):
        return None, None
    e_acc = {h: [0., 0.] for h in HOURS}
    d_acc = {h: [0., 0.] for h in HOURS}
    with open(filepath, newline='') as f:
        for row in csv.DictReader(f):
            for h in HOURS:
                w = row.get(f"{prefix}_{h}")
                if not w or float(w) <= 0:
                    continue
                w = float(w)
                try:
                    max_e = float(row[f"max_{prefix}_{h}"])
                    max_d = float(row[f"max_distance_{prefix}_{h}"])
                    if max_e > 0:
                        ratio_e = (max_e - float(row[f"min_{prefix}_{h}"])) / max_e
                        e_acc[h][0] += w * ratio_e
                        e_acc[h][1] += w
                    if max_d > 0:
                        ratio_d = (float(row[f"min_distance_{prefix}_{h}"]) - max_d) / max_d
                        d_acc[h][0] += w * ratio_d
                        d_acc[h][1] += w
                except (KeyError, ValueError):
                    continue
    avg_e = [e_acc[h][0] / e_acc[h][1] if e_acc[h][1] > 0 else 0 for h in HOURS]
    avg_d = [d_acc[h][0] / d_acc[h][1] if d_acc[h][1] > 0 else 0 for h in HOURS]
    return avg_e, avg_d


def pct_abs_formatter(x, pos):
    return '{:,.0%}'.format(abs(x))


def apply_y_limits(ax):
    ax.set_ylim(Y_MIN, Y_MAX)
    ax.set_yticks(Y_TICKS)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(pct_abs_formatter))


def load_or_compute(cache_file):
    """
    Figure 4 uses ratio data, not raw data like figure 3.
    So it has its own cache key 'ratio' inside the same file.
    """
    import csv as _csv

    ratio_cache_file = cache_file.replace('.pkl', '_ratio.pkl')

    if os.path.exists(ratio_cache_file):
        print(f"  Loading ratio cache: {ratio_cache_file}", flush=True)
        with open(ratio_cache_file, 'rb') as f:
            return pickle.load(f)

    print("  Ratio cache not found — computing from CSVs ...", flush=True)
    cache = {}
    for fname, abbr in INPUT_FILES.items():
        fpath = os.path.join(INPUT_DIR, fname)
        print(f"    Loading {abbr}...", flush=True)
        we, wd = get_ratio_data(fpath, "wkdy")
        ne, nd = get_ratio_data(fpath, "wknd")
        if we is None:
            continue
        cache[fname] = {'abbr': abbr, 'wkdy': (we, wd), 'wknd': (ne, nd)}

    with open(ratio_cache_file, 'wb') as f:
        pickle.dump(cache, f)
    print(f"  Ratio cache saved: {ratio_cache_file}", flush=True)
    return cache

def print_ratio_stats(cache):
    """Print key statistics for Fig 4 exposure and distance ratios."""
    
    MONTHS = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    
    for day_type, key in [("Weekday", "wkdy"), ("Weekend", "wknd")]:
        print(f"\n{'═'*80}")
        print(f"  Fig 4 — {day_type} Exposure & Distance Ratio Statistics")
        print(f"{'═'*80}")
        print(f"  {'Month':<12} {'AM Peak %':>10} {'AM Hour':>8} {'PM Peak %':>10} {'PM Hour':>8} "
              f"{'Midday %':>10} {'Max Dist %':>12} {'Avg Dist %':>12}")
        print(f"  {'-'*82}")
        
        for fname, data in cache.items():
            abbr = data['abbr']
            if key == 'wkdy':
                exp_ratios, dist_ratios = data['wkdy']
            else:
                exp_ratios, dist_ratios = data['wknd']
            
            # AM peak — hours 4-9 (index 0-5)
            am_vals = exp_ratios[:6]
            am_peak = max(am_vals)
            am_hour = HOURS[am_vals.index(am_peak)]
            
            # PM peak — hours 13-20 (index 9-16)
            pm_vals = exp_ratios[9:]
            pm_peak = max(pm_vals)
            pm_hour = HOURS[9 + pm_vals.index(pm_peak)]
            
            # Midday trough — hours 10-12 (index 6-8)
            mid_vals = exp_ratios[6:9]
            mid_trough = min(mid_vals)
            
            # Distance ratio stats
            max_dist = max(dist_ratios)
            avg_dist = sum(dist_ratios) / len([d for d in dist_ratios if d > 0]) if any(d > 0 for d in dist_ratios) else 0
            
            print(f"  {abbr:<12} "
                  f"{am_peak:>9.1%} "
                  f"{am_hour:>8} "
                  f"{pm_peak:>9.1%} "
                  f"{pm_hour:>8} "
                  f"{mid_trough:>9.1%} "
                  f"{max_dist:>11.1%} "
                  f"{avg_dist:>11.1%}")
    
    # Summary — seasonal comparison
    print(f"\n{'═'*80}")
    print(f"  Seasonal Summary — Weekday AM Peak vs PM Peak")
    print(f"{'═'*80}")
    print(f"  {'Month':<12} {'AM Peak':>10} {'PM Peak':>10} {'AM/PM Ratio':>12} {'Max Dist':>10}")
    print(f"  {'-'*56}")
    
    for fname, data in cache.items():
        abbr = data['abbr']
        we, wd = data['wkdy']
        am_peak = max(we[:6])
        pm_peak = max(we[9:])
        ratio = am_peak / pm_peak if pm_peak > 0 else 0
        max_dist = max(wd)
        print(f"  {abbr:<12} "
              f"{am_peak:>9.1%} "
              f"{pm_peak:>9.1%} "
              f"{ratio:>11.2f}x "
              f"{max_dist:>9.1%}")

if __name__ == "__main__":
    os.makedirs(V1_DIR, exist_ok=True)
    os.makedirs(V2_DIR, exist_ok=True)

    cache = load_or_compute(CACHE_FILE)

    import csv

    for fname, label in INPUT_FILES.items():
        fpath = os.path.join(INPUT_DIR, fname)
        if not os.path.exists(fpath):
            print(f"{label}: FILE NOT FOUND")
            continue
        print(f"\n=== {label} ===")
        for prefix in ["wkdy", "wknd"]:
            weight_sums = {h: 0. for h in HOURS}
            with open(fpath, newline='') as f:
                for row in csv.DictReader(f):
                    for h in HOURS:
                        w = row.get(f"{prefix}_{h}")
                        if not w or float(w) <= 0:
                            continue
                        weight_sums[h] += float(w)
            print(f"  {prefix}: { {h: f'{weight_sums[h]:,.0f}' for h in HOURS} }")

    for fname, data in cache.items():
        abbr   = data['abbr']
        we, wd = data['wkdy']
        ne, nd = data['wknd']
        print(f"Processing {abbr}...", flush=True)

        # ── VERSION 1: Separate Bar Plots ──
        for data_e, data_d, prefix, label in [
            (we, wd, "wkdy", "Weekday"),
            (ne, nd, "wknd", "Weekend"),
        ]:
            fig, ax = plt.subplots(figsize=(12, 9))
            x = np.arange(len(HOURS))
            ax.bar(x,  data_e,           color='#E65100', alpha=0.8, width=0.6)
            ax.bar(x, -np.array(data_d), color='#1565C0', alpha=0.8, width=0.6)
            ax.axhline(0, color='black', linewidth=1)

            apply_y_limits(ax)
            ax.set_title(abbr, fontsize=50, fontweight='bold', pad=20)
            ax.set_xticks(x - 0.5)
            ax.set_xticklabels([f"{h:02d}:00" for h in HOURS], rotation=45, fontsize=40)
            ax.tick_params(axis='y', labelsize=40)
            # ax.set_xlabel("Hour of Day", fontsize=32, labelpad=15)
            ax.set_ylabel("← Dist Ratio | Exp Ratio →", fontsize=50, labelpad=15)

            plt.tight_layout()
            plt.savefig(os.path.join(V1_DIR, f"{abbr}_{prefix}.png"), dpi=300)
            plt.close()

        # ── VERSION 2: Combined Line Plot ──
        fig, ax = plt.subplots(figsize=(20, 12))
        x = np.arange(len(HOURS))

        ax.plot(x,  we,           color='orange',   label='Weekday Exp', linewidth=5, marker='o', markersize=12)
        ax.plot(x,  ne,           color='red',      label='Weekend Exp',  linewidth=5, marker='o', markersize=12)
        ax.plot(x, -np.array(wd), color='skyblue',  label='Weekday Dist', linewidth=5, marker='s', markersize=12)
        ax.plot(x, -np.array(nd), color='darkblue', label='Weekend Dist', linewidth=5, marker='s', markersize=12)

        ax.fill_between(x,  we,           0, color='orange',   alpha=0.15)
        ax.fill_between(x,  ne,           0, color='red',      alpha=0.15)
        ax.fill_between(x, -np.array(wd), 0, color='skyblue',  alpha=0.15)
        ax.fill_between(x, -np.array(nd), 0, color='darkblue', alpha=0.15)

        ax.axhline(0, color='black', linewidth=1.5)
        apply_y_limits(ax)
        ax.set_title(abbr, fontsize=64, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xlim(0, len(HOURS) - 1)
        ax.set_xticklabels([f"{h:02d}:00" for h in HOURS], rotation=60,
                           ha='right', fontsize=40)
        ax.tick_params(axis='y', labelsize=40)
        # ax.set_xlabel("Hour of Day", fontsize=36, labelpad=15)
        ax.set_ylabel("← Dist Ratio | Exp Ratio →", fontsize=50, labelpad=15)
        ax.legend(fontsize=38, loc='upper right')
        ax.grid(True, alpha=0.2)

        plt.tight_layout()
        plt.savefig(os.path.join(V2_DIR, f"Fig4_Line_{abbr}.png"), dpi=300)
        plt.close()

    print("Done.")
    print_ratio_stats(cache)