# Optimal route: Python (algorithm + API client)

The optimal route algorithm is implemented in **Python**. The script that **POSTs** the computed route to FastAPI (stored in PostgreSQL/Supabase) is in the repo root:

- **`scripts/post_optimal_route.py`** — POST optimal route to FastAPI (same JSON shape as before).

## Run (Python)

```bash
# From repo root: POST to https://sunlight-city-blush.vercel.app/api/optimal-route
python scripts/post_optimal_route.py

# Local server (uvicorn): no /api prefix
python scripts/post_optimal_route.py --base http://localhost:8000 --path /optimal-route

# Custom anonymous_id (match Web/Unity session)
python scripts/post_optimal_route.py --anonymous-id "your-session-id"
```

## Request body (JSON)

Matches FastAPI `OptimalRouteCreate`:

- `origin`: `{ "lat": number, "lng": number }`
- `destination`: `{ "lat", "lng" }`
- `waypoints`: array of `{ "lat", "lng" }`
- `total_distance_km`: optional float
- `total_time_minutes`: optional float
- `anonymous_id`: optional string (associate with Unity/Web session)
- `user_email`: optional string

## Integration with your algorithm

Replace the example `origin`, `destination`, `waypoints`, `total_distance_km`, `total_time_minutes` (and optionally `anonymous_id` / `user_email`) in `scripts/post_optimal_route.py` with the output of your Python pathfinding. You can also import `build_payload` and `post_optimal_route` from that script and call them from your algorithm module.
