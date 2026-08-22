"""
Plot 5 — Residual heatmap: shadiest − shortest
Uses same cache as figure_five.py (CACHE_VERSION=2, monthly calendar logic).
Positive (warm) = shadiest accumulates MORE exposure than shortest
Negative (cool) = shadiest REDUCES exposure vs shortest  ← good
"""

import csv
import os
import glob
import re
import pickle
import calendar
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.collections import LineCollection
from collections import defaultdict
from datetime import date

# ── shared cache from figure_five.py ──────────────────────────────────────
CACHE_PATH    = "figure5_data_cache.pkl"
CACHE_VERSION = 2

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
plt.rcParams['text.color'] = '#1a1a1a'
plt.rcParams['axes.labelcolor'] = '#1a1a1a'

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

PLOT_DIR = "figure_five_residual"

# ══════════════════════════════════════════════════════════════════════════════
#  COLORMAP (unchanged from original)
# ══════════════════════════════════════════════════════════════════════════════

def make_residual_cmap():
    colors = [
        (0.00, "#041d49"),
        (0.14, "#2166ac"),
        (0.30, "#4393c3"),
        (0.45, "#92c5de"),
        (0.50, "#f7f7f7"),
        (0.55, "#fddbc7"),
        (0.70, "#ef8a3c"),
        (0.85, "#ca0020"),
        (1.00, "#67000d"),
    ]
    return mcolors.LinearSegmentedColormap.from_list(
        "residual_rich",
        [(pos, mcolors.to_rgb(col)) for pos, col in colors]
    )

RESIDUAL_CMAP = make_residual_cmap()

# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def fmt_tick(val):
    sign    = '+' if val > 0 else ('−' if val < 0 else '')
    abs_val = abs(val)
    if abs_val >= 1e9:
        return f"{sign}{abs_val/1e9:.1f}B"
    elif abs_val >= 1e6:
        return f"{sign}{abs_val/1e6:.1f}M"
    elif abs_val >= 1e3:
        return f"{sign}{abs_val/1e3:.0f}k"
    elif abs_val == 0:
        return "0"
    else:
        return f"{sign}{abs_val:.0f}"

# ══════════════════════════════════════════════════════════════════════════════
#  CACHE
# ══════════════════════════════════════════════════════════════════════════════

def load_cache():
    if not os.path.exists(CACHE_PATH):
        print(f"  [ERROR] Cache not found: {CACHE_PATH}")
        print(f"  Run figure_five.py first to build the cache.")
        return None
    try:
        with open(CACHE_PATH, 'rb') as f:
            cache = pickle.load(f)
        if cache.get('version') != CACHE_VERSION:
            print(f"  [ERROR] Cache version mismatch. Run figure_five.py first.")
            return None
        print(f"  Loaded cache from {CACHE_PATH}")
        return cache
    except Exception as e:
        print(f"  [CACHE] load failed: {e}")
        return None


def save_vlim_cache(cache, vlim):
    cache['vlim_residual'] = vlim
    with open(CACHE_PATH, 'wb') as f:
        pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"  vlim saved to cache")

# ══════════════════════════════════════════════════════════════════════════════
#  LEGEND
# ══════════════════════════════════════════════════════════════════════════════

def draw_legend(vlim, out_path):
    fig, ax = plt.subplots(figsize=(4, 10))
    fig.patch.set_facecolor('white')
    ax.set_visible(False)

    norm = mcolors.TwoSlopeNorm(vmin=-vlim, vcenter=0, vmax=vlim)
    sm   = plt.cm.ScalarMappable(cmap=RESIDUAL_CMAP, norm=norm)
    sm.set_array([])

    cbar_ax = fig.add_axes([0.15, 0.05, 0.18, 0.88])
    cbar    = fig.colorbar(sm, cax=cbar_ax)
    cbar.set_label('Residual Exposure',
                   fontsize=44, color='black', fontweight='semibold', labelpad=10)

    # ~5 ticks
    step      = vlim / 2
    magnitude = 10 ** np.floor(np.log10(step))
    step      = np.round(step / magnitude) * magnitude
    ticks     = [-vlim, -step, 0, step, vlim]
    cbar.set_ticks(ticks)
    cbar.set_ticklabels([fmt_tick(t) for t in ticks])
    cbar.ax.tick_params(labelsize=36, colors='black', length=10, width=2)
    for label in cbar.ax.get_yticklabels():
        label.set_fontweight('bold')
    cbar.ax.axhline(y=0.5, color='#555555', linewidth=0.8,
                    linestyle='--', alpha=0.7)

    plt.savefig(out_path, dpi=300, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f"  Legend saved: {out_path}")

# ══════════════════════════════════════════════════════════════════════════════
#  DRAW ONE RESIDUAL MAP
# ══════════════════════════════════════════════════════════════════════════════

def draw_residual_map(coord_map, all_edges, max_heat, min_heat,
                      month_name, vlim, out_path):

    all_keys = set(max_heat.keys()) | set(min_heat.keys())
    residual = {k: min_heat.get(k, 0.0) - max_heat.get(k, 0.0)
                for k in all_keys}

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

    if not residual:
        ax.text(0.5, 0.5, "No data", ha='center', va='center',
                transform=ax.transAxes, fontsize=10, color='gray')
        ax.autoscale()
        plt.savefig(out_path, dpi=300, facecolor='white', bbox_inches='tight')
        plt.close(fig)
        return

    undirected = {}
    for (u, v), val in residual.items():
        key = tuple(sorted([u, v]))
        undirected[key] = undirected.get(key, 0) + val

    hot_lines, hot_values = [], []
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

    norm = mcolors.TwoSlopeNorm(vmin=-vlim, vcenter=0, vmax=vlim)
    lc   = LineCollection(hot_lines, array=np.array(hot_values),
                          cmap=RESIDUAL_CMAP, norm=norm,
                          linewidths=0.8, zorder=2)
    ax.add_collection(lc)
    ax.autoscale()
    ax.set_aspect('equal')

    plt.savefig(out_path, dpi=300, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out_path}")

def print_residual_stats(monthly_data):
    """Print summary statistics for the residual (shadiest - shortest) maps."""
    
    MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    # Track which edges are consistently negative across all months
    edge_negative_count = defaultdict(int)
    edge_total_count = defaultdict(int)
    
    print(f"\n{'═'*80}")
    print(f"  Residual Statistics (Shadiest - Shortest)")
    print(f"{'═'*80}")
    print(f"  {'Month':<6} {'Mean Diff':>12} {'% Negative':>12} {'% Large Neg':>12} "
          f"{'Max Pos':>12} {'Max Neg':>12}")
    print(f"  {'-'*66}")
    
    for month in MONTHS:
        data = monthly_data.get(month)
        if not data or not data['max'] or not data['min']:
            print(f"  {month:<6} {'NO DATA':>12}")
            continue
        
        all_keys = set(data['max'].keys()) | set(data['min'].keys())
        diffs = []
        for k in all_keys:
            diff = data['min'].get(k, 0.0) - data['max'].get(k, 0.0)
            diffs.append((k, diff))
            edge_total_count[k] += 1
            if diff < 0:
                edge_negative_count[k] += 1
        
        diff_vals = np.array([d for _, d in diffs])
        pct_negative = 100 * np.mean(diff_vals < 0)
        
        # Large negative = bottom 10% of differences
        threshold = np.percentile(diff_vals, 10)
        pct_large_neg = 100 * np.mean(diff_vals < threshold)
        
        print(f"  {month:<6} "
              f"{np.mean(diff_vals):>12.0f} "
              f"{pct_negative:>11.1f}% "
              f"{pct_large_neg:>11.1f}% "
              f"{np.max(diff_vals):>12.0f} "
              f"{np.min(diff_vals):>12.0f}")
    
    # Consistency analysis — edges that are consistently negative
    print(f"\n{'═'*80}")
    print(f"  Edge Consistency Analysis")
    print(f"{'═'*80}")
    
    total_edges = len(edge_total_count)
    
    for threshold_months in [12, 10, 8, 6]:
        consistent = sum(1 for k, count in edge_negative_count.items() 
                        if count >= threshold_months)
        pct = 100 * consistent / total_edges if total_edges > 0 else 0
        print(f"  Edges negative in >= {threshold_months}/12 months: "
              f"{consistent:,} ({pct:.1f}% of network)")
    
    print()
# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    os.makedirs(PLOT_DIR, exist_ok=True)

    cache = load_cache()
    if cache is None:
        exit(1)

    coord_map    = cache['coord_map']
    edges        = cache['edges']
    monthly_data = cache['monthly_data']
    vlim         = cache.get('vlim_residual')
    print_residual_stats(monthly_data)

    # Compute vlim if not cached
    if vlim is None:
        print("  Computing global vlim (95th percentile of |residual|)...")
        all_residuals = []
        for data in monthly_data.values():
            if data:
                all_keys = set(data['max'].keys()) | set(data['min'].keys())
                for k in all_keys:
                    all_residuals.append(
                        data['min'].get(k, 0.0) - data['max'].get(k, 0.0)
                    )
        arr  = np.abs(all_residuals)
        vlim = float(np.percentile(arr, 95)) if all_residuals else 1.0
        vlim = max(vlim, 1.0)
        print(f"  vlim = {fmt_tick(vlim)}")
        save_vlim_cache(cache, vlim)

    # Legend
    draw_legend(vlim, os.path.join(PLOT_DIR, "legend.png"))

    # Maps
    for month_name, data in monthly_data.items():
        if not data:
            print(f"  [SKIP] {month_name} — no data")
            continue
        draw_residual_map(
            coord_map, edges,
            data['max'], data['min'],
            month_name, vlim,
            os.path.join(PLOT_DIR, f"{month_name}.png")
        )

    print(f"\n  Done → ./{PLOT_DIR}/")