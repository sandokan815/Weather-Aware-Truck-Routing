import { useEffect } from 'react'
import { HEAT_METRICS } from '../risk'

/**
 * 0-48 h forecast slider (hour offset from departure) + heatmap controls.
 * Play animates through the hours.
 */
export default function ForecastSlider({ hour, onHour, startIso, hours = 48, metric, onMetric, scope, onScope, show, onShow, playing, onPlaying }) {
  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => onHour((h) => (h >= hours ? 0 : h + 1)), 450)
    return () => clearInterval(id)
  }, [playing, hours, onHour])

  const at = new Date(new Date(startIso).getTime() + hour * 3600 * 1000)
  const atLabel = at.toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' })

  return (
    <div className="rounded-xl bg-white/95 p-3 shadow-lg backdrop-blur">
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-2">
        <button
          type="button"
          onClick={() => onPlaying(!playing)}
          className="flex h-8 w-8 items-center justify-center rounded-full bg-teal-700 text-white hover:bg-teal-800"
          title={playing ? 'Pause' : 'Play forecast'}
          aria-label={playing ? 'Pause' : 'Play forecast'}
        >
          {playing ? '❚❚' : '▶'}
        </button>
        <div className="min-w-[120px]">
          <div className="text-sm font-semibold tabular-nums">Departure +{hour} h</div>
          <div className="text-[11px] text-slate-500">{atLabel}</div>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2 text-xs">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={show} onChange={(e) => onShow(e.target.checked)} className="accent-teal-700" />
            Heatmap
          </label>
          <select value={metric} onChange={(e) => onMetric(e.target.value)} className="rounded-md border border-slate-300 bg-white px-1.5 py-1" aria-label="Heatmap metric">
            {Object.entries(HEAT_METRICS).map(([k, m]) => (
              <option key={k} value={k}>{m.label}</option>
            ))}
          </select>
          <select value={scope} onChange={(e) => onScope(e.target.value)} className="rounded-md border border-slate-300 bg-white px-1.5 py-1" aria-label="Heatmap scope">
            <option value="selected">Selected route</option>
            <option value="all">All routes</option>
          </select>
        </div>
      </div>
      <input
        type="range"
        className="forecast w-full"
        min={0}
        max={hours}
        step={1}
        value={hour}
        onChange={(e) => {
          onPlaying(false)
          onHour(Number(e.target.value))
        }}
        aria-label="Forecast hour offset"
      />
      <div className="flex justify-between text-[10px] text-slate-400">
        {[0, 12, 24, 36, 48].map((h) => <span key={h}>{h} h</span>)}
      </div>
    </div>
  )
}
