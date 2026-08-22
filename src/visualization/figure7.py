"""
Plot 7 — Monthly pedestrian flow exposure by OD type
======================================================
BAR VERSION v3  — 12 plots (one per month), 4 bars per OD type
LINE VERSION    — 12 plots (one per month), 4 lines
PIE VERSION v4  — 4 separate files, one per condition
PIE LEGEND      — separate horizontal legend file

Output structure
----------------
  figure_seven/
    cache.json
    bar/v3/plot7_bar_v3_january.png  ...
    line/plot7_line_january.png  ...
    pie/plot7_pie_weekday_max.png
    pie/plot7_pie_weekday_min.png
    pie/plot7_pie_weekend_max.png
    pie/plot7_pie_weekend_min.png
    pie/plot7_pie_legend.png
    legend_labels.png
"""

import csv
import json
import math
import os
from collections import defaultdict

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker
import numpy as np

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

ENRICHED_DIR = "../enriched"
OD_UNITY_CSV = "../od_all_hourly_unity_filtered.csv"
OD_TYPE_CSV  = "../od_type.csv"
PLOT_DIR     = "figure_seven"
CACHE_FILE   = os.path.join(PLOT_DIR, "cache.json")

HOUR_START = 4
HOUR_END   = 20

DP_EXACT  = 6
DP_APPROX = 4

MONTHS = [
    "january","february","march","april","may","june",
    "july","august","september","october","november","december",
]

C_MAX_WKDY = "#FF7F0E"
C_MAX_WKND = "#D62728"
C_MIN_WKDY = "#64B5F6"
C_MIN_WKND = "#1565C0"

BAR_ALPHA = 0.85
FIG_BG    = "white"

TITLE_FS  = 48
YLABEL_FS = 36
TICK_FS   = 30
LEGEND_FS = 32
XTICK_FS  = 30
XTICK_ROT = 20

OD_LABEL_MAP = {
    "amenities_to_amenities": "Amen→Amen",
    "amenities_to_metro":     "Amen→Metro",
    "homes_to_amenities":     "Home→Amen",
    "homes_to_jobs":          "Home→Jobs",
    "homes_to_metro":         "Home→Metro",
    "homes_to_parks":         "Home→Parks",
    "homes_to_schools":       "Home→School",
    "jobs_to_amenities":      "Jobs→Amen",
    "jobs_to_metro":          "Jobs→Metro",
    "parks_to_metro":         "Parks→Metro",
}

PIE_COLORS = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
]

def short_label(t):
    return OD_LABEL_MAP.get(t, t.replace("_", " "))


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 1 — Build lookup structures
# ══════════════════════════════════════════════════════════════════════════════

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    p = math.pi / 180
    a = (math.sin((lat2-lat1)*p/2)**2 +
         math.cos(lat1*p) * math.cos(lat2*p) *
         math.sin((lon2-lon1)*p/2)**2)
    return 2 * R * math.asin(math.sqrt(a))


def load_od_lookups(od_type_csv):
    exact_map = {}
    by_origin = defaultdict(list)
    by_dest   = defaultdict(list)

    if not os.path.exists(od_type_csv):
        print(f"WARNING: {od_type_csv} not found")
        return exact_map, by_origin, by_dest

    with open(od_type_csv, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                olat = float(row["origin_lat"]); olon = float(row["origin_lon"])
                dlat = float(row["dest_lat"]);   dlon = float(row["dest_lon"])
                od_t = row["od_type"].strip()
            except (KeyError, ValueError):
                continue
            exact_key = (round(olat, DP_EXACT), round(olon, DP_EXACT),
                         round(dlat, DP_EXACT), round(dlon, DP_EXACT))
            exact_map[exact_key] = od_t
            e = (olat, olon, dlat, dlon, od_t)
            by_origin[(round(olat, DP_APPROX), round(olon, DP_APPROX))].append(e)
            by_dest[(round(dlat, DP_APPROX), round(dlon, DP_APPROX))].append(e)

    print(f"  od_type.csv -> {len(exact_map):,} exact | "
          f"{len(by_origin):,} origin groups | {len(by_dest):,} dest groups")
    return exact_map, by_origin, by_dest


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 2 — Process one month
# ══════════════════════════════════════════════════════════════════════════════

def process_month(enriched_path, unity_csv, exact_map, by_origin, by_dest, hours):
    acc = {
        'wkdy': defaultdict(lambda: {'max': 0.0, 'min': 0.0}),
        'wknd': defaultdict(lambda: {'max': 0.0, 'min': 0.0}),
    }

    if not os.path.exists(enriched_path):
        print(f"  MISSING: {enriched_path}")
        return {'wkdy': {}, 'wknd': {}}

    row_count = unknown_count = 0
    level_counts = [0, 0, 0]

    with open(unity_csv,     newline='', encoding='utf-8') as fu, \
         open(enriched_path, newline='', encoding='utf-8') as fe:

        for u_row, e_row in zip(csv.DictReader(fu), csv.DictReader(fe)):
            try:
                olat = float(u_row["origin_lat"]); olon = float(u_row["origin_lon"])
                dlat = float(u_row["dest_lat"]);   dlon = float(u_row["dest_lon"])
            except (KeyError, ValueError):
                unknown_count += 1
                continue

            key = (round(olat, DP_EXACT), round(olon, DP_EXACT),
                   round(dlat, DP_EXACT), round(dlon, DP_EXACT))
            if key in exact_map:
                od_type = exact_map[key]; level_counts[0] += 1
            elif (round(olat, DP_APPROX), round(olon, DP_APPROX)) in by_origin:
                candidates = by_origin[(round(olat, DP_APPROX), round(olon, DP_APPROX))]
                od_type = min(candidates, key=lambda e: haversine(dlat, dlon, e[2], e[3]))[4]
                level_counts[1] += 1
            elif (round(dlat, DP_APPROX), round(dlon, DP_APPROX)) in by_dest:
                candidates = by_dest[(round(dlat, DP_APPROX), round(dlon, DP_APPROX))]
                od_type = min(candidates, key=lambda e: haversine(olat, olon, e[0], e[1]))[4]
                level_counts[2] += 1
            else:
                od_type = "unknown"; unknown_count += 1

            for prefix in ['wkdy', 'wknd']:
                for h in hours:
                    w_str   = e_row.get(f"{prefix}_{h}", "")
                    max_str = e_row.get(f"max_{prefix}_{h}", "")
                    min_str = e_row.get(f"min_{prefix}_{h}", "")
                    if not w_str or not max_str:
                        continue
                    try:
                        w  = float(w_str)
                        mx = float(max_str)
                        mn = float(min_str) if min_str else mx
                    except ValueError:
                        continue
                    if w <= 0:
                        continue
                    acc[prefix][od_type]['max'] += w * mx
                    acc[prefix][od_type]['min'] += w * mn

            row_count += 1
            if row_count % 200_000 == 0:
                print(f"    {row_count:,} rows...", flush=True)

    result = {'wkdy': dict(acc['wkdy']), 'wknd': dict(acc['wknd'])}
    print(f"    {row_count:,} rows | exact={level_counts[0]:,} "
          f"by_origin={level_counts[1]:,} by_dest={level_counts[2]:,} "
          f"unknown={unknown_count:,} | {len(result['wkdy'])} OD categories")
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 3 — Build / load matrix (with cache)
# ══════════════════════════════════════════════════════════════════════════════

def build_matrix(exact_map, by_origin, by_dest, hours):
    if os.path.exists(CACHE_FILE):
        print(f"Loading cache from {CACHE_FILE}...")
        with open(CACHE_FILE, encoding='utf-8') as f:
            cache = json.load(f)
        print(f"  Loaded {len(cache['monthly_data'])} months, "
              f"{len(cache['all_od_types'])} OD types")
        return cache["monthly_data"], cache["all_od_types"]

    monthly_data     = []
    all_od_types_set = set()

    for month_name in MONTHS:
        enriched_path = os.path.join(ENRICHED_DIR, f"od_enriched_{month_name}.csv")
        print(f"Processing {month_name}...")
        result = process_month(enriched_path, OD_UNITY_CSV,
                               exact_map, by_origin, by_dest, hours)
        monthly_data.append(result)
        for prefix in ['wkdy', 'wknd']:
            all_od_types_set.update(result[prefix].keys())

    all_od_types = sorted(t for t in all_od_types_set if t != "unknown")

    os.makedirs(PLOT_DIR, exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump({"monthly_data": monthly_data, "all_od_types": all_od_types}, f)
    print(f"  Cached to {CACHE_FILE}")
    return monthly_data, all_od_types


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 4 — Global y-axis max
# ══════════════════════════════════════════════════════════════════════════════

def compute_global_ymax(monthly_data, all_od_types):
    global_max = 0.0
    for result in monthly_data:
        for prefix in ['wkdy', 'wknd']:
            for od_type in all_od_types:
                entry = result[prefix].get(od_type, {})
                global_max = max(global_max,
                                 entry.get('max', 0.0),
                                 entry.get('min', 0.0))
    return global_max * 1.3


def fmt_yaxis(v, _):
    if v >= 1e6: return f"{v/1e6:.0f}M"
    if v >= 1e3: return f"{v/1e3:.0f}K"
    return f"{v:.0f}"

def style_ax(ax):
    ax.grid(axis='y', linestyle='--', alpha=0.4, zorder=0)
    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)
    ax.spines['bottom'].set_color('#cccccc')
    ax.spines['left'].set_color('#cccccc')
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(fmt_yaxis))
    ax.tick_params(axis='y', labelsize=TICK_FS)


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 5 — Horizontal label legend file
# ══════════════════════════════════════════════════════════════════════════════

def save_label_legend(out_path):
    items = list(OD_LABEL_MAP.items())
    n = len(items)

    fig, ax = plt.subplots(figsize=(n * 1.8, 1.8))
    fig.patch.set_facecolor(FIG_BG)
    ax.set_facecolor(FIG_BG)
    ax.axis('off')
    ax.set_xlim(0, n)
    ax.set_ylim(0, 1)

    for i, (full_key, short) in enumerate(items):
        cx = i + 0.5
        full_name = full_key.replace("_", " ")
        ax.text(cx, 0.68, short, ha='center', va='center',
                fontsize=16, fontweight='bold', color='#222222')
        ax.text(cx, 0.28, full_name, ha='center', va='center',
                fontsize=12, color='#555555')
        if i > 0:
            ax.axvline(x=i, color='#dddddd', linewidth=1)

    ax.axhline(y=0.98, color='#cccccc', linewidth=1)
    ax.axhline(y=0.02, color='#cccccc', linewidth=1)

    plt.tight_layout(pad=0.3)
    plt.savefig(out_path, dpi=300, facecolor=FIG_BG, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 6A — Bar v3
# ══════════════════════════════════════════════════════════════════════════════

def plot_bar_month_v3(month_result_wkdy, month_result_wknd,
                      all_od_types, month_name, global_ymax, out_path):
    n_types = len(all_od_types)
    x       = np.arange(n_types)
    width   = 0.2

    bars = [
        ([month_result_wkdy.get(t, {}).get('max', 0.0) for t in all_od_types], C_MAX_WKDY, 'Weekday Max'),
        ([month_result_wknd.get(t, {}).get('max', 0.0) for t in all_od_types], C_MAX_WKND, 'Weekend Max'),
        ([month_result_wkdy.get(t, {}).get('min', 0.0) for t in all_od_types], C_MIN_WKDY, 'Weekday Min'),
        ([month_result_wknd.get(t, {}).get('min', 0.0) for t in all_od_types], C_MIN_WKND, 'Weekend Min'),
    ]
    offsets = [-1.5, -0.5, 0.5, 1.5]

    fig, ax = plt.subplots(figsize=(max(10, n_types * 1.6), 8.5))
    fig.patch.set_facecolor(FIG_BG)
    ax.set_facecolor(FIG_BG)
    style_ax(ax)

    for (vals, color, label), offset in zip(bars, offsets):
        ax.bar(x + offset * width, vals, width,
               label=label, color=color, alpha=BAR_ALPHA,
               edgecolor='white', linewidth=0.5, zorder=3)

    ax.set_ylim(0, global_ymax)
    ax.set_title(month_name.capitalize(), fontsize=TITLE_FS, fontweight='bold', pad=10)
    ax.set_xticks(x)
    ax.set_xticklabels([short_label(t) for t in all_od_types],
                       rotation=XTICK_ROT, ha='right', fontsize=XTICK_FS)
    ax.set_ylabel("Total daily exposure", fontsize=YLABEL_FS)
    ax.legend(fontsize=LEGEND_FS, loc='upper right', labelspacing=0.2,
              bbox_to_anchor=(0.99, 1.04))

    plt.tight_layout()
    plt.savefig(out_path, dpi=300, facecolor=FIG_BG, bbox_inches='tight')
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 6B — Line version
# ══════════════════════════════════════════════════════════════════════════════

def plot_line_month(month_result_wkdy, month_result_wknd,
                    all_od_types, month_name, global_ymax, out_path):
    n_types = len(all_od_types)
    x       = np.arange(n_types)

    vals = {
        'max_wkdy': [month_result_wkdy.get(t, {}).get('max', 0.0) for t in all_od_types],
        'max_wknd': [month_result_wknd.get(t, {}).get('max', 0.0) for t in all_od_types],
        'min_wkdy': [month_result_wkdy.get(t, {}).get('min', 0.0) for t in all_od_types],
        'min_wknd': [month_result_wknd.get(t, {}).get('min', 0.0) for t in all_od_types],
    }

    lines = [
        ('max_wkdy', 'Weekday Max', C_MAX_WKDY, '-',  3.5),
        ('max_wknd', 'Weekend Max', C_MAX_WKND, '-',  3.5),
        ('min_wkdy', 'Weekday Min', C_MIN_WKDY, '--', 3.0),
        ('min_wknd', 'Weekend Min', C_MIN_WKND, '--', 3.0),
    ]

    fig, ax = plt.subplots(figsize=(max(10, n_types * 1.2), 8.5))
    fig.patch.set_facecolor(FIG_BG)
    ax.set_facecolor(FIG_BG)
    style_ax(ax)

    for key, lbl, color, ls, lw in lines:
        ax.plot(x, vals[key], color=color, linestyle=ls, linewidth=lw,
                marker='o', markersize=10, label=lbl, zorder=3,
                markeredgecolor='white', markeredgewidth=1.5)

    ax.set_ylim(0, global_ymax)
    ax.set_title(month_name.capitalize(), fontsize=TITLE_FS, fontweight='bold', pad=10)
    ax.set_xticks(x)
    ax.set_xticklabels([short_label(t) for t in all_od_types],
                       rotation=XTICK_ROT, ha='right', fontsize=XTICK_FS)
    ax.set_ylabel("Total daily exposure", fontsize=YLABEL_FS)
    ax.legend(fontsize=LEGEND_FS, loc='upper right', labelspacing=0.2)

    plt.tight_layout()
    plt.savefig(out_path, dpi=300, facecolor=FIG_BG, bbox_inches='tight')
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
#  STEP 6C — Pie v4: 4 separate files, consistent layout via ax.set_position
# ══════════════════════════════════════════════════════════════════════════════

def compute_annual_avg(monthly_data, all_od_types):
    n = len(monthly_data)
    avg = {
        'wkdy': {t: {'max': 0.0, 'min': 0.0} for t in all_od_types},
        'wknd': {t: {'max': 0.0, 'min': 0.0} for t in all_od_types},
    }
    for result in monthly_data:
        for prefix in ['wkdy', 'wknd']:
            for t in all_od_types:
                entry = result[prefix].get(t, {})
                avg[prefix][t]['max'] += entry.get('max', 0.0) / n
                avg[prefix][t]['min'] += entry.get('min', 0.0) / n
    return avg


def plot_single_pie(vals, all_od_types, title, out_path):
    colors = PIE_COLORS[:len(all_od_types)]
    labels = [short_label(t) for t in all_od_types]
    total  = sum(vals)

    fig = plt.figure(figsize=(16, 11))
    fig.patch.set_facecolor(FIG_BG)

    # Title via fig.text at fixed absolute position — same for all 4 pies
    fig.text(0.5, 0.93, title,
             ha='center', va='top',
             fontsize=45, fontweight='bold', color='#000000')

    # Pie axes pinned to fixed position — same for all 4 pies
    ax = fig.add_axes([0.05, 0.00, 0.9, 0.92])
    ax.set_facecolor(FIG_BG)

    wedges, _ = ax.pie(
        vals,
        labels=None,
        colors=colors,
        startangle=90,
        wedgeprops=dict(edgecolor='white', linewidth=2),
        radius=0.72,
    )

    for i, (wedge, label, val) in enumerate(zip(wedges, labels, vals)):
        angle = (wedge.theta2 + wedge.theta1) / 2
        pct   = val / total * 100
        x     = np.cos(np.radians(angle))
        y     = np.sin(np.radians(angle))

        lx = 0.75 * x
        ly = 0.75 * y
        tx = 0.90 * x
        ty = 0.90 * y

        ha = 'left' if x >= 0 else 'right'

        ax.annotate(
            f"{pct:.1f}%",
            xy=(lx, ly),
            xytext=(tx, ty),
            ha=ha, va='center',
            fontsize=32,
            color='#000000',
            fontweight='bold',
            arrowprops=dict(arrowstyle='-', color='#6e6a6a', lw=1.4),
        )

    plt.savefig(out_path, dpi=300, facecolor=FIG_BG, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out_path}")


def save_pie_legend(all_od_types, out_path):
    labels = [short_label(t) for t in all_od_types]
    colors = PIE_COLORS[:len(all_od_types)]

    fig, ax = plt.subplots(figsize=(len(all_od_types) * 1.6, 1.4))
    fig.patch.set_facecolor(FIG_BG)
    ax.set_facecolor(FIG_BG)
    ax.axis('off')

    handles = [mpatches.Patch(color=c, label=l) for c, l in zip(colors, labels)]
    ax.legend(handles=handles, loc='center', ncol=int(np.ceil(len(all_od_types) / 2)),
              fontsize=32, frameon=False, handlelength=1.5, columnspacing=1)

    plt.tight_layout(pad=0.3)
    plt.savefig(out_path, dpi=300, facecolor=FIG_BG, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_pies_v4(monthly_data, all_od_types, pie_dir):
    avg = compute_annual_avg(monthly_data, all_od_types)

    pies = [
        ('wkdy', 'max', 'Weekday Shortest Route',      'plot7_pie_weekday_max.png'),
        ('wkdy', 'min', 'Weekday Min Exposure Route',   'plot7_pie_weekday_min.png'),
        ('wknd', 'max', 'Weekend Shortest Route',       'plot7_pie_weekend_max.png'),
        ('wknd', 'min', 'Weekend Min Exposure Route',   'plot7_pie_weekend_min.png'),
    ]

    for prefix, key, title, fname in pies:
        vals = [avg[prefix][t][key] for t in all_od_types]
        plot_single_pie(vals, all_od_types, title, os.path.join(pie_dir, fname))

    save_pie_legend(all_od_types, os.path.join(pie_dir, "plot7_pie_legend.png"))


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    hours = list(range(HOUR_START, HOUR_END + 1))

    exact_map = by_origin = by_dest = {}
    if not os.path.exists(CACHE_FILE):
        print("Loading od_type lookups...")
        exact_map, by_origin, by_dest = load_od_lookups(OD_TYPE_CSV)
        if not exact_map:
            print("ERROR: od_type lookup empty.")
            raise SystemExit(1)

    print("\nBuilding monthly data matrix...")
    monthly_data, all_od_types = build_matrix(exact_map, by_origin, by_dest, hours)

    if not all_od_types:
        print("ERROR: No OD types found.")
        raise SystemExit(1)

    print(f"\nOD types ({len(all_od_types)}): {all_od_types}")

    global_ymax = compute_global_ymax(monthly_data, all_od_types)
    print(f"Global y-axis max: {global_ymax:.2e}")

    for subdir in ["bar/v3", "line", "pie"]:
        os.makedirs(os.path.join(PLOT_DIR, subdir), exist_ok=True)

    print("\nGenerating label legend...")
    save_label_legend(os.path.join(PLOT_DIR, "legend_labels.png"))

    print("\nGenerating bar v3 plots (12)...")
    for m_idx, month_name in enumerate(MONTHS):
        out_path = os.path.join(PLOT_DIR, "bar/v3", f"plot7_bar_v3_{month_name}.png")
        plot_bar_month_v3(
            monthly_data[m_idx]['wkdy'],
            monthly_data[m_idx]['wknd'],
            all_od_types, month_name, global_ymax, out_path,
        )
        print(f"  Saved: {out_path}")

    print("\nGenerating line plots (12)...")
    for m_idx, month_name in enumerate(MONTHS):
        out_path = os.path.join(PLOT_DIR, "line", f"plot7_line_{month_name}.png")
        plot_line_month(
            monthly_data[m_idx]['wkdy'],
            monthly_data[m_idx]['wknd'],
            all_od_types, month_name, global_ymax, out_path,
        )
        print(f"  Saved: {out_path}")

    print("\nGenerating pie charts v4 (4 files + legend)...")
    plot_pies_v4(monthly_data, all_od_types, os.path.join(PLOT_DIR, "pie"))

    print(f"\n{'='*60}")
    print(f"  Done.")
    print(f"  Bar v3:        ./{PLOT_DIR}/bar/v3/")
    print(f"  Lines:         ./{PLOT_DIR}/line/")
    print(f"  Pies:          ./{PLOT_DIR}/pie/")
    print(f"  Label legend:  ./{PLOT_DIR}/legend_labels.png")
    print(f"  Cache:         {CACHE_FILE}  (delete to reprocess)")
    print(f"{'='*60}")