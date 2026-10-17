import { useState } from 'react'
import { RISK_LEVELS, ROUTE_COLORS } from '../risk'

/** Map legend: risk colors, thresholds/units and route line meanings. Collapsible. */
export default function Legend() {
  const [open, setOpen] = useState(true)
  return (
    <div className="absolute right-3 top-3 z-[500] w-56 rounded-xl bg-white/95 text-xs shadow-lg backdrop-blur">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between px-3 py-2 font-semibold">
        Legend <span className="text-slate-400">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-slate-100 px-3 pb-3 pt-2">
          <ul className="space-y-1">
            {RISK_LEVELS.map((r) => (
              <li key={r.key} className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-full border border-white shadow" style={{ background: r.color }} />
                <span className="w-16 font-medium">{r.label}</span>
                <span className="text-[10px] text-slate-400">{r.level}</span>
              </li>
            ))}
          </ul>
          <table className="w-full text-[10px] text-slate-500">
            <tbody>
              <tr><td className="pr-1 font-medium text-slate-600">Wind</td><td>mph: 25 / 35 / 45 / 55</td></tr>
              <tr><td className="pr-1 font-medium text-slate-600">Rain</td><td>in/hr: .10 / .25 / .50 / 1.0</td></tr>
              <tr><td className="pr-1 font-medium text-slate-600">Snow</td><td>in/hr: .5 / 1 / 2 / 3</td></tr>
            </tbody>
          </table>
          <p className="text-[10px] leading-snug text-slate-400">
            Load rules: 45–54 mph &gt;30k lb → No Travel; 35–44 mph &gt;40k lb → Severe.
          </p>
          <div className="space-y-1 border-t border-slate-100 pt-2">
            <LineKey color={ROUTE_COLORS.recommended} label="Recommended route" />
            <LineKey color={ROUTE_COLORS.selected} label="Selected route" />
            <LineKey color={ROUTE_COLORS.other} label="Other routes" dashed />
          </div>
        </div>
      )}
    </div>
  )
}

function LineKey({ color, label, dashed }) {
  return (
    <div className="flex items-center gap-2">
      <svg width="24" height="6">
        <line x1="0" y1="3" x2="24" y2="3" stroke={color} strokeWidth="4" strokeDasharray={dashed ? '5 4' : undefined} />
      </svg>
      {label}
    </div>
  )
}
