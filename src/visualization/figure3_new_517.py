import csv
import os
import pickle
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════
INPUT_DIR = "../enriched"
V1_DIR = "figure_three_v1"
V2_DIR = "figure_three_v2"

CACHE_FILE = "enriched_cache.pkl"   # shared cache — figure 4 can load this too

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
PREFIXES = [("wkdy", "Weekday"), ("wknd", "Weekend")]


def get_data(filepath, prefix):
    if not os.path.exists(filepath):
        return None, None
    exp_acc  = {h: [0.0, 0.0] for h in HOURS}
    dist_acc = {h: [0.0, 0.0] for h in HOURS}
    with open(filepath, newline='') as f:
        for row in csv.DictReader(f):
            for h in HOURS:
                w = row.get(f"{prefix}_{h}")
                if not w or float(w) <= 0:
                    continue
                w = float(w)
                try:
                    e = float(row[f"max_{prefix}_{h}"]) - float(row[f"min_{prefix}_{h}"])
                    d = float(row[f"min_distance_{prefix}_{h}"]) - float(row[f"max_distance_{prefix}_{h}"])
                    exp_acc[h][0]  += w * e;  exp_acc[h][1]  += w
                    dist_acc[h][0] += w * d;  dist_acc[h][1] += w
                except (KeyError, ValueError):
                    continue

    avg_e = [exp_acc[h][0]  / exp_acc[h][1]  if exp_acc[h][1]  > 0 else 0 for h in HOURS]
    avg_d = [dist_acc[h][0] / dist_acc[h][1] if dist_acc[h][1] > 0 else 0 for h in HOURS]
    return avg_e, avg_d


def apply_fixed_y_limits(ax):
    ymin, ymax, step = -100.0, 60.0, 20.0
    ax.set_ylim(ymin, ymax)
    ax.set_yticks(np.arange(ymin, ymax + step / 2, step))


# ══════════════════════════════════════════════════════════════════════════════
#  CACHE
# ══════════════════════════════════════════════════════════════════════════════

def load_or_compute(cache_file):
    if os.path.exists(cache_file):
        print(f"  Loading from cache: {cache_file}", flush=True)
        with open(cache_file, 'rb') as f:
            return pickle.load(f)

    print("  Cache not found — computing from CSVs ...", flush=True)
    # cache structure: { fname: { 'abbr': str, 'wkdy': (we, wd), 'wknd': (ne, nd) } }
    cache = {}
    for fname, abbr in INPUT_FILES.items():
        fpath = os.path.join(INPUT_DIR, fname)
        print(f"    Loading {abbr}...", flush=True)
        we, wd = get_data(fpath, "wkdy")
        ne, nd = get_data(fpath, "wknd")
        if we is None:
            continue
        cache[fname] = {'abbr': abbr, 'wkdy': (we, wd), 'wknd': (ne, nd)}

    with open(cache_file, 'wb') as f:
        pickle.dump(cache, f)
    print(f"  Cache saved: {cache_file}", flush=True)
    return cache


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    os.makedirs(V1_DIR, exist_ok=True)
    os.makedirs(V2_DIR, exist_ok=True)

    cache = load_or_compute(CACHE_FILE)

    for fname, data in cache.items():
        abbr      = data['abbr']
        we, wd    = data['wkdy']
        ne, nd    = data['wknd']
        print(f"Processing {abbr}...", flush=True)

        # ── VERSION 1: Separate Bar Plots ──
        for data_e, data_d, prefix, label in [
            (we, wd, "wkdy", "Weekday"),
            (ne, nd, "wknd", "Weekend"),
        ]:
            fig, ax = plt.subplots(figsize=(12, 10))
            x = np.arange(len(HOURS))
            ax.bar(x,  data_e,           color='#E65100', alpha=0.8, width=0.6)
            ax.bar(x, -np.array(data_d), color='#1565C0', alpha=0.8, width=0.6)
            ax.axhline(0, color='black', linewidth=1)

            apply_fixed_y_limits(ax)
            ax.set_title(abbr, fontsize=50, fontweight='bold', pad=20)
            ax.set_xticks(x - 0.5)
            ax.set_xticklabels([f"{h:02d}:00" for h in HOURS], rotation=45, fontsize=32)
            ax.tick_params(axis='y', labelsize=28)
            ax.set_xlabel("Hour of Day", fontsize=32, labelpad=15)
            ax.set_ylabel("← Extra Dist (m) | Saved Exp →", fontsize=36, labelpad=15)

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
        apply_fixed_y_limits(ax)
        ax.set_title(abbr, fontsize=50, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xlim(0, len(HOURS) - 1)
        ax.set_xticklabels([f"{h:02d}:00" for h in HOURS], rotation=60,
                           ha='right', fontsize=36)
        ax.tick_params(axis='y', labelsize=36)
        ax.set_ylabel("← Extra Dist (m) | Saved Exp →", fontsize=40, labelpad=15)
        ax.legend(fontsize=28, loc='upper right')
        ax.grid(True, alpha=0.2)

        plt.tight_layout()
        plt.savefig(os.path.join(V2_DIR, f"Fig3_Line_{abbr}.png"), dpi=300)
        plt.close()

    print("All Figure 3 plots generated.")