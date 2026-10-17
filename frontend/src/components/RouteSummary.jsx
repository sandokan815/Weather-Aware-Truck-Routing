import { formatDateTime, formatDuration, formatMiles, RISK_LEVELS, riskColor, ROUTE_COLORS } from '../risk'

/** Stacked bar: share of the route's miles in each risk level. */
function RiskBar({ summary }) {
  const total = summary.total_miles || 1
  return (
    <div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
        {RISK_LEVELS.map(({ key, label, color }) => {
          const mi = summary[`${key}_miles`]
          if (!mi) return null
          return <div key={key} style={{ width: `${(mi / total) * 100}%`, background: color }} title={`${label}: ${mi} mi`} />
        })}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-slate-500">
        {RISK_LEVELS.map(({ key, label, color }) => {
          const mi = summary[`${key}_miles`]
          if (!mi) return null
          return (
            <span key={key} className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-full" style={{ background: color }} />
              {label} {Math.round(mi)} mi
            </span>
          )
        })}
      </div>
    </div>
  )
}

function RouteCard({ route, selected, onSelect }) {
  const s = route.summary
  const accent = route.recommended ? ROUTE_COLORS.recommended : selected ? ROUTE_COLORS.selected : ROUTE_COLORS.other
  return (
    <button
      type="button"
      onClick={() => onSelect(route.id)}
      className={`w-full rounded-xl border bg-white p-3 text-left shadow-sm transition hover:shadow ${
        selected ? 'border-slate-800 ring-2 ring-slate-800/10' : 'border-slate-200'
      }`}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: accent }} />
            <span className="font-semibold">{route.name}</span>
            <span className="text-xs text-slate-400">#{route.rank}</span>
          </div>
          {route.via && <p className="mt-0.5 truncate text-xs text-slate-500">via {route.via}</p>}
        </div>
        {route.recommended && (
          <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-800">★ Recommended</span>
        )}
      </div>

      <dl className="mb-2.5 grid grid-cols-4 gap-1 text-center">
        <Stat label="Distance" value={formatMiles(s.total_miles)} />
        <Stat label="Drive time" value={formatDuration(s.total_duration_min)} />
        <Stat label="Avg risk" value={s.avg_risk_score.toFixed(2)} />
        <Stat label="Worst" value={s.max_risk_label} color={riskColor(s.max_risk_level)} />
      </dl>

      <RiskBar summary={s} />
      {s.severe_or_worse_miles > 0 && (
        <p className="mt-1.5 text-[11px] font-medium text-red-700">⚠ {s.severe_or_worse_miles} mi severe or no-travel conditions</p>
      )}
    </button>
  )
}

function Stat({ label, value, color }) {
  return (
    <div className="rounded-md bg-slate-50 px-1 py-1.5">
      <dt className="text-[10px] uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="text-xs font-semibold" style={color ? { color } : undefined}>
        {value}
      </dd>
    </div>
  )
}

/** Checkpoint list for the selected route (mile, ETA, conditions, risk). */
function CheckpointTable({ route, onFocusCheckpoint }) {
  return (
    <details className="rounded-xl border border-slate-200 bg-white text-xs shadow-sm">
      <summary className="cursor-pointer select-none px-3 py-2 font-semibold text-slate-700">
        {route.name} checkpoints ({route.checkpoints.length})
      </summary>
      <div className="max-h-72 overflow-auto border-t border-slate-100">
        <table className="w-full">
          <thead className="sticky top-0 bg-slate-50 text-[10px] uppercase text-slate-500">
            <tr>
              <th className="px-2 py-1 text-left">Mile</th>
              <th className="px-2 py-1 text-left">ETA</th>
              <th className="px-2 py-1 text-right">Wind</th>
              <th className="px-2 py-1 text-right">Rain</th>
              <th className="px-2 py-1 text-right">Snow</th>
              <th className="px-2 py-1 text-left">Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((cp) => (
              <tr key={cp.index} className="cursor-pointer border-t border-slate-100 hover:bg-teal-50" onClick={() => onFocusCheckpoint(cp)}>
                <td className="px-2 py-1 tabular-nums">{cp.mile}</td>
                <td className="whitespace-nowrap px-2 py-1">{formatDateTime(cp.eta_iso)}</td>
                <td className="px-2 py-1 text-right tabular-nums">{cp.weather.wind_mph}</td>
                <td className="px-2 py-1 text-right tabular-nums">{cp.weather.rain_in_hr}</td>
                <td className="px-2 py-1 text-right tabular-nums">{cp.weather.snow_in_hr}</td>
                <td className="px-2 py-1">
                  <span className="inline-flex items-center gap-1 whitespace-nowrap">
                    <span className="h-2 w-2 rounded-full" style={{ background: riskColor(cp.risk.level) }} />
                    {cp.risk.label}
                    {cp.risk.load_adjusted && <span title="Upgraded by load rule">⚖</span>}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="px-3 py-1.5 text-[10px] text-slate-400">Wind mph · rain/snow in/hr at ETA · ⚖ = upgraded by load rule</p>
      </div>
    </details>
  )
}

export default function RouteSummary({ result, selectedId, onSelect, onFocusCheckpoint }) {
  const selected = result.routes.find((r) => r.id === selectedId)
  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs leading-relaxed text-emerald-900">
        <p className="mb-0.5 font-semibold">Recommendation</p>
        {result.recommendation_reason}
      </div>
      {result.routes.map((r) => (
        <RouteCard key={r.id} route={r} selected={r.id === selectedId} onSelect={onSelect} />
      ))}
      {selected && <CheckpointTable route={selected} onFocusCheckpoint={onFocusCheckpoint} />}
    </div>
  )
}
