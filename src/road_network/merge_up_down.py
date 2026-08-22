import argparse
import json
import math
import os
import struct
from dataclasses import dataclass


def read_7bit_int(f):
    value = 0
    shift = 0
    while True:
        b = f.read(1)
        if not b:
            raise EOFError("Unexpected EOF while reading 7-bit encoded int")
        byte = b[0]
        value |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return value
        shift += 7


def read_cache_header(path):
    with open(path, "rb") as f:
        strlen = read_7bit_int(f)
        magic = f.read(strlen).decode("utf-8")
        if magic != "RGP1":
            raise ValueError(f"{path}: unexpected cache magic {magic!r}")

        min_x, max_x, min_z, max_z = struct.unpack("<4f", f.read(16))
        cell_size, min_triangle_up_dot = struct.unpack("<2f", f.read(8))
        dilation_iterations = struct.unpack("<i", f.read(4))[0]
        grid_width, grid_height = struct.unpack("<2i", f.read(8))
        origin_x, origin_y = struct.unpack("<2f", f.read(8))

    return {
        "min_x": min_x,
        "max_x": max_x,
        "min_z": min_z,
        "max_z": max_z,
        "cell_size": cell_size,
        "min_triangle_up_dot": min_triangle_up_dot,
        "dilation_iterations": dilation_iterations,
        "grid_width": grid_width,
        "grid_height": grid_height,
        "origin_x": origin_x,
        "origin_y": origin_y,
    }


def compute_bbox(vertices):
    xs = [p[0] for p in vertices]
    zs = [p[2] for p in vertices]
    return {
        "min_x": min(xs),
        "max_x": max(xs),
        "min_z": min(zs),
        "max_z": max(zs),
    }


def read_graph(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    vertices = [(float(v["x"]), float(v["y"]), float(v["z"])) for v in data["vertices"]]
    edges = [(int(e["from"]), int(e["to"])) for e in data["edges"]]
    return vertices, edges


def undirected_key(a, b):
    return (a, b) if a < b else (b, a)


def sqr_distance(a, b):
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    dz = a[2] - b[2]
    return dx * dx + dy * dy + dz * dz


def convex_hull(points):
    pts = sorted(set(points))
    if len(pts) <= 1:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def min_area_bbox(points):
    pts = [(p[0], p[2]) for p in points]
    hull = convex_hull(pts)
    if len(hull) == 0:
        return []
    if len(hull) == 1:
        x, y = hull[0]
        return [(x, y), (x, y), (x, y), (x, y)]

    best = None
    m = len(hull)
    for i in range(m):
        x0, y0 = hull[i]
        x1, y1 = hull[(i + 1) % m]
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy)
        if length <= 1e-8:
            continue

        ux = dx / length
        uy = dy / length
        vx = -uy
        vy = ux

        min_u = float("inf")
        max_u = float("-inf")
        min_v = float("inf")
        max_v = float("-inf")
        for x, y in hull:
            pu = x * ux + y * uy
            pv = x * vx + y * vy
            min_u = min(min_u, pu)
            max_u = max(max_u, pu)
            min_v = min(min_v, pv)
            max_v = max(max_v, pv)

        area = (max_u - min_u) * (max_v - min_v)
        if best is None or area < best[0]:
            best = (area, ux, uy, vx, vy, min_u, max_u, min_v, max_v)

    _, ux, uy, vx, vy, min_u, max_u, min_v, max_v = best
    corners = []
    for pu, pv in [(min_u, min_v), (max_u, min_v), (max_u, max_v), (min_u, max_v)]:
        corners.append((pu * ux + pv * vx, pu * uy + pv * vy))
    return corners


def point_segment_distance_2d(px, py, ax, ay, bx, by):
    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay
    denom = abx * abx + aby * aby
    if denom <= 1e-8:
        dx = px - ax
        dy = py - ay
        return math.hypot(dx, dy)
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / denom))
    qx = ax + t * abx
    qy = ay + t * aby
    dx = px - qx
    dy = py - qy
    return math.hypot(dx, dy)


def near_oriented_boundary(p, corners, margin):
    if len(corners) < 4:
        return False
    x, _, z = p
    for i in range(4):
        ax, ay = corners[i]
        bx, by = corners[(i + 1) % 4]
        if point_segment_distance_2d(x, z, ax, ay, bx, by) <= margin:
            return True
    return False


def bbox_distance(a, b):
    dx = max(0.0, a["min_x"] - b["max_x"], b["min_x"] - a["max_x"])
    dz = max(0.0, a["min_z"] - b["max_z"], b["min_z"] - a["max_z"])
    return math.hypot(dx, dz)


@dataclass
class Part:
    name: str
    bbox: dict
    obb: list
    vertices: list
    edges: list
    boundary_local_ids: list
    endpoint_local_ids: list


def quantize_point(p, tol):
    return (
        round(p[0] / tol),
        round(p[1] / tol),
        round(p[2] / tol),
    )


def build_global_graph(parts, merge_tolerance):
    global_vertices = []
    point_to_global = {}
    per_part_map = {}
    undirected_edges = set()

    for part in parts:
        local_to_global = {}
        for i, p in enumerate(part.vertices):
            key = quantize_point(p, merge_tolerance)
            gid = point_to_global.get(key)
            if gid is None:
                gid = len(global_vertices)
                global_vertices.append(p)
                point_to_global[key] = gid
            local_to_global[i] = gid

        for a, b in part.edges:
            ga = local_to_global[a]
            gb = local_to_global[b]
            if ga != gb:
                undirected_edges.add(undirected_key(ga, gb))

        per_part_map[part.name] = local_to_global

    return global_vertices, undirected_edges, per_part_map


def find_endpoint_stitch_edges(parts, per_part_map, max_bbox_gap, connect_distance):
    connect_distance_sq = connect_distance * connect_distance
    stitch_edges = set()

    endpoints = []
    for i in range(len(parts)):
        for local_id in parts[i].endpoint_local_ids:
            endpoints.append((i, local_id))

    for i in range(len(endpoints)):
        part_i, local_i = endpoints[i]
        pi = parts[part_i]
        p_i = pi.vertices[local_i]

        for j in range(i + 1, len(endpoints)):
            part_j, local_j = endpoints[j]
            if part_i == part_j:
                continue

            pj = parts[part_j]
            if bbox_distance(pi.bbox, pj.bbox) > max_bbox_gap:
                continue

            p_j = pj.vertices[local_j]
            if sqr_distance(p_i, p_j) > connect_distance_sq:
                continue

            gi = per_part_map[pi.name][local_i]
            gj = per_part_map[pj.name][local_j]
            if gi != gj:
                stitch_edges.add(undirected_key(gi, gj))

    return stitch_edges


def write_graph(path, vertices, undirected_edges):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    directed_edges = []
    for a, b in sorted(undirected_edges):
        directed_edges.append({"from": a, "to": b})
        directed_edges.append({"from": b, "to": a})

    data = {
        "vertices": [
            {"id": i, "x": p[0], "y": p[1], "z": p[2]}
            for i, p in enumerate(vertices)
        ],
        "edges": directed_edges,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))


def load_part(folder, boundary_margin):
    cache_path = os.path.join(folder, "road_graph_preprocess_cache.bin")
    graph_path = os.path.join(folder, "road_graph.json")
    vertices, edges = read_graph(graph_path)
    bbox = read_cache_header(cache_path) if os.path.exists(cache_path) else compute_bbox(vertices)
    obb = min_area_bbox(vertices)
    adj = [set() for _ in range(len(vertices))]
    for a, b in edges:
        if a != b:
            adj[a].add(b)

    boundary_local_ids = [
        i for i, p in enumerate(vertices)
        if near_oriented_boundary(p, obb, boundary_margin)
    ]
    endpoint_local_ids = [i for i in boundary_local_ids if len(adj[i]) > 0]

    return Part(
        name=os.path.basename(folder.rstrip("\\/")),
        bbox=bbox,
        obb=obb,
        vertices=vertices,
        edges=edges,
        boundary_local_ids=boundary_local_ids,
        endpoint_local_ids=endpoint_local_ids,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--parts",
        nargs="+",
        default=["down_city", "up_city"],
    )
    parser.add_argument("--boundary-margin", type=float, default=50.0)
    parser.add_argument("--connect-distance", type=float, default=50.0)
    parser.add_argument("--max-bbox-gap", type=float, default=260.0)
    parser.add_argument("--merge-tolerance", type=float, default=0.01)
    parser.add_argument("--output", default=os.path.join("up_down_city", "road_graph.json"))
    args = parser.parse_args()

    parts = [load_part(folder, args.boundary_margin) for folder in args.parts]
    vertices, undirected_edges, per_part_map = build_global_graph(parts, args.merge_tolerance)
    endpoint_stitch_edges = find_endpoint_stitch_edges(
        parts,
        per_part_map,
        args.max_bbox_gap,
        args.connect_distance,
    )
    undirected_edges |= endpoint_stitch_edges
    write_graph(args.output, vertices, undirected_edges)

    print(
        f"parts={len(parts)} vertices={len(vertices)} edges={len(undirected_edges) * 2} "
        f"endpoint_stitches={len(endpoint_stitch_edges) * 2}"
    )
    for part in parts:
        print(
            f"{part.name}: boundary_points={len(part.boundary_local_ids)} "
            f"endpoint_candidates={len(part.endpoint_local_ids)}"
        )
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
