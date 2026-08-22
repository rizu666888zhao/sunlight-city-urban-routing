"""
Plot trip-weighted average exposure (max and min) per hour
for weekday vs weekend as line chart, one plot per month.
4 lines: weekday max, weekday min, weekend max, weekend min.
"""

import csv
import os
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG（修改路径与参数）
# ══════════════════════════════════════════════════════════════════════════════

# 已经为您指定 CSV 数据所在的绝对路径
INPUT_DIR  = r"C:\Users\DIVINA\Desktop\enriched\enriched"

# 12张单图生成后存放的路径（供您的大图合成代码读取）
PLOT_DIR   = r"C:\Users\DIVINA\Desktop\figure_one\figure_one"

CACHE_FILE = "figure_2a_data.json"

INPUT_FILES = {
    "1.csv":   "january",
    "2.csv":  "february",
    "3.csv":     "march",
    "4.csv":     "april",
    "5.csv":       "may",
    "6.csv":      "june",
    "7.csv":      "july",
    "8.csv":    "august",
    "9.csv": "september",
    "10.csv":   "october",
    "11.csv":  "november",
    "12.csv":  "december",
}

HOUR_START = 3
HOUR_END   = 20  # inclusive

# Color logic:
#   Weekday: orange (max), light blue (min)
#   Weekend: red (max), dark blue (min)
COLORS = {
    'wkdy_max': '#F57C00',  # orange
    'wkdy_min': '#81D4FA',  # light blue
    'wknd_max': '#D32F2F',  # red
    'wknd_min': '#1565C0',  # dark blue
}

# ══════════════════════════════════════════════════════════════════════════════
#  Process and plot one month
# ══════════════════════════════════════════════════════════════════════════════

def process_month_data(filename, month_name, hours):
    filepath = os.path.join(INPUT_DIR, filename)
    if not os.path.exists(filepath):
        print(f"  [SKIP] File not found: {filepath}")
        return None

    print(f"\n{'═'*60}")
    print(f"  Month: {month_name}  |  File: {filename}")
    print(f"{'═'*60}")

    acc = {
        'wkdy': {h: [0.0, 0.0, 0.0] for h in hours},
        'wknd': {h: [0.0, 0.0, 0.0] for h in hours},
    }

    row_count = 0
    with open(filepath, newline='') as f:
        for row in csv.DictReader(f):
            for prefix in ['wkdy', 'wknd']:
                for h in hours:
                    weight  = float(row.get(f"{prefix}_{h}", 0) or 0)
                    min_val = row.get(f"min_{prefix}_{h}", '')
                    max_val = row.get(f"max_{prefix}_{h}", '')
                    if weight == 0 or min_val == '' or max_val == '':
                        continue
                    acc[prefix][h][0] += weight * float(min_val)
                    acc[prefix][h][1] += weight * float(max_val)
                    acc[prefix][h][2] += weight

            row_count += 1
            if row_count % 100000 == 0:
                print(f"  {row_count:,} rows processed...", flush=True)

    print(f"  {row_count:,} rows processed")

    # Compute weighted averages
    min_wkdy, max_wkdy, min_wknd, max_wknd = [], [], [], []
    for h in hours:
        w_dy = acc['wkdy'][h][2]
        w_nd = acc['wknd'][h][2]
        min_wkdy.append(acc['wkdy'][h][0] / w_dy if w_dy > 0 else 0)
        max_wkdy.append(acc['wkdy'][h][1] / w_dy if w_dy > 0 else 0)
        min_wknd.append(acc['wknd'][h][0] / w_nd if w_nd > 0 else 0)
        max_wknd.append(acc['wknd'][h][1] / w_nd if w_nd > 0 else 0)

    return {
        'min_wkdy': min_wkdy,
        'max_wkdy': max_wkdy,
        'min_wknd': min_wknd,
        'max_wknd': max_wknd
    }

def plot_month_data(month_name, hours, data):
    if data is None:
        return

    # Filter data for the requested 4am - 8pm window (4 <= h <= 20)
    valid_idx = [i for i, h in enumerate(hours) if 4 <= h <= 20]
    plot_hours = [hours[i] for i in valid_idx]

    min_wkdy = np.array(data['min_wkdy'])[valid_idx]
    max_wkdy = np.array(data['max_wkdy'])[valid_idx]
    min_wknd = np.array(data['min_wknd'])[valid_idx]
    max_wknd = np.array(data['max_wknd'])[valid_idx]

    # ── Plot ──────────────────────────────────────────────────────────────────
    x      = np.arange(len(plot_hours))
    labels = [f"{h:02d}:00" for h in plot_hours]

    # Use Arial for an academic and professional look
    plt.rcParams['font.family'] = 'Arial'

    # 参数 1：调整为设定的瘦高尺寸 (7, 9)
    fig, ax = plt.subplots(figsize=(12, 10))
    fig.patch.set_facecolor('#ffffff')

    # Weekday — solid lines
    ax.plot(x, max_wkdy, color=COLORS['wkdy_max'], linewidth=4, marker='o', markersize=12, linestyle='-',  label='Weekday max')
    ax.plot(x, min_wkdy, color=COLORS['wkdy_min'], linewidth=4, marker='o', markersize=12, linestyle='-',  label='Weekday min')

    # Weekend — dashed lines
    ax.plot(x, max_wknd, color=COLORS['wknd_max'], linewidth=4, marker='s', markersize=12, linestyle='--', label='Weekend max')
    ax.plot(x, min_wknd, color=COLORS['wknd_min'], linewidth=4, marker='s', markersize=12, linestyle='--', label='Weekend min')

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=24)
    ax.set_xlim(x[0], x[-1])
    ax.set_ylim(0, 250)
    ax.set_yticks(np.arange(0, 251, 50))

    # 参数 2：设置 labelpad=2，显著缩小 Y 轴标签与数字之间的间距
    ax.set_ylabel("Avg. Pedestrian Exposure", fontsize=40, fontweight='bold', labelpad=2)

    # 6-8pt spacing for tick marks
    # 保持 Y 轴字体为 24 不变
    ax.tick_params(axis='y', which='major', labelsize=40, pad=12, length=8, width=2)

    # 核心修改：单独控制 X 轴，将 labelsize 从 24 缩小到 16（或者 14）
    ax.tick_params(axis='x', which='major', labelsize=26, pad=12, length=8, width=2)

    ax.set_title(
        f"{month_name.capitalize()}",
        fontsize=56, fontweight='bold', pad=20
    )

    # Legend slightly reduced and pinned to top right
    ax.legend(fontsize=24, loc='upper right', framealpha=0.9, edgecolor='#333333')

    # Professional grid and spines
    ax.grid(axis='y', alpha=0.4, linestyle='--')
    for spine in ax.spines.values():
        spine.set_edgecolor('#333333')
        spine.set_linewidth(1.5)

    plt.tight_layout()
    out_path = os.path.join(PLOT_DIR, f"exposure_line_{month_name}.png")
    plt.savefig(out_path, dpi=300, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved plot: {out_path}")

# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    os.makedirs(PLOT_DIR, exist_ok=True)
    hours = list(range(HOUR_START, HOUR_END + 1))

    cache_data = {}
    if os.path.exists(CACHE_FILE):
        print(f"Loading cached data from {CACHE_FILE}...")
        try:
            with open(CACHE_FILE, 'r') as f:
                cache_data = json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: {CACHE_FILE} is corrupted. Starting fresh.")

    for filename, month_name in INPUT_FILES.items():
        if month_name in cache_data:
            print(f"\n{'═'*60}")
            print(f"  Month: {month_name}  |  Using cached data")
            print(f"{'═'*60}")
            data = cache_data[month_name]
        else:
            data = process_month_data(filename, month_name, hours)
            if data is not None:
                cache_data[month_name] = data
                with open(CACHE_FILE, 'w') as f:
                    json.dump(cache_data, f, indent=4)

        plot_month_data(month_name, hours, data)

    print(f"\n{'═'*60}")
    print(f"  All done. Plots saved in: {PLOT_DIR}")
    print(f"{'═'*60}\n")