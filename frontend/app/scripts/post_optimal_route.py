#!/usr/bin/env python3
"""
POST optimal route to FastAPI; FastAPI stores it in PostgreSQL (Supabase).
The optimal route algorithm is implemented in Python; this script sends the result to the Web API.

Usage:
  python scripts/post_optimal_route.py
  python scripts/post_optimal_route.py --base http://localhost:8000 --path /optimal-route
"""
import argparse
import json
import urllib.request
import urllib.error
import sys


def build_payload(origin, destination, waypoints, total_distance_km=None, total_time_minutes=None, anonymous_id=None, user_email=None):
    """Build JSON body matching FastAPI OptimalRouteCreate."""
    payload = {
        "origin": {"lat": origin["lat"], "lng": origin["lng"]},
        "destination": {"lat": destination["lat"], "lng": destination["lng"]},
        "waypoints": [{"lat": p["lat"], "lng": p["lng"]} for p in waypoints],
    }
    if total_distance_km is not None:
        payload["total_distance_km"] = total_distance_km
    if total_time_minutes is not None:
        payload["total_time_minutes"] = total_time_minutes
    if anonymous_id:
        payload["anonymous_id"] = anonymous_id
    if user_email:
        payload["user_email"] = user_email
    return payload


def post_optimal_route(base_url, path, payload):
    url = base_url.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
            print(body)
            return resp.status in (200, 201)
    except urllib.error.HTTPError as e:
        print(e.read().decode(), file=sys.stderr)
        print(f"HTTP {e.code}", file=sys.stderr)
        return False
    except Exception as e:
        print(str(e), file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="POST optimal route to FastAPI")
    parser.add_argument(
        "--base",
        default="https://sunlight-city-blush.vercel.app",
        help="API base URL (default: Vercel production)",
    )
    parser.add_argument(
        "--path",
        default="/api/optimal-route",
        help="Endpoint path (default: /api/optimal-route; use /optimal-route for local uvicorn)",
    )
    parser.add_argument("--anonymous-id", default="unity-session-123", help="anonymous_id for Web/Unity session")
    args = parser.parse_args()

    # Example: route from A to B with two waypoints (replace with your algorithm output)
    origin = {"lat": 39.9042, "lng": 116.4074}
    destination = {"lat": 39.9163, "lng": 116.3972}
    waypoints = [
        {"lat": 39.9080, "lng": 116.4040},
        {"lat": 39.9120, "lng": 116.4000},
    ]
    total_distance_km = 2.5
    total_time_minutes = 8.0

    payload = build_payload(
        origin,
        destination,
        waypoints,
        total_distance_km=total_distance_km,
        total_time_minutes=total_time_minutes,
        anonymous_id=args.anonymous_id,
    )
    ok = post_optimal_route(args.base, args.path, payload)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
