"""
Plot 5: Monthly cumulative pedestrian exposure heatmap
Uses actual calendar day counts per month (weekdays vs weekends).
2 groups: max (shortest) and min (shadiest)
Shared colorscale across both groups for direct comparison.
"""

import psycopg2
import csv
import os
import glob
import pickle
import re
import calendar
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from collections import defaultdict
from datetime import date

CACHE_PATH    = "figure5_data_cache.pkl"
CACHE_VERSION = 2   # bumped so old weekly cache is ignored

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
plt.rcParams['text.color'] = '#1a1a1a'
plt.rcParams['axes.labelcolor'] = '#1a1a1a'
plt.rcParams['xtick.color'] = '#1a1a1a'
plt.rcParams['ytick.color'] = '#1a1a1a'

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

OD_CSV   = "../od_all_hourly_unity_filtered.csv"
PLOT_DIR = "figure_five_fix"
YEAR     = 2026   # used for calendar weekday counting

PARETO_DIRS = {
    "Jan": ("../jan",     1),
    "Feb": ("../feb",     2),
    "Mar": ("../march",   3),
    "Apr": ("../april",   4),
    "May": ("../may",     5),
    "Jun": ("../june",    6),
    "Jul": ("../july2",   7),
    "Aug": ("../august",  8),
    "Sep": ("../sept",    9),
    "Oct": ("../oct",    10),
    "Nov": ("../nov",    11),
    "Dec": ("../dec",    12),
}

HOUR_START = 5
HOUR_END   = 20
HOURS      = list(range(HOUR_START, HOUR_END + 1))

DB_PARAMS = dict(
    host=os.environ["DB_HOST"],
    port=int(os.environ.get("DB_PORT", "5432")),
    database=os.environ["DB_DATABASE"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
)

GROUPS = [
    ("shortest", "max", "YlOrRd", "Shortest route — cumulative exposure"),
    ("shadiest", "min", "YlOrRd", "Shadiest route — cumulative exposure"),
]

# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def parse_point(point_str):
    x, z, *_ = re.findall(r'[-\d.]+', point_str)
    return (-float(x), -float(z))


def fmt_tick(val):
    abs_val = abs(val)
    if abs_val >= 1e9:
        return f"{abs_val/1e9:.1f}B"
    elif abs_val >= 1e6:
        return f"{abs_val/1e6:.1f}M"
    elif abs_val >= 1e3:
        return f"{abs_val/1e3:.0f}k"
    elif abs_val == 0:
        return "0"
    else:
        return f"{abs_val:.0f}"


def month_day_counts(year, month_num):
    """Return (n_weekdays, n_weekend_days) for a given month."""
    n_days = calendar.monthrange(year, month_num)[1]
    n_wd   = sum(1 for d in range(1, n_days + 1)
                 if date(year, month_num, d).weekday() < 5)
    n_we   = n_days - n_wd
    return n_wd, n_we

# ══════════════════════════════════════════════════════════════════════════════
#  DB LOAD
# ══════════════════════════════════════════════════════════════════════════════

def load_graph(conn):
    cursor = conn.cursor()
    print("  Loading waypoints...")
    cursor.execute("SELECT id, ST_AsText(geom) FROM meo_waypoints;")
    coord_map = {wp_id: parse_point(geom) for wp_id, geom in cursor.fetchall()}
    print(f"    {len(coord_map):,} waypoints")
    print("  Loading edges...")
    cursor.execute("SELECT id, start_wp_id, end_wp_id FROM meo_edges;")
    edges = [(u, v) for _, u, v in cursor.fetchall()]
    edges += [(v, u) for _, u, v in cursor.fetchall()]
    print(f"    {len(edges):,} directed edges")
    cursor.close()
    return coord_map, edges


def load_od_weights(od_csv):
    print("  Loading OD trip weights...")
    weights = {}
    with open(od_csv, newline='') as f:
        for row in csv.DictReader(f):
            src = row['source_wp'].strip()
            tgt = row['target_wp'].strip()
            weights[(src, tgt)] = {
                h: {
                    'wkdy': float(row.get(f"wkdy_{h}", 0) or 0),
                    'wknd': float(row.get(f"wknd_{h}", 0) or 0),
                }
                for h in HOURS
            }
    print(f"    {len(weights):,} OD pairs")
    return weights

# ══════════════════════════════════════════════════════════════════════════════
#  CACHE
# ══════════════════════════════════════════════════════════════════════════════

def load_cache():
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH, 'rb') as f:
            cache = pickle.load(f)
        if cache.get('version') != CACHE_VERSION:
            print(f"  [CACHE] version mismatch, rebuilding")
            return None
        print(f"  Loaded cache from {CACHE_PATH}")
        return cache
    except Exception as e:
        print(f"  [CACHE] load failed: {e}")
        return None


def save_cache(coord_map, edges, od_weights, monthly_data, vmax_global):
    with open(CACHE_PATH, 'wb') as f:
        pickle.dump({
            'version':      CACHE_VERSION,
            'coord_map':    coord_map,
            'edges':        edges,
            'od_weights':   od_weights,
            'monthly_data': monthly_data,
            'vmax_global':  vmax_global,
        }, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"  Cache saved → {CACHE_PATH}")

# ══════════════════════════════════════════════════════════════════════════════
#  PRINT STATISTICS — add after save_cache() function
# ══════════════════════════════════════════════════════════════════════════════

def print_network_stats(monthly_data):
    """Print summary statistics for each month and routing strategy."""
    
    MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    for route_type, label in [("max", "Shortest"), ("min", "Shadiest")]:
        print(f"\n{'═'*70}")
        print(f"  {label} Route — Edge-level Cumulative Exposure Statistics")
        print(f"{'═'*70}")
        print(f"  {'Month':<6} {'Mean':>12} {'Median':>12} {'Std':>12} "
              f"{'P90':>12} {'P95':>12} {'N Edges':>10}")
        print(f"  {'-'*66}")
        
        for month in MONTHS:
            data = monthly_data.get(month)
            if not data or not data[route_type]:
                print(f"  {month:<6} {'NO DATA':>12}")
                continue
            
            vals = np.array(list(data[route_type].values()))
            
            print(f"  {month:<6} "
                  f"{np.mean(vals):>12.0f} "
                  f"{np.median(vals):>12.0f} "
                  f"{np.std(vals):>12.0f} "
                  f"{np.percentile(vals, 90):>12.0f} "
                  f"{np.percentile(vals, 95):>12.0f} "
                  f"{len(vals):>10,}")

    # Difference stats (shadiest - shortest)
    print(f"\n{'═'*70}")
    print(f"  Route Exposure Difference (Shadiest - Shortest)")
    print(f"{'═'*70}")
    print(f"  {'Month':<6} {'Mean Diff':>12} {'% Negative':>12} "
          f"{'Max Pos':>12} {'Max Neg':>12}")
    print(f"  {'-'*54}")
    
    for month in MONTHS:
        data = monthly_data.get(month)
        if not data or not data['max'] or not data['min']:
            print(f"  {month:<6} {'NO DATA':>12}")
            continue
        
        # Get common edges
        all_edges = set(data['max'].keys()) | set(data['min'].keys())
        diffs = []
        for edge in all_edges:
            max_val = data['max'].get(edge, 0)
            min_val = data['min'].get(edge, 0)
            diffs.append(min_val - max_val)
        
        diffs = np.array(diffs)
        pct_negative = 100 * np.mean(diffs < 0)
        
        print(f"  {month:<6} "
              f"{np.mean(diffs):>12.0f} "
              f"{pct_negative:>11.1f}% "
              f"{np.max(diffs):>12.0f} "
              f"{np.min(diffs):>12.0f}")

def print_total_network_exposure(monthly_data):
    """Print total network-wide cumulative exposure by month and routing strategy."""
    
    MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    print(f"\n{'═'*80}")
    print(f"  Total Network-Wide Cumulative Exposure")
    print(f"{'═'*80}")
    print(f"  {'Month':<6} {'Shortest Total':>16} {'Shadiest Total':>16} "
          f"{'Reduction':>12} {'% Reduction':>12}")
    print(f"  {'-'*64}")
    
    for month in MONTHS:
        data = monthly_data.get(month)
        if not data:
            continue
            
        # Sum all edge values directly
        shortest_total = sum(data['max'].values()) if data['max'] else 0
        shadiest_total = sum(data['min'].values()) if data['min'] else 0
        
        reduction = shortest_total - shadiest_total
        pct_reduction = 100 * reduction / shortest_total if shortest_total > 0 else 0
        
        print(f"  {month:<6} "
              f"{shortest_total:>16,.0f} "
              f"{shadiest_total:>16,.0f} "
              f"{reduction:>12,.0f} "
              f"{pct_reduction:>11.1f}%")
    
    print()

# ══════════════════════════════════════════════════════════════════════════════
#  PROCESS ONE MONTH — uses actual calendar day counts
# ══════════════════════════════════════════════════════════════════════════════

def parse_pareto_filename(fname):
    base  = fname.replace('pareto_', '').replace('.csv', '')
    parts = base.split('--')
    if len(parts) < 3:
        return None, None
    src = parts[0].replace('_', '-')
    tgt = parts[1].replace('_', '-')
    return src, tgt


def process_month(pareto_dir, month_num, od_weights, month_name):
    pareto_files = glob.glob(os.path.join(pareto_dir, "pareto_*.csv"))
    print(f"  Found {len(pareto_files):,} pareto files")
    if not pareto_files:
        return None

    n_wd, n_we = month_day_counts(YEAR, month_num)
    print(f"  Calendar {month_name}: {n_wd} weekdays, {n_we} weekend days")

    max_heat = defaultdict(float)
    min_heat = defaultdict(float)
    file_count = skip_nokey = 0

    for fpath in pareto_files:
        fname    = os.path.basename(fpath)
        src, tgt = parse_pareto_filename(fname)
        if src is None:
            skip_nokey += 1
            continue

        od_w = od_weights.get((src, tgt))
        if not od_w:
            skip_nokey += 1
            continue

        by_time = defaultdict(list)
        try:
            with open(fpath, newline='') as f:
                for row in csv.DictReader(f):
                    st   = int(row['start_time_min'])
                    rank = int(row['rank'])
                    exp  = float(row['exposure'])
                    path = [n.strip() for n in row.get('path', '').split(',') if n.strip()]
                    if len(path) >= 2:
                        by_time[st].append((rank, exp, path))
        except Exception as e:
            print(f"  [WARN] {fname}: {e}")
            continue

        for st, entries in by_time.items():
            h = st // 60
            if h not in HOURS:
                continue

            entries.sort(key=lambda x: x[0])
            rank1_exp,  rank1_path = entries[0][1],  entries[0][2]
            rankN_exp,  rankN_path = entries[-1][1], entries[-1][2]

            hw = od_w.get(h, {'wkdy': 0, 'wknd': 0})
            w_wd = hw['wkdy']
            w_we = hw['wknd']

            # Monthly weight = weekday_trips × n_weekdays + weekend_trips × n_weekend_days
            w_max = w_wd * n_wd + w_we * n_we
            w_min = w_wd * n_wd + w_we * n_we

            if w_max <= 0:
                continue

            for i in range(len(rank1_path) - 1):
                max_heat[(rank1_path[i], rank1_path[i+1])] += w_max * rank1_exp

            for i in range(len(rankN_path) - 1):
                min_heat[(rankN_path[i], rankN_path[i+1])] += w_min * rankN_exp

        file_count += 1
        if file_count % 1000 == 0:
            print(f"    {file_count:,} / {len(pareto_files):,}...", flush=True)

    print(f"  Processed {file_count:,} files, skipped {skip_nokey:,}")
    return {'max': max_heat, 'min': min_heat}

# ══════════════════════════════════════════════════════════════════════════════
#  DRAW LEGEND
# ══════════════════════════════════════════════════════════════════════════════

def draw_legend(vmax_global, cmap_name, out_path):
    fig, ax = plt.subplots(figsize=(4, 10))
    fig.patch.set_facecolor('white')
    ax.set_visible(False)

    # Target ~5 ticks
    step = vmax_global / 4   # gives 5 ticks: 0, 25%, 50%, 75%, 100%
    # Round to a nice number
    magnitude = 10 ** np.floor(np.log10(step))
    step = np.round(step / magnitude) * magnitude
    ticks = list(np.arange(0, vmax_global + step, step))

    sm = plt.cm.ScalarMappable(
        cmap=cmap_name,
        norm=plt.Normalize(vmin=0, vmax=ticks[-1])
    )
    sm.set_array([])

    cbar_ax = fig.add_axes([0.15, 0.05, 0.18, 0.88])
    cbar    = fig.colorbar(sm, cax=cbar_ax)
    cbar.set_label('Cumulative Exposed Cells',
                   fontsize=44, color='black', fontweight='semibold', labelpad=10)
    cbar.ax.tick_params(labelsize=36, colors='black', length=10, width=2)
    cbar.set_ticks(ticks)
    cbar.set_ticklabels([fmt_tick(t) for t in ticks])
    for label in cbar.ax.get_yticklabels():
        label.set_fontweight('bold')

    plt.savefig(out_path, dpi=300, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f"    Saved legend: {out_path}")

# ══════════════════════════════════════════════════════════════════════════════
#  DRAW MAP
# ══════════════════════════════════════════════════════════════════════════════

def draw_and_save_map(coord_map, all_edges, edge_values,
                      month_name, cmap_name, vmax_global, out_path):
    fig, ax = plt.subplots(figsize=(6, 9))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.axis('off')

    ax.text(0.15, 0.94, month_name,
            transform=ax.transAxes,
            fontsize=50, fontweight='bold',
            va='top', ha='left', color='black')

    bg_lines = [[coord_map[u], coord_map[v]]
                for u, v in all_edges
                if u in coord_map and v in coord_map]
    if bg_lines:
        ax.add_collection(LineCollection(bg_lines, colors='#dddddd',
                                         linewidths=0.3, zorder=1))

    if not edge_values:
        ax.text(0.5, 0.5, "No data", ha='center', va='center',
                transform=ax.transAxes, fontsize=10, color='gray')
        ax.autoscale()
        plt.savefig(out_path, dpi=300, facecolor='white', bbox_inches='tight')
        plt.close(fig)
        return

    undirected = {}
    for (u, v), val in edge_values.items():
        key = tuple(sorted([u, v]))
        undirected[key] = undirected.get(key, 0) + val

    hot_lines  = []
    hot_values = []
    for (u, v), val in undirected.items():
        if u in coord_map and v in coord_map:
            hot_lines.append([coord_map[u], coord_map[v]])
            hot_values.append(val)

    if not hot_lines:
        ax.text(0.5, 0.5, "No coords matched", ha='center', va='center',
                transform=ax.transAxes, fontsize=10, color='red')
        ax.autoscale()
        plt.savefig(out_path, dpi=300, facecolor='white', bbox_inches='tight')
        plt.close(fig)
        return

    lc = LineCollection(
        hot_lines,
        array=np.array(hot_values),
        cmap=cmap_name,
        norm=plt.Normalize(vmin=0, vmax=vmax_global),
        linewidths=0.8,
        zorder=2
    )
    ax.add_collection(lc)
    ax.autoscale()
    ax.set_aspect('equal')

    plt.savefig(out_path, dpi=300, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f"    Saved: {out_path}")

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    os.makedirs(PLOT_DIR, exist_ok=True)

    cache = load_cache()
    if cache is not None:
        coord_map    = cache['coord_map']
        edges        = cache['edges']
        od_weights   = cache['od_weights']
        monthly_data = cache['monthly_data']
        vmax_global  = cache['vmax_global']
    else:
        conn             = psycopg2.connect(**DB_PARAMS)
        coord_map, edges = load_graph(conn)
        conn.close()

        od_weights = load_od_weights(OD_CSV)

        monthly_data = {}
        for month_name, (pareto_dir, month_num) in PARETO_DIRS.items():
            print(f"\n{'═'*60}")
            print(f"  {month_name} → {pareto_dir}/")
            print(f"{'═'*60}")
            monthly_data[month_name] = process_month(
                pareto_dir, month_num, od_weights, month_name)

        all_vals = []
        for data in monthly_data.values():
            if data:
                all_vals.extend(data['max'].values())
                all_vals.extend(data['min'].values())

        vmax_global = np.percentile(all_vals, 95) if all_vals else 1.0
        vmax_global = max(vmax_global, 1.0)
        print(f"\n  Shared vmax (95th pct): {fmt_tick(vmax_global)}")

        save_cache(coord_map, edges, od_weights, monthly_data, vmax_global)
    print_network_stats(monthly_data)
    print_total_network_exposure(monthly_data)

    # Legend
    draw_legend(vmax_global, "YlOrRd", os.path.join(PLOT_DIR, "legend.png"))

    # Maps
    for group_name, route_type, cmap_name, group_label in GROUPS:
        print(f"\n{'═'*60}")
        print(f"  {group_label}")
        print(f"{'═'*60}")
        group_dir = os.path.join(PLOT_DIR, group_name)
        os.makedirs(group_dir, exist_ok=True)
        for month_name, data in monthly_data.items():
            edge_values = data[route_type] if data else {}
            draw_and_save_map(
                coord_map, edges, edge_values,
                month_name, cmap_name, vmax_global,
                os.path.join(group_dir, f"{month_name}.png")
            )

    print(f"\n  All done → ./{PLOT_DIR}/")