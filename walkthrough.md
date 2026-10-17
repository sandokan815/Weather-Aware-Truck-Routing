# Walkthrough — Truck Safe Route Planner

Presentation outline in three parts:

1. [Third-party libraries and services](#1-third-party-libraries-and-services)
2. [Backend endpoints](#2-backend-endpoints)
3. [Frontend UI and the API calls behind each user action](#3-frontend-ui-and-api-calls-per-user-action)

**One-line pitch:** the user enters origin, destination, departure time and load weight. The app gets 3 route options and places a checkpoint every 10 / 25 / 50 miles along each one. At each checkpoint it estimates when the truck will arrive, looks up the forecast for that hour, and rates the risk using the load-weight rules. It then recommends the safest route.

---

## 1. Third-party libraries and services

### 1.1 Backend (Python) — `backend/requirements.txt`

| Library | Purpose in this project |
|---|---|
| **Django** | Web framework: settings, URL routing, request handling, and the in-memory cache (`LocMemCache`). The cache stores geocoding results (24 h), weather series (30 min) and planned-trip corridor data (1 h). No database is used. |
| **djangorestframework (DRF)** | Builds the JSON API. `APIView` classes handle the endpoints, and `PlanTripSerializer` validates input (lat/lon ranges, load 0–80,000 lb, departure window). Configured for JSON output only, with no authentication. |
| **django-cors-headers** | Lets the frontend call the API from another origin when the frontend is hosted separately (`CORS_ALLOWED_ORIGINS`). In development this isn't needed because Vite proxies `/api`. |
| **python-dotenv** | Loads `backend/.env`, which holds the provider choice, service URLs, timeouts, user agent, and the mock-fallback switch. |
| **requests** | HTTP client for every external call: routing (OSRM), geocoding (Photon / Nominatim) and weather (Open-Meteo). |
| **gunicorn** | Production WSGI server for deployment (Linux/macOS only; skipped on Windows). |

Standard library worth mentioning: `concurrent.futures.ThreadPoolExecutor` runs the routing requests in parallel, and the weather batches too, so one plan takes about as long as a single round trip.

### 1.2 Frontend (JavaScript) — `frontend/package.json`

| Library | Purpose in this project |
|---|---|
| **React 19** + **react-dom** | UI components and state (form, selected route, slider hour, heatmap settings). |
| **Leaflet** | Map engine: tiles, polylines, markers, canvas-rendered heatmap circles, and distance math (`latLng.distanceTo`) for placing the truck marker. |
| **react-leaflet** | React components on top of Leaflet: `MapContainer`, `TileLayer`, `Polyline`, `CircleMarker`, `Marker`, `Popup`, `Tooltip`, `useMap`. |
| **axios** | HTTP client in `src/api.js`: one shared instance (`/api` base URL, 60 s timeout), cancellation of stale autocomplete requests (`AbortController`), and readable error messages. |
| **Vite** (dev) + **@vitejs/plugin-react** | Dev server with hot reload, production build, and an `/api` → `http://127.0.0.1:8000` proxy so there's no CORS setup in development. |
| **Tailwind CSS v4** + **@tailwindcss/vite** (dev) | Utility-class styling for the whole UI. |

### 1.3 External services (all free, no API keys)

| Service | Used for | Called from |
|---|---|---|
| **OSRM** (`router.project-osrm.org`) | Driving routes + alternatives, including the via-point requests | Backend, `routing.py` |
| **Photon** (`photon.komoot.io`) | Address autocomplete while the user types; fallback if Nominatim fails | Backend, `geocoding.py` |
| **Nominatim** (`nominatim.openstreetmap.org`) | Address lookup when "Plan" is clicked and no suggestion was picked; fallback if Photon fails | Backend, `geocoding.py` |
| **Open-Meteo** (`api.open-meteo.com`) | Hourly forecast at each checkpoint: wind, gusts, rain, showers, snowfall, temperature, weather code. Many coordinates per request, batched 20 at a time | Backend, `weather.py` |
| **OpenStreetMap tiles** (`tile.openstreetmap.org`) | Map background | Browser (Leaflet `TileLayer`) |

**Resilience:** if OSRM or Open-Meteo fails, the backend falls back to simulated routes or weather (`ALLOW_MOCK_FALLBACK=true`) and shows a warning in the UI. `WEATHER_PROVIDER=mock` runs a fixed simulated storm, which is useful for a demo.

---

## 2. Backend endpoints

All endpoints are under `/api/` ([trip_planner/urls.py](backend/trip_planner/urls.py) → [routes/urls.py](backend/routes/urls.py)) and are implemented in [routes/views.py](backend/routes/views.py).

| Method | Path | View | Purpose |
|---|---|---|---|
| GET | `/api/health` | `HealthView` | Liveness check → `{"status": "ok"}` |
| GET | `/api/geocode?q=…&autocomplete=1` | `GeocodeView` | Address search / type-ahead |
| POST | `/api/plan-trip` | `PlanTripView` | The main pipeline: 3 routes, checkpoints, ETA, weather, risk, recommendation |


### 2.1 `GET /api/health`
Returns `{"status": "ok"}`. Used for deployment health checks.

### 2.2 `GET /api/geocode`
- **Params:** `q` (at least 3 characters), `autocomplete` (`1` / `0`).
- **Logic** ([services/geocoding.py](backend/routes/services/geocoding.py)): checks the cache first. If there's no hit, it calls the providers in order (Photon for autocomplete, Nominatim otherwise, the other as fallback), filters by country (`us,ca,mx`), and caches the result for 24 h.
- **Response:** `{"results": [{"label": "Denver, Colorado, USA", "lat": 39.74, "lon": -104.99}, …]}`

### 2.3 `POST /api/plan-trip` — the core endpoint
**Request:**
```json
{ "origin_lat": 34.0522, "origin_lon": -118.2437,
  "dest_lat": 39.7392, "dest_lon": -104.9903,
  "departure_iso": "2026-10-16T15:00:00Z",
  "load_weight_lb": 40500 }
```

**Validation** (`PlanTripSerializer`): coordinates in range, load from 0 to 80,000 lb, departure no more than 2 days in the past and no more than 13 days ahead (the forecast horizon), origin ≠ destination, straight-line distance ≤ 3,500 mi. Invalid input returns `400` with errors per field.

**Pipeline** ([services/planner.py](backend/routes/services/planner.py)):

1. **Routes** ([routing.py](backend/routes/services/routing.py)): asks for the primary route with native alternatives. In parallel, it asks for routes forced through 4 "via" points offset to the side of the straight origin→destination line. Then it drops near-duplicates (more than 85% overlap) and detours more than 60% slower than the fastest route, and keeps the 3 fastest distinct routes.
2. **Sampling interval, chosen automatically** ([geo.py](backend/routes/services/geo.py) `auto_sample_miles`): based on the longest route. Up to 300 mi → every **10 mi**, up to 1,000 mi → every **25 mi**, longer → every **50 mi**. All 3 routes use the same spacing so they compare fairly.
3. **Checkpoints:** mile markers 0, N, 2N, … plus the destination, mapped onto the route geometry.
4. **ETA per checkpoint:** `departure + (mile / total_miles) × total_duration`.
5. **Weather:** one batched Open-Meteo fetch covers every checkpoint of every route for the whole window, departure → departure + max(48 h, longest trip). It converts km/h → mph, mm → in/hr, cm snow → in/hr. Each checkpoint takes the forecast hour closest to its ETA.
6. **Risk** ([risk.py](backend/routes/services/risk.py)): each of wind, rain and snow is scored on a 1–5 scale (Low, Moderate, High, Severe, No Travel). The checkpoint gets the worst of the three, then the **load rules** apply: 45–54 mph with more than 30k lb → No Travel; 35–44 mph with more than 40k lb → Severe; 55 mph or more → No Travel at any load. The rules only ever raise the risk, never lower it.
7. **Route summary:** each checkpoint counts for half of the road segment before it and half after, so the miles per risk level add up to the route's total. Also computes a mile-weighted average risk and the worst level.
8. **Recommendation:** ranks the routes by 4 criteria in order: ① fewest Severe + No-Travel miles → ② fewest High miles → ③ lowest average risk → ④ shortest travel time. It writes a readable reason naming the criterion that decided it.
9. **Corridor heatmap data:** for every checkpoint, 49 hourly values (hour 0–48) of risk, wind, rain and snow. Cached under a `trip_id` for 1 h.

**Response (abridged):** `trip_id`, `sample_miles`, `routes[]` (geometry, totals, `summary`, `checkpoints[]` with `eta_iso`, `weather`, `risk`), `recommended_route_id`, `ranking`, `recommendation_reason`, `corridor`, `data_sources`, `warnings`, `timing_ms`.

**Errors:** `502` if routing or weather fails and fallback is turned off. `500` with a generic message for anything unexpected; stack traces are never sent to the client.


---

## 3. Frontend UI and API calls per user action

**Layout** ([App.jsx](frontend/src/App.jsx)): a left sidebar holds the form, warnings, route cards and checkpoint table. On the right is a full-height map with the forecast slider overlaid at the bottom. Every API call goes through [src/api.js](frontend/src/api.js), which has only two functions: `geocode()` and `planTrip()`.

### Components

| Component | What it shows |
|---|---|
| `TripForm` | Origin, Destination (with ⇅ Swap), Departure (+ "Now"), Load weight, **Plan safest route**, "Fill example" |
| `AddressInput` | Text box with an autocomplete dropdown, keyboard navigation, and a ✓ once a place is confirmed |
| `RouteSummary` | Three route cards (distance, drive time, average risk, worst level, risk bar, ★ recommended, reason) plus a checkpoint table for the selected route |
| `RouteMap` | Route lines (recommended / selected / other), checkpoint dots colored by risk with popups, A/B markers, truck marker, heatmap |
| `ForecastSlider` | 0–48 h slider, ▶ Play, heatmap on/off, metric (risk / wind / rain / snow), scope (selected / all routes) |
| `Legend` | Collapsible key for risk colors and route line styles |

### User actions → what happens

| # | User action | API call | What happens |
|---|---|---|---|
| 1 | **Types in Origin / Destination** (3+ characters) | `GET /api/geocode?q=…&autocomplete=1` | Waits 400 ms after the last keystroke, then sends the request. The previous request is cancelled with `AbortController`, so an old response can't replace a newer one. Shows the suggestion list. |
| 2 | **Picks a suggestion** (click or ↑/↓ + Enter) | — | Saves `{label, lat, lon}` and shows ✓. No more lookups for that field. |
| 3 | **Clicks ⇅ Swap / "Now" / "Fill example"** | — | Local state only. The example fills in LA → Denver with known coordinates and 40,500 lb. |
| 4 | **Clicks "Plan safest route"** | Maybe `GET /api/geocode?q=…` (no autocomplete), then `POST /api/plan-trip` | Checks load weight locally (0–80,000). If an address was typed but no suggestion was picked, it looks it up and takes the top match. Then it sends `planTrip` with coordinates, departure (ISO) and load. The button shows a spinner while waiting. |
| 5 | **Response arrives** | — | Stores the result, selects the recommended route, resets the slider to hour 0, and fits the map to all routes. Shows any `warnings` (for example, simulated data was used) and a footer line: *Checkpoints every N mi · Routing · Weather · time taken*. |
| 6 | **Request fails** | — | `errorMessage()` turns the error into readable text: field validation messages, the server's `error`, a timeout, or "Cannot reach the server". It appears in a red box. |
| 7 | **Clicks a route card or a route line on the map** | — | Changes the selected route: highlights the line, switches the checkpoint table, moves the truck marker, and filters the heatmap when scope is "selected". |
| 8 | **Clicks a checkpoint row in the table** | — | The map centers and zooms on that checkpoint and opens its popup (ETA, weather, risk factors, load-rule flag). |
| 9 | **Clicks a checkpoint dot on the map** | — | Opens the same popup. |
| 10 | **Drags the forecast slider / presses ▶ Play** | — | Uses `result.corridor` already in memory, so no extra request. Heatmap circles are recolored for that hour, and the truck marker moves to where it would be *hour* hours after departure (a fraction of drive time along the route). Play advances one hour every 450 ms. |
| 11 | **Changes metric / scope / heatmap toggle** | — | Local state only. Redraws the heatmap from the same data. |

**Main point for the audience:** one user action, **Plan safest route**, triggers the single heavy request. After that, everything interactive (switching routes, inspecting checkpoints, scrubbing the 48 h forecast) runs on the client from that one response. Autocomplete is the only other network traffic, and it's debounced, cancellable and cached on the server.

### Request flow (end to end)

```
Browser (React)                Django API                     External services
───────────────                ──────────                     ─────────────────
type address ──GET /geocode──► cache? ─miss─► Photon / Nominatim
             ◄── suggestions ─┘
Plan ───────POST /plan-trip──► validate
                               routes (parallel) ───────────► OSRM (+ via points)
                               auto sample 10/25/50
                               checkpoints + ETA
                               weather (batched, parallel) ─► Open-Meteo
                               risk + load rules
                               summary + recommendation
             ◄── JSON (routes, checkpoints, corridor) ─┘
slider / clicks: client-side only
```
