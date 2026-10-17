// Risk levels + colors shared by map, cards and legend. Thresholds mirror
// backend/routes/services/risk.py (used only to color the wind/rain/snow
// heatmap modes; checkpoint risk always comes from the backend).

export const RISK_LEVELS = [
  { level: 1, key: 'low', label: 'Low', color: '#16a34a' },
  { level: 2, key: 'moderate', label: 'Moderate', color: '#eab308' },
  { level: 3, key: 'high', label: 'High', color: '#f97316' },
  { level: 4, key: 'severe', label: 'Severe', color: '#dc2626' },
  { level: 5, key: 'no_travel', label: 'No Travel', color: '#111827' },
]

export const riskColor = (level) => RISK_LEVELS[Math.min(5, Math.max(1, level)) - 1].color
export const riskLabel = (level) => RISK_LEVELS[Math.min(5, Math.max(1, level)) - 1].label

export const windLevel = (mph) => (mph >= 55 ? 5 : mph >= 45 ? 4 : mph >= 35 ? 3 : mph >= 25 ? 2 : 1)
export const rainLevel = (r) => (r > 1 ? 5 : r >= 0.5 ? 4 : r >= 0.25 ? 3 : r >= 0.1 ? 2 : 1)
export const snowLevel = (s) => (s > 3 ? 5 : s >= 2 ? 4 : s >= 1 ? 3 : s >= 0.5 ? 2 : 1)

/** Heatmap metrics: how to turn a corridor frame at hour h into level + 0..1 intensity. */
export const HEAT_METRICS = {
  risk: { label: 'Risk (load-adjusted)', level: (f, h) => f.risk[h], intensity: (f, h) => (f.risk[h] - 1) / 4 },
  wind: { label: 'Wind (mph)', level: (f, h) => windLevel(f.wind[h]), intensity: (f, h) => Math.min(1, f.wind[h] / 55) },
  rain: { label: 'Rain (in/hr)', level: (f, h) => rainLevel(f.rain[h]), intensity: (f, h) => Math.min(1, f.rain[h] / 1) },
  snow: { label: 'Snow (in/hr)', level: (f, h) => snowLevel(f.snow[h]), intensity: (f, h) => Math.min(1, f.snow[h] / 3) },
}

export const ROUTE_COLORS = { recommended: '#059669', selected: '#2563eb', other: '#94a3b8' }

export function formatDuration(min) {
  const h = Math.floor(min / 60)
  const m = Math.round(min % 60)
  return h ? `${h} h ${m} m` : `${m} m`
}

export function formatMiles(mi) {
  return `${Math.round(mi).toLocaleString()} mi`
}

export function formatDateTime(iso) {
  return new Date(iso).toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}
