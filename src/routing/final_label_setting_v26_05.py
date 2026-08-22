#this file finds the pareto solutions for all OD pairs (or a subset if you choose) and saves the results of each OD pair
#into a separate CSV file. We run this file on one month at a time.

import psycopg2
import re
import csv
import numpy as np
import networkx as nx
import heapq
import time
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.collections import LineCollection
from collections import defaultdict
import os

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

OD_CSV_PATH   = "od_all_hourly_unity_filtered.csv"
UNIQUE_WP_CSV = "unique_hourly_wp_pairs.csv"  # pre-deduplicated pairs from count_unique_od.py

# Which rows to run:
#slice(0,10000)
#"all"
OD_SELECTION = "all"

SPEED       = 77               # Unity units per minute
START_TIMES = range(180, 1201, 60)  # 03:00 – 20:00 in 60-min steps
OUTPUT_DIR  = "march"           # all CSVs and plots saved here 

DATE_SELECTION = 2 #0 for january, 1 for february, 2 for march, etc. (0-based index into INPUT_FILES)

DB_PARAMS = dict(
    host=os.environ["DB_HOST"],
    port=int(os.environ.get("DB_PORT", "5432")),
    database=os.environ["DB_DATABASE"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
)

# ══════════════════════════════════════════════════════════════════════════════
#  Timing helper
# ══════════════════════════════════════════════════════════════════════════════

class StepTimer:
    def __init__(self):
        self.reset()

    def tick(self, label: str) -> float:
        now     = time.perf_counter()
        step_s  = now - self._last
        total_s = now - self._t0
        print(f"  ⏱  [{total_s:7.3f}s total | +{step_s:6.3f}s]  {label}", flush=True)
        self._last = now
        return step_s

    def reset(self):
        self._t0 = self._last = time.perf_counter()


TIMER = StepTimer()

# ══════════════════════════════════════════════════════════════════════════════
#  Coordinate helpers
# ══════════════════════════════════════════════════════════════════════════════

def parse_point(point_str):
    x, z, *_ = re.findall(r'[-\d.]+', point_str)
    return (float(x), float(z))

# ══════════════════════════════════════════════════════════════════════════════
#  OD CSV loading
# ══════════════════════════════════════════════════════════════════════════════

def load_od_pairs(csv_path: str, selection):
    with open(csv_path, newline='') as f:
        rows = list(csv.DictReader(f))
    total = len(rows)

    if selection == "all":
        selected, original_indices = rows, list(range(total))
        desc = f"all {total} rows"
    elif isinstance(selection, list):
        selected = [rows[i] for i in selection]
        original_indices = list(selection)
        desc = f"rows {selection} ({len(selected)} of {total})"
    elif isinstance(selection, slice):
        selected = rows[selection]
        original_indices = list(range(*selection.indices(total)))
        desc = f"slice {selection} → {len(selected)} of {total} rows"
    elif isinstance(selection, str):
        selected = [r for r in rows if r.get('od_type') == selection]
        original_indices = [j for j, r in enumerate(rows) if r.get('od_type') == selection]
        desc = f"od_type='{selection}' → {len(selected)} of {total} rows"
    else:
        raise ValueError(f"Unsupported OD_SELECTION: {type(selection)}")

    print(f"  OD pairs loaded: {desc}")

    od_pairs = []
    for orig_idx, r in zip(original_indices, selected):
        od_pairs.append({
            'index':      orig_idx,
            'od_type':    r.get('od_type', ''),
            'trips':      float(r.get('trips', 0)),
            'origin_lat': float(r.get('origin_lat', 0)),
            'origin_lon': float(r.get('origin_lon', 0)),
            'dest_lat':   float(r.get('dest_lat', 0)),
            'dest_lon':   float(r.get('dest_lon', 0)),
            'origin_ux':  float(r['origin_Unity_X']),
            'origin_uz':  float(r['origin_Unity_Z']),
            'dest_ux':    float(r['dest_Unity_X']),
            'dest_uz':    float(r['dest_Unity_Z']),
            # Pre-snapped waypoint IDs from CSV — no DB snap needed
            'source_wp':  r.get('source_wp', ''),
            'target_wp':  r.get('target_wp', ''),
        })
    return od_pairs

# ══════════════════════════════════════════════════════════════════════════════
#  Unique waypoint pairs loading
# ══════════════════════════════════════════════════════════════════════════════

def load_unique_wp_pairs(csv_path: str):
    """Load pre-deduplicated (source_wp, target_wp) pairs from unique_wp_pairs.csv."""
    pairs = []
    with open(csv_path, newline='') as f:
        for row in csv.DictReader(f):
            pairs.append((row['source_wp'], row['target_wp']))
    print(f"  Unique WP pairs loaded: {len(pairs):,} from {csv_path}")
    return pairs

# ══════════════════════════════════════════════════════════════════════════════
#  Minute helpers
# ══════════════════════════════════════════════════════════════════════════════

def dt_to_minute(dt):
    return min(round((dt.hour * 60 + dt.minute) / 3) * 3, 2000)

def round3(t):
    return int(round(t / 3) * 3)

# ══════════════════════════════════════════════════════════════════════════════
#  Snap to nearest waypoint
# ══════════════════════════════════════════════════════════════════════════════

def snap_to_waypoint(cursor, ux: float, uz: float, label: str):
    cursor.execute("""
        SELECT id, ST_AsText(geom),
               ST_Distance(geom, ST_MakePoint(%s, %s)) AS dist
        FROM meo_waypoints
        ORDER BY geom <-> ST_MakePoint(%s, %s)
        LIMIT 1;
    """, (ux, uz, ux, uz))
    row    = cursor.fetchone()
    wp_id  = row[0]
    wp_xy  = parse_point(row[1])
    snap_d = row[2]
    TIMER.tick(f"Snap {label} → waypoint {wp_id}  (dist {snap_d:.4f} u)")
    return wp_id, wp_xy, snap_d

# ══════════════════════════════════════════════════════════════════════════════
#  Per-date exposure precompute
# ══════════════════════════════════════════════════════════════════════════════

def precompute_edge_exposure(speed_m_min: float):
    edge_exposure = {}
    for eid, sorted_cells in edge_cells.items():
        uv   = edge_id_to_uv.get(eid)
        info = edge_info.get(uv) if uv else None
        if not info:
            continue
        n = len(sorted_cells)
        if n == 0:
            continue
        cell_size = info['len'] / n
        sunlit    = np.zeros((2001, n), dtype=np.float32)
        for col_idx, (_, cid) in enumerate(sorted_cells):
            cell_data = exposure_by_cell.get(cid)
            if cell_data:
                mins = np.array(list(cell_data.keys()),   dtype=np.int32)
                vals = np.array(list(cell_data.values()), dtype=np.float32)
                sunlit[mins, col_idx] = vals
        start_times = np.arange(2001).reshape(2001, 1)
        offsets_fwd = np.arange(n) * cell_size / speed_m_min
        arrival_fwd = np.clip(
            (np.round((start_times + offsets_fwd) / 3) * 3).astype(int), 0, 2000)
        edge_exposure[uv] = sunlit[arrival_fwd, np.arange(n)].sum(axis=1)
        offsets_rev = np.arange(n - 1, -1, -1) * cell_size / speed_m_min
        arrival_rev = np.clip(
            (np.round((start_times + offsets_rev) / 3) * 3).astype(int), 0, 2000)
        edge_exposure[(uv[1], uv[0])] = sunlit[arrival_rev, np.arange(n)].sum(axis=1)
    return edge_exposure

# ══════════════════════════════════════════════════════════════════════════════
#  Lower bounds  (target-dependent, computed per OD)
# ══════════════════════════════════════════════════════════════════════════════

def compute_duration_lower_bounds(graph, target, speed_m_min: float):
    heap = [(0.0, target)]
    lb   = {target: 0.0}
    while heap:
        cost, node = heapq.heappop(heap)
        if cost > lb.get(node, float('inf')):
            continue
        for nb in graph.predecessors(node):
            e = edge_info.get((nb, node))
            if not e:
                continue
            nc = cost + e['len'] / speed_m_min
            if nc < lb.get(nb, float('inf')):
                lb[nb] = nc
                heapq.heappush(heap, (nc, nb))
    return lb


def compute_exposure_lower_bounds(graph, target, edge_exposure):
    min_exp = {e: float(np.min(arr)) for e, arr in edge_exposure.items()}
    heap    = [(0.0, target)]
    lb      = {target: 0.0}
    while heap:
        cost, node = heapq.heappop(heap)
        if cost > lb.get(node, float('inf')):
            continue
        for nb in graph.predecessors(node):
            key = (nb, node)
            if key not in min_exp:
                continue
            nc = cost + min_exp[key]
            if nc < lb.get(nb, float('inf')):
                lb[nb] = nc
                heapq.heappush(heap, (nc, nb))
    return lb


def dijkstra_duration_fast(fast_adj, source, target):
    pq   = [(0.0, source)]
    dist = {source: 0.0}
    while pq:
        cur, node = heapq.heappop(pq)
        if cur > dist.get(node, float('inf')):
            continue
        if node == target:
            return cur
        for nb, et, _, _ in fast_adj.get(node, []):
            nd = cur + et
            if nd < dist.get(nb, float('inf')):
                dist[nb] = nd
                heapq.heappush(pq, (nd, nb))
    return float('inf')

# ══════════════════════════════════════════════════════════════════════════════
#  Dominance
# ══════════════════════════════════════════════════════════════════════════════

def dominates_label(a, b):
    return (
        a['duration'] <= b['duration']
        and a['exposure'] <= b['exposure']
        and a['turns']   <= b['turns']
        and (a['duration'] < b['duration']
             or a['exposure'] < b['exposure']
             or a['turns']   < b['turns'])
    )

def dominates_target(a, b):
    return (
        a['duration'] <= b['duration']
        and a['exposure'] <= b['exposure']
        and (a['duration'] < b['duration'] or a['exposure'] < b['exposure'])
    )

# ══════════════════════════════════════════════════════════════════════════════
#  Turn detection
# ══════════════════════════════════════════════════════════════════════════════

TURN_THRESHOLD_DEG = 30.0

def is_turn(angle1, angle2):
    if angle1 is None:
        return False
    return abs((angle2 - angle1 + 180) % 360 - 180) > TURN_THRESHOLD_DEG

# ══════════════════════════════════════════════════════════════════════════════
#  Multi-objective label-setting
# ══════════════════════════════════════════════════════════════════════════════

def label_setting_pareto_fast(fast_adj, source, target, edge_exposure,
                               start_time, speed_m_min, delta, max_turns,
                               dur_lb, exp_lb):
    if source not in dur_lb:
        return []

    max_duration     = dur_lb[source] * (1 + delta)
    LN               = {node: {} for node in fast_adj}
    pq               = []
    label_id         = 0
    completed_pareto = []

    start_label = {
        'node': source, 'duration': 0.0, 'exposure': 0.0,
        'turns': 0, 'last_angle': None, 'parent': None,
        'valid': True, 'settled': False,
    }
    LN[source].setdefault(None, []).append(start_label)
    heapq.heappush(pq, (dur_lb.get(source, float('inf')),
                        exp_lb.get(source, float('inf')),
                        label_id, start_label))
    label_id += 1

    while pq:
        _, _, _, current = heapq.heappop(pq)
        if not current['valid'] or current['settled']:
            continue
        node               = current['node']
        dur, exp           = current['duration'], current['exposure']
        turns, last_angle  = current['turns'], current['last_angle']
        current['settled'] = True

        if dur + dur_lb.get(node, float('inf')) > max_duration:
            continue

        if node == target:
            dominated = False
            to_remove = []
            for comp in completed_pareto:
                if not comp['valid']:
                    continue
                if dominates_target(comp, current):
                    dominated = True; break
                if dominates_target(current, comp):
                    to_remove.append(comp)
            if not dominated:
                for comp in to_remove:
                    comp['valid'] = False
                completed_pareto.append(current)
            continue

        for nb, edge_time, edge_angle, edge_key in fast_adj.get(node, []):
            new_turns = turns + (1 if is_turn(last_angle, edge_angle) else 0)
            if new_turns > max_turns:
                continue
            new_dur = dur + edge_time
            if new_dur + dur_lb.get(nb, float('inf')) > max_duration:
                continue
            if edge_key not in edge_exposure:
                continue
            arrival_t = min(round3(start_time + dur), 2000)
            new_exp   = exp + edge_exposure[edge_key][arrival_t]

            angle_key        = round(edge_angle) if edge_angle is not None else None
            candidate_labels = LN[nb].setdefault(angle_key, [])
            probe            = {'duration': new_dur, 'exposure': new_exp, 'turns': new_turns}
            is_dominated     = False
            surviving        = []

            for existing in candidate_labels:
                if not existing['valid']:
                    continue
                if dominates_label(existing, probe):
                    is_dominated = True
                    surviving.append(existing)
                elif dominates_label(probe, existing):
                    existing['valid'] = False
                else:
                    surviving.append(existing)

            LN[nb][angle_key] = surviving
            if not is_dominated:
                new_label = {
                    'node': nb, 'duration': new_dur, 'exposure': new_exp,
                    'turns': new_turns, 'last_angle': edge_angle,
                    'parent': current, 'valid': True, 'settled': False,
                }
                surviving.append(new_label)
                heapq.heappush(pq, (
                    new_dur + dur_lb.get(nb, float('inf')),
                    new_exp + exp_lb.get(nb, float('inf')),
                    label_id, new_label
                ))
                label_id += 1

    final_results = []
    for comp in completed_pareto:
        if not comp['valid']:
            continue
        path_nodes, curr = [], comp
        while curr:
            path_nodes.append(curr['node']); curr = curr['parent']
        path_nodes.reverse()
        comp['path'] = path_nodes
        final_results.append(comp)

    strict_pareto = [
        c for c in final_results
        if not any(o is not c and dominates_target(o, c) for o in final_results)
    ]
    unique = {}
    for r in strict_pareto:
        key = (r['duration'], r['exposure'])
        if key not in unique or r['turns'] < unique[key]['turns']:
            unique[key] = r
    return list(unique.values())

# ══════════════════════════════════════════════════════════════════════════════
#  Max consecutive sunlit streak
# ══════════════════════════════════════════════════════════════════════════════

def max_consecutive_sunlit(path, edge_exposure, start_time, speed_m_min):
    max_streak = current_streak = 0
    elapsed = 0.0
    for i in range(len(path) - 1):
        u, v     = path[i], path[i + 1]
        edge_key = (u, v)
        if edge_key not in edge_exposure:
            current_streak = 0; continue
        info         = edge_info.get(edge_key, {})
        sorted_cells = edge_cells.get(info.get('edge_id'), [])
        n            = len(sorted_cells)
        if n == 0:
            continue
        cell_time = (info.get('len', 0) / n) / speed_m_min
        for col_idx, (_, cid) in enumerate(sorted_cells):
            arrival_t = min(round3(start_time + elapsed + col_idx * cell_time), 2000)
            val = exposure_by_cell.get(cid, {}).get(arrival_t, 0)
            if val:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        elapsed += info.get('len', 0) / speed_m_min
    return max_streak

# ══════════════════════════════════════════════════════════════════════════════
#  Plot  (light mode)
# ══════════════════════════════════════════════════════════════════════════════

def plot_graph_and_routes(pareto_paths, source, target, title,
                          source_xy=None, target_xy=None, pad_frac=0.05):
    fig, ax = plt.subplots(1, 1, figsize=(16, 11))
    ax.set_facecolor('#f7f7f7')
    fig.patch.set_facecolor('#ffffff')

    all_xs, all_zs = [], []
    for route in pareto_paths:
        for n in route['path']:
            if n in coord_map:
                all_xs.append(coord_map[n][0]); all_zs.append(coord_map[n][1])
    for pt in [source_xy, target_xy]:
        if pt: all_xs.append(pt[0]); all_zs.append(pt[1])
    for wp in [source, target]:
        if wp in coord_map:
            all_xs.append(coord_map[wp][0]); all_zs.append(coord_map[wp][1])

    x_pad = max((max(all_xs) - min(all_xs)) * pad_frac, 200)
    z_pad = max((max(all_zs) - min(all_zs)) * pad_frac, 200)
    xlim  = (min(all_xs) - x_pad, max(all_xs) + x_pad)
    zlim  = (min(all_zs) - z_pad, max(all_zs) + z_pad)

    def in_view(u):
        if u not in coord_map: return False
        x, z = coord_map[u]
        return xlim[0] <= x <= xlim[1] and zlim[0] <= z <= zlim[1]

    ax.add_collection(LineCollection(
        [[coord_map[u], coord_map[v]] for u, v in G_full.edges()
         if in_view(u) and v in coord_map],
        colors='#d0d8d0', linewidths=0.3, zorder=1))
    ax.add_collection(LineCollection(
        [[coord_map[u], coord_map[v]] for u, v in G.edges()
         if in_view(u) and v in coord_map],
        colors='#9dbf9d', linewidths=0.5, zorder=2))

    vis_xs = [c[3][0] for c in cells if xlim[0] <= c[3][0] <= xlim[1] and zlim[0] <= c[3][1] <= zlim[1]]
    vis_zs = [c[3][1] for c in cells if xlim[0] <= c[3][0] <= xlim[1] and zlim[0] <= c[3][1] <= zlim[1]]
    if vis_xs:
        ax.scatter(vis_xs, vis_zs, s=3, color='#2e7d32', zorder=3, alpha=0.7, label='Sample points')

    cmap = matplotlib.colormaps.get_cmap('plasma')
    for idx, route in enumerate(sorted(pareto_paths, key=lambda r: r['duration'])):
        color = cmap(idx / max(len(pareto_paths) - 1, 1))
        rxs = [coord_map[n][0] for n in route['path'] if n in coord_map]
        rzs = [coord_map[n][1] for n in route['path'] if n in coord_map]
        ax.plot(rxs, rzs, color=color, linewidth=2.5, zorder=5, alpha=0.9,
                label=(f"Route {idx+1}  |  Dur={route['duration']:.2f}m  |  "
                       f"Exp={route['exposure']:.0f}  |  Turns={route['turns']}"))

    def _draw_od(wp_id, xy_query, color, tag):
        if wp_id not in coord_map: return
        sx, sz = coord_map[wp_id]
        ax.scatter([sx], [sz], s=300, color=color, zorder=8,
                   edgecolors='black', linewidths=1.5, label=f'{tag} node (wp {wp_id})')
        ax.annotate(f'{tag}\n(wp {wp_id})', (sx, sz),
                    textcoords="offset points", xytext=(8, 8),
                    fontsize=9, fontweight='bold', color=color,
                    bbox=dict(boxstyle='round,pad=0.2', fc='#ffffff', alpha=0.7))
        if xy_query and xy_query != (sx, sz):
            rx, rz = xy_query
            ax.scatter([rx], [rz], s=160, color=color, zorder=7,
                       edgecolors='black', linewidths=1.2, marker='*',
                       label=f'{tag} (query point)')
            ax.plot([rx, sx], [rz, sz], color=color, linewidth=1.2,
                    linestyle='--', zorder=6, alpha=0.7)
            ax.annotate(f'{tag}*', (rx, rz), textcoords="offset points",
                        xytext=(7, -13), fontsize=9, color=color, style='italic')

    _draw_od(source, source_xy, '#1b7f4a', 'O')
    _draw_od(target, target_xy, '#c0392b', 'D')

    ax.set_xlim(xlim); ax.set_ylim(zlim)
    ax.legend(loc='upper left', fontsize=7.5, framealpha=0.85,
              facecolor='#ffffff', edgecolor='#cccccc', labelcolor='black')
    ax.set_title(title, fontsize=13, color='#111111', pad=12)
    ax.set_xlabel("Unity X", color='#333333')
    ax.set_ylabel("Unity Z", color='#333333')
    ax.tick_params(colors='#333333')
    for spine in ax.spines.values():
        spine.set_edgecolor('#cccccc')
    ax.set_aspect('equal')
    ax.text(0.5, -0.06,
            f"Full: {G_full.number_of_nodes():,} nodes  |  "
            f"Filtered: {G.number_of_nodes():,} nodes  |  "
            f"Pareto: {len(pareto_paths)}  |  O→wp{source}  D→wp{target}",
            transform=ax.transAxes, fontsize=8, color='#555555', ha='center')
    plt.tight_layout()
    safe_title = re.sub(r'[^\w\-]', '_', title)
    filepath   = os.path.join(OUTPUT_DIR, f"{safe_title}.png")
    plt.savefig(filepath, dpi=150, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved plot : {filepath}")

# ══════════════════════════════════════════════════════════════════════════════
#  CSV — UPDATED HEADER AND LOGIC
# ══════════════════════════════════════════════════════════════════════════════

CSV_HEADER = [
    'source_wp', 'target_wp',
    'date', 'start_time_min', 'start_time_hhmm',
    'rank', 'duration_min', 'exposure', 'turns', 'length_m',
    'max_streak', 'total_cells', 'num_nodes', 'path',
]

def wp_csv_path(source_wp, target_wp, run_date):
    # One CSV per unique waypoint pair — keyed by (source_wp, target_wp, date)
    # UUIDs have hyphens replaced with underscores; parts separated by -- for unambiguous parsing
    src = str(source_wp).replace('-', '_')
    tgt = str(target_wp).replace('-', '_')
    return os.path.join(OUTPUT_DIR, f"pareto_{src}--{tgt}--{run_date}.csv")

def write_timestamp_to_csv(writer, pareto_paths, run_date,
                           start_time, source_wp, target_wp):
    """Append all Pareto rows for one timestamp to an already-open CSV writer."""
    for rank, r in enumerate(pareto_paths, 1):
        total_len = 0
        total_cells = 0
        for i in range(len(r['path']) - 1):
            u, v = r['path'][i], r['path'][i+1]
            info = edge_info.get((u, v), {})
            total_len += info.get('len', 0)

            # Count the sample points (cells) for this edge
            edge_id = info.get('edge_id')
            if edge_id is not None:
                total_cells += len(edge_cells.get(edge_id, []))

        streak = max_consecutive_sunlit(r['path'], edge_exposure, start_time, SPEED)

        writer.writerow([
            source_wp, target_wp,
            run_date, start_time,
            f"{start_time//60:02d}:{start_time%60:02d}",
            rank,
            round(r['duration'], 6),
            round(r['exposure'], 1),
            r['turns'],
            round(total_len, 1),
            streak,
            total_cells,
            len(r['path']),
            ",".join(str(n) for n in r['path']),
        ])


# ══════════════════════════════════════════════════════════════════════════════
#  Summary OD map — all origins and destinations on full network
# ══════════════════════════════════════════════════════════════════════════════

def plot_od_summary(od_pairs, processed_od_snaps, run_date):
    """
    Plot the full network with all processed OD pairs as small dots.
    processed_od_snaps: list of (origin_ux, origin_uz, dest_ux, dest_uz)
    """
    fig, ax = plt.subplots(1, 1, figsize=(14, 20))
    ax.set_facecolor('#f7f7f7')
    fig.patch.set_facecolor('#ffffff')

    # Full network background
    ax.add_collection(LineCollection(
        [[coord_map[u], coord_map[v]] for u, v in G_full.edges()
         if u in coord_map and v in coord_map],
        colors='#d0d8d0', linewidths=0.3, zorder=1))
    ax.add_collection(LineCollection(
        [[coord_map[u], coord_map[v]] for u, v in G.edges()
         if u in coord_map and v in coord_map],
        colors='#c5d9c5', linewidths=0.5, zorder=2))

    # Origins (green) and destinations (red) as small dots
    if processed_od_snaps:
        ox = [s[0] for s in processed_od_snaps]
        oz = [s[1] for s in processed_od_snaps]
        dx = [s[2] for s in processed_od_snaps]
        dz = [s[3] for s in processed_od_snaps]
        ax.scatter(ox, oz, s=8, color='#1b7f4a', zorder=5, alpha=0.7, label=f'Origins ({len(ox)})')
        ax.scatter(dx, dz, s=8, color='#c0392b', zorder=5, alpha=0.7, label=f'Destinations ({len(dx)})')

    ax.autoscale()
    ax.set_aspect('equal')
    ax.legend(loc='upper left', fontsize=9, framealpha=0.9,
              facecolor='#ffffff', edgecolor='#cccccc')
    ax.set_title(f'OD Pair Coverage — {run_date} — {len(processed_od_snaps)} ODs processed',
                 fontsize=13, color='#111111', pad=12)
    ax.set_xlabel("Unity X", color='#333333')
    ax.set_ylabel("Unity Z", color='#333333')
    ax.tick_params(colors='#333333')
    for spine in ax.spines.values():
        spine.set_edgecolor('#cccccc')

    plt.tight_layout()
    filepath = os.path.join(OUTPUT_DIR, f'od_summary_{run_date}.png')
    plt.savefig(filepath, dpi=150, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f'  Saved OD summary plot: {filepath}')

# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    _SCRIPT_START = time.perf_counter()

    # ── Load OD pairs (for summary plot) and unique WP pairs (for Pareto) ───
    print(f"\n{'═'*70}")
    print("  Loading OD pairs and unique waypoint pairs")
    print(f"{'═'*70}")
    od_pairs     = load_od_pairs(OD_CSV_PATH, OD_SELECTION)
    unique_pairs = load_unique_wp_pairs(UNIQUE_WP_CSV)
    print(f"  → {len(od_pairs)} OD pair(s) | {len(unique_pairs):,} unique WP pairs\n")

    # ── Load static DB data ────────────────────────────────────────────────────
    print(f"\n{'═'*70}")
    print("  Loading static DB data")
    print(f"{'═'*70}")
    TIMER.reset()

    conn   = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()

    cursor.execute("SELECT id, ST_AsText(geom) FROM meo_waypoints;")
    waypoints_raw = cursor.fetchall()
    coord_map = {wp_id: parse_point(geom) for wp_id, geom in waypoints_raw}
    TIMER.tick(f"Loaded waypoints ({len(waypoints_raw):,})")

    cursor.execute("SELECT id, start_wp_id, end_wp_id, length FROM meo_edges;")
    edges_raw = cursor.fetchall()
    TIMER.tick(f"Loaded edges ({len(edges_raw):,})")

    cursor.execute("SELECT id, edge_id, sequence_index, ST_AsText(geom) FROM meo_sample_points;")
    cells_raw = cursor.fetchall()
    cells = [(cid, eid, seq, parse_point(geom)) for cid, eid, seq, geom in cells_raw]
    TIMER.tick(f"Loaded sample points ({len(cells_raw):,})")

    cursor.execute("SELECT DISTINCT date(datetime) FROM meo_exposure_samples ORDER BY 1;")
    all_dates = [row[0] for row in cursor.fetchall()]
    TIMER.tick(f"Fetched available dates ({len(all_dates)})")
    print(f"\n  Available dates : {all_dates}")

    if DATE_SELECTION is None:
        available_dates = all_dates
        print(f"  Running all {len(available_dates)} date(s).")
    elif isinstance(DATE_SELECTION, int):
        available_dates = [all_dates[DATE_SELECTION]]
        print(f"  Running date index {DATE_SELECTION} -> {available_dates[0]}")
    elif isinstance(DATE_SELECTION, str):
        from datetime import date as _date
        target_d = _date.fromisoformat(DATE_SELECTION)
        if target_d not in all_dates:
            raise ValueError(f"Date {DATE_SELECTION} not found in DB. Available: {all_dates}")
        available_dates = [target_d]
        print(f"  Running date: {available_dates[0]}")
    else:
        raise ValueError(f"Unsupported DATE_SELECTION type: {type(DATE_SELECTION)}")

    # ── Build static graph structures ──────────────────────────────────────────
    print(f"\n{'═'*70}")
    print("  Building static graph structures")
    print(f"{'═'*70}")
    TIMER.reset()

    edge_cells = defaultdict(list)
    for cid, eid, seq, _ in cells:
        edge_cells[eid].append((seq, cid))
    for eid in edge_cells:
        edge_cells[eid].sort()
    TIMER.tick("Built edge→cell index")

    edge_id_to_uv = {edge_id: (u, v) for edge_id, u, v, _ in edges_raw}

    G_full = nx.DiGraph()
    for edge_id, u, v, length in edges_raw:
        G_full.add_edge(u, v, weight=length)
        G_full.add_edge(v, u, weight=length)
    TIMER.tick(f"Built full graph ({G_full.number_of_nodes():,} nodes, {G_full.number_of_edges():,} edges)")

    edges_with_samples = set(edge_cells.keys())
    G = nx.DiGraph()
    edge_info = {}
    for edge_id, u, v, length in edges_raw:
        if edge_id not in edges_with_samples:
            continue
        G.add_edge(u, v, weight=length)
        edge_info[(u, v)] = {'len': length, 'edge_id': edge_id}
        G.add_edge(v, u, weight=length)
        edge_info[(v, u)] = {'len': length, 'edge_id': edge_id}
    TIMER.tick(
        f"Built filtered graph ({G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges) "
        f"[−{G_full.number_of_nodes()-G.number_of_nodes()} nodes, "
        f"−{G_full.number_of_edges()-G.number_of_edges()} edges vs full]"
    )

    undirected      = G.to_undirected()
    largest_comp    = max(nx.connected_components(undirected), key=len)
    TIMER.tick(f"Largest component: {len(largest_comp):,} nodes")

    angle_map = {}
    for edge_id, u, v, _ in edges_raw:
        if u in coord_map and v in coord_map:
            x1, y1 = coord_map[u]; x2, y2 = coord_map[v]
            angle_map[(u, v)] = math.degrees(math.atan2(y2 - y1, x2 - x1))
            angle_map[(v, u)] = math.degrees(math.atan2(y1 - y2, x1 - x2))
    TIMER.tick(f"Computed angle map ({len(angle_map):,} directed edges)")

    fast_adj_base = {node: [] for node in G.nodes()}
    for edge_id, u, v, length in edges_raw:
        if (u, v) in edge_info:
            fast_adj_base[u].append((v, length / SPEED, angle_map.get((u, v)), (u, v)))
        if (v, u) in edge_info:
            fast_adj_base[v].append((u, length / SPEED, angle_map.get((v, u)), (v, u)))
    TIMER.tick(f"Built fast_adj ({sum(len(v) for v in fast_adj_base.values()):,} entries)")

    # ── Outer loop: dates ──────────────────────────────────────────────────────
    for run_date in available_dates:
        print(f"\n{'═'*70}")
        print(f"  DATE: {run_date}")
        print(f"{'═'*70}")
        TIMER.reset()

        # Stream exposure rows for this date — never loads all 131M rows at once
        srv = conn.cursor('exposure_stream')
        srv.execute("""
            SELECT sample_point_id, datetime, is_sunlit
            FROM meo_exposure_samples
            WHERE datetime::date = %s;
        """, (run_date,))

        exposure_by_cell = defaultdict(dict)
        row_count = 0
        min_minute, max_minute = 9999, 0
        while True:
            batch = srv.fetchmany(10000)
            if not batch:
                break
            for cell_id, dt, is_sunlit in batch:
                minute = dt_to_minute(dt)
                exposure_by_cell[cell_id][minute] = int(is_sunlit)
                if minute < min_minute: min_minute = minute
                if minute > max_minute: max_minute = minute
            row_count += len(batch)
        srv.close()
        TIMER.tick(f"Streamed + built exposure_by_cell ({row_count:,} rows)")

        MIN_M, MAX_M = min_minute, max_minute
        print(f"  Exposure covers {MIN_M//60:02d}:{MIN_M%60:02d} – {MAX_M//60:02d}:{MAX_M%60:02d}")

        edge_exposure = precompute_edge_exposure(SPEED)
        TIMER.tick(f"Precomputed edge exposure ({len(edge_exposure):,} directed edges)")

        # ── Build processed_od_snaps for summary plot ───────────────────────────
        processed_od_snaps = [(od['origin_ux'], od['origin_uz'],
                                od['dest_ux'],   od['dest_uz']) for od in od_pairs]

        # ── Pre-compute lower bounds for all unique targets ────────────────────
        unique_targets = {tgt for (_, tgt) in unique_pairs}
        print(f"  Pre-computing lower bounds for {len(unique_targets):,} unique targets...")
        dur_lb_cache = {}
        exp_lb_cache = {}
        for i, tgt in enumerate(unique_targets, 1):
            dur_lb_cache[tgt] = compute_duration_lower_bounds(G, tgt, SPEED)
            exp_lb_cache[tgt] = compute_exposure_lower_bounds(G, tgt, edge_exposure)
            if i % 100 == 0 or i == len(unique_targets):
                print(f"    {i:,} / {len(unique_targets):,} targets done...", flush=True)
        TIMER.tick(f"✓ All lower bounds ready ({len(unique_targets):,} unique targets cached)")

        # ── Unique-pair loop — one CSV per (source_wp, target_wp) ─────────────
        total_pairs = len(unique_pairs)
        for pair_idx, (SOURCE, TARGET) in enumerate(unique_pairs, 1):
            TIMER.reset()

            dur_lb = dur_lb_cache[TARGET]
            exp_lb = exp_lb_cache[TARGET]

            dijkstra_best = dijkstra_duration_fast(fast_adj_base, SOURCE, TARGET)
            lb_best       = dur_lb.get(SOURCE, float('inf'))
            gap           = abs(dijkstra_best - lb_best)
            TIMER.tick(
                f"[{pair_idx}/{total_pairs}] {SOURCE[:8]}→{TARGET[:8]}  "
                f"Dijkstra={dijkstra_best:.4f}  LB={lb_best:.4f}  gap={gap:.2e}"
                + ("  ⚠ MISMATCH" if gap > 1e-8 else "  ✓")
            )

            # One CSV per unique waypoint pair — all timestamps written inside
            csv_file = wp_csv_path(SOURCE, TARGET, run_date)
            with open(csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADER)

                for START_TIME in START_TIMES:
                    pareto_paths = label_setting_pareto_fast(
                        fast_adj=fast_adj_base,
                        source=SOURCE, target=TARGET,
                        edge_exposure=edge_exposure,
                        start_time=START_TIME,
                        speed_m_min=SPEED,
                        delta=0.5, max_turns=15,
                        dur_lb=dur_lb, exp_lb=exp_lb,
                    )
                    pareto_paths.sort(key=lambda x: x['duration'])

                    if pareto_paths:
                        write_timestamp_to_csv(
                            writer, pareto_paths, run_date,
                            START_TIME, SOURCE, TARGET
                        )
                    else:
                        print(f"  ⚠  [{pair_idx}/{total_pairs}] No paths at {START_TIME//60:02d}:{START_TIME%60:02d}")

            if pair_idx % 1000 == 0 or pair_idx == total_pairs:
                print(f"  ✓ {pair_idx:,}/{total_pairs:,} pairs done  — last: {csv_file}")

        # ── Summary OD map for this date ──────────────────────────────────────
        TIMER.reset()
        plot_od_summary(od_pairs, processed_od_snaps, run_date)
        TIMER.tick(f"OD summary plot saved ({len(processed_od_snaps)} ODs)")

    cursor.close()
    conn.close()

    total_s = time.perf_counter() - _SCRIPT_START
    h = int(total_s // 3600)
    m = int((total_s % 3600) // 60)
    s = total_s % 60
    print(f"\n{'═'*70}")
    print("  Done.")
    print(f"  Total runtime: {h:02d}h {m:02d}m {s:05.2f}s  ({total_s:.1f}s)")
    print(f"{'═'*70}\n")