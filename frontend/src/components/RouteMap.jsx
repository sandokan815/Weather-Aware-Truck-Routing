import { useEffect, useMemo, useRef } from 'react'
import L from 'leaflet'
import { CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { formatDateTime, HEAT_METRICS, riskColor, ROUTE_COLORS } from '../risk'
import Legend from './Legend'

const US_CENTER = [39.5, -98.35]
// Basemap tiles; override with VITE_TILE_URL (e.g. a Mapbox / CARTO style URL).
const TILE_URL = import.meta.env.VITE_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const TILE_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
const MI_TO_M = 1609.344

function routeColor(route, selectedId) {
  if (route.recommended) return ROUTE_COLORS.recommended
  return route.id === selectedId ? ROUTE_COLORS.selected : ROUTE_COLORS.other
}

/** Fit the map to all routes whenever a new trip result arrives. */
function FitToResult({ result }) {
  const map = useMap()
  useEffect(() => {
    if (!result) return
    const bounds = L.latLngBounds(result.routes.flatMap((r) => r.coordinates))
    map.fitBounds(bounds, { padding: [40, 40] })
  }, [result, map])
  return null
}

/**
 * Weather heatmap along the corridor. Circles are created once per trip /
 * scope (imperatively, on a canvas renderer) and only restyled when the slider
 * moves, so dragging the slider stays smooth even with hundreds of cells.
 */
function HeatLayer({ frames, hour, metric, radiusMiles }) {
  const map = useMap()
  const circlesRef = useRef([])

  useEffect(() => {
    // Own pane below the route lines (overlayPane z-index is 400).
    if (!map.getPane('heat')) map.createPane('heat').style.zIndex = 350
    const renderer = L.canvas({ pane: 'heat', padding: 0.3 })
    const group = L.layerGroup().addTo(map)
    circlesRef.current = frames.map((f) =>
      L.circle([f.lat, f.lon], { radius: radiusMiles * MI_TO_M, stroke: false, renderer, interactive: false, fillOpacity: 0 }).addTo(group),
    )
    return () => {
      group.remove()
      circlesRef.current = []
    }
  }, [frames, radiusMiles, map])

  useEffect(() => {
    const m = HEAT_METRICS[metric]
    frames.forEach((f, i) => {
      const h = Math.min(hour, f.risk.length - 1)
      const intensity = m.intensity(f, h)
      circlesRef.current[i]?.setStyle({
        fillColor: riskColor(m.level(f, h)),
        fillOpacity: 0.1 + 0.45 * intensity,
      })
    })
  }, [frames, hour, metric, radiusMiles])

  return null
}

/** Position along a polyline at fraction t (0..1) of its length. */
function pointAlong(coords, cum, t) {
  const target = t * cum[cum.length - 1]
  let i = cum.findIndex((d) => d >= target)
  if (i <= 0) return coords[Math.max(0, i)]
  const seg = cum[i] - cum[i - 1] || 1
  const f = (target - cum[i - 1]) / seg
  return [coords[i - 1][0] + (coords[i][0] - coords[i - 1][0]) * f, coords[i - 1][1] + (coords[i][1] - coords[i - 1][1]) * f]
}

function cumulative(coords) {
  const cum = [0]
  for (let i = 1; i < coords.length; i++) {
    cum.push(cum[i - 1] + L.latLng(coords[i - 1]).distanceTo(L.latLng(coords[i])))
  }
  return cum
}

const truckIcon = L.divIcon({
  className: 'plain-div-icon',
  html: '<div style="font-size:22px;line-height:28px;width:30px;height:30px;text-align:center;background:#fff;border:2px solid #0f766e;border-radius:50%;box-shadow:0 2px 6px rgba(0,0,0,.35)">🚚</div>',
  iconSize: [30, 30],
  iconAnchor: [15, 15],
})

const endpointIcon = (letter, color) =>
  L.divIcon({
    className: 'plain-div-icon',
    html: `<div style="background:${color};color:#fff;font-weight:700;font-size:13px;width:28px;height:28px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);display:flex;align-items:center;justify-content:center;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.4)"><span style="transform:rotate(45deg)">${letter}</span></div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 28],
  })
const originIcon = endpointIcon('A', '#0f172a')
const destIcon = endpointIcon('B', '#0f766e')

function CheckpointPopup({ cp }) {
  const w = cp.weather
  return (
    <div className="min-w-[190px]">
      <div className="mb-1 flex items-center justify-between gap-3">
        <strong className="text-sm">Mile {cp.mile}</strong>
        <span className="rounded px-1.5 py-0.5 text-[11px] font-semibold text-white" style={{ background: riskColor(cp.risk.level) }}>
          {cp.risk.label}
        </span>
      </div>
      <div className="text-slate-500">ETA {formatDateTime(cp.eta_iso)}</div>
      <table className="my-1.5 w-full">
        <tbody>
          <tr><td>Wind</td><td className="text-right font-medium">{w.wind_mph} mph <span className="text-slate-400">(gust {w.gust_mph})</span></td><td className="pl-2 text-right text-slate-500">{cp.risk.factors.wind}</td></tr>
          <tr><td>Rain</td><td className="text-right font-medium">{w.rain_in_hr} in/hr</td><td className="pl-2 text-right text-slate-500">{cp.risk.factors.rain}</td></tr>
          <tr><td>Snow</td><td className="text-right font-medium">{w.snow_in_hr} in/hr</td><td className="pl-2 text-right text-slate-500">{cp.risk.factors.snow}</td></tr>
          <tr><td>Temp</td><td className="text-right font-medium">{w.temp_f} °F</td><td className="pl-2 text-right text-slate-500">{w.description}</td></tr>
        </tbody>
      </table>
      <div className={`text-[11px] ${cp.risk.load_adjusted ? 'font-semibold text-red-700' : 'text-slate-500'}`}>{cp.risk.reason}</div>
      <div className="mt-1 text-[10px] text-slate-400">{cp.lat.toFixed(3)}, {cp.lon.toFixed(3)}</div>
    </div>
  )
}

/** Pan to + open the popup of a checkpoint chosen in the side table. */
function FocusCheckpoint({ focus, markerRefs }) {
  const map = useMap()
  useEffect(() => {
    if (!focus) return
    map.setView([focus.cp.lat, focus.cp.lon], Math.max(map.getZoom(), 8))
    markerRefs.current[focus.cp.index]?.openPopup()
  }, [focus, map, markerRefs])
  return null
}

export default function RouteMap({ result, selectedId, onSelect, hour, heatMetric, heatScope, showHeat, focus, loading }) {
  const markerRefs = useRef({})
  const selected = result?.routes.find((r) => r.id === selectedId)

  // Draw unselected routes first so the selected one sits on top.
  const orderedRoutes = useMemo(
    () => (result ? [...result.routes].sort((a, b) => (a.id === selectedId) - (b.id === selectedId)) : []),
    [result, selectedId],
  )

  const heatFrames = useMemo(() => {
    if (!result) return []
    const byRoute = result.corridor.routes
    if (heatScope === 'all') return Object.values(byRoute).flat()
    return byRoute[String(selectedId)] || []
  }, [result, selectedId, heatScope])

  // Where the truck is `hour` hours after departure on the selected route.
  const selectedCum = useMemo(() => (selected ? cumulative(selected.coordinates) : null), [selected])
  const truck = useMemo(() => {
    if (!selected) return null
    const t = Math.min(1, (hour * 60) / selected.total_duration_min)
    return {
      pos: pointAlong(selected.coordinates, selectedCum, t),
      mile: Math.round(t * selected.total_miles),
      arrived: t >= 1,
    }
  }, [selected, selectedCum, hour])

  return (
    <div className="relative h-full w-full">
      <MapContainer center={US_CENTER} zoom={4} className="h-full w-full" preferCanvas zoomControl={false}>
        <TileLayer attribution={TILE_ATTRIBUTION} url={TILE_URL} />
        <FitToResult result={result} />

        {result && showHeat && heatFrames.length > 0 && (
          <HeatLayer frames={heatFrames} hour={hour} metric={heatMetric} radiusMiles={Math.max(12, result.sample_miles * 0.7)} />
        )}

        {orderedRoutes.map((r) => {
          const isSel = r.id === selectedId
          return [
            isSel && <Polyline key={`${r.id}-casing`} positions={r.coordinates} pathOptions={{ color: '#fff', weight: 10, opacity: 0.9 }} interactive={false} />,
            <Polyline
              key={`${r.id}-line`}
              positions={r.coordinates}
              pathOptions={{
                color: routeColor(r, selectedId),
                weight: isSel ? 6 : 4,
                opacity: isSel ? 1 : 0.75,
                dashArray: isSel || r.recommended ? null : '8 8',
              }}
              eventHandlers={{ click: () => onSelect(r.id) }}
            >
              <Tooltip sticky>
                <strong>{r.name}</strong>
                {r.recommended ? ' ★ recommended' : ''}
                <br />
                {Math.round(r.total_miles)} mi · avg risk {r.summary.avg_risk_score.toFixed(2)} · click to select
              </Tooltip>
            </Polyline>,
          ]
        })}

        {selected?.checkpoints.map((cp) => (
          <CircleMarker
            key={`${selected.id}-${cp.index}`}
            ref={(el) => (markerRefs.current[cp.index] = el)}
            center={[cp.lat, cp.lon]}
            radius={cp.risk.level >= 4 ? 7 : 5.5}
            pathOptions={{ color: '#fff', weight: 1.5, fillColor: riskColor(cp.risk.level), fillOpacity: 1 }}
          >
            <Popup>
              <CheckpointPopup cp={cp} />
            </Popup>
          </CircleMarker>
        ))}
        <FocusCheckpoint focus={focus} markerRefs={markerRefs} />

        {result && (
          <>
            <Marker position={[result.origin.lat, result.origin.lon]} icon={originIcon}>
              <Tooltip direction="top" offset={[0, -26]}>Origin</Tooltip>
            </Marker>
            <Marker position={[result.destination.lat, result.destination.lon]} icon={destIcon}>
              <Tooltip direction="top" offset={[0, -26]}>Destination</Tooltip>
            </Marker>
          </>
        )}

        {truck && (
          <Marker position={truck.pos} icon={truckIcon} zIndexOffset={1000}>
            <Tooltip direction="right" offset={[16, 0]} permanent className="!text-[11px]">
              {truck.arrived ? 'Arrived' : `+${hour} h · mile ${truck.mile}`}
            </Tooltip>
          </Marker>
        )}
      </MapContainer>

      <Legend />

      {!result && !loading && (
        <div className="pointer-events-none absolute inset-0 z-[500] flex items-center justify-center">
          <div className="rounded-xl bg-white/90 px-6 py-4 text-center shadow-lg backdrop-blur">
            <p className="text-2xl">🚚</p>
            <p className="font-semibold text-slate-700">Plan a trip to compare routes</p>
            <p className="text-xs text-slate-500">Routes, checkpoint risk and a 48-hour weather heatmap appear here.</p>
          </div>
        </div>
      )}
      {loading && (
        <div className="absolute inset-0 z-[600] flex items-center justify-center bg-white/40 backdrop-blur-[1px]">
          <div className="flex items-center gap-3 rounded-xl bg-white px-5 py-3 shadow-lg">
            <span className="h-5 w-5 animate-spin rounded-full border-2 border-slate-200 border-t-teal-700" />
            <div>
              <p className="text-sm font-semibold">Fetching routes &amp; forecasts…</p>
              <p className="text-xs text-slate-500">Sampling weather at every checkpoint ETA</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
