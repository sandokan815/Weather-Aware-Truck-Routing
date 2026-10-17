import { useCallback, useState } from 'react'
import { errorMessage, planTrip } from './api'
import ForecastSlider from './components/ForecastSlider'
import RouteMap from './components/RouteMap'
import RouteSummary from './components/RouteSummary'
import TripForm from './components/TripForm'

export default function App() {
  const [result, setResult] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Heatmap / slider state
  const [hour, setHour] = useState(0)
  const [heatMetric, setHeatMetric] = useState('risk')
  const [heatScope, setHeatScope] = useState('selected')
  const [showHeat, setShowHeat] = useState(true)
  const [playing, setPlaying] = useState(false)
  const [focus, setFocus] = useState(null)

  const handleSubmit = useCallback(async (form) => {
    setLoading(true)
    setError('')
    setPlaying(false)
    try {
      const data = await planTrip({
        origin_lat: form.origin.lat,
        origin_lon: form.origin.lon,
        dest_lat: form.destination.lat,
        dest_lon: form.destination.lon,
        departure_iso: form.departure_iso,
        load_weight_lb: form.load_weight_lb,
        sample_miles: form.sample_miles,
      })
      setResult(data)
      setSelectedId(data.recommended_route_id)
      setHour(0)
      setFocus(null)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  return (
    <div className="flex h-full flex-col md:flex-row">
      <aside className="flex w-full shrink-0 flex-col border-slate-200 bg-slate-50 md:h-full md:w-[420px] md:border-r">
        <header className="flex items-center gap-2 border-b border-slate-200 bg-white px-4 py-3">
          <span className="text-xl">🚚</span>
          <div>
            <h1 className="text-base font-bold leading-tight">Truck Safe Route Planner</h1>
            <p className="text-[11px] text-slate-500">Weather- and load-aware routing · 3 options · 48 h forecast</p>
          </div>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          <TripForm onSubmit={handleSubmit} loading={loading} />

          {error && (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              <strong className="block">Could not plan trip</strong>
              {error}
            </div>
          )}

          {result?.warnings?.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              {result.warnings.map((w) => <p key={w}>⚠ {w}</p>)}
            </div>
          )}

          {result && (
            <>
              <RouteSummary
                result={result}
                selectedId={selectedId}
                onSelect={setSelectedId}
                onFocusCheckpoint={(cp) => setFocus({ cp, at: Date.now() })}
              />
              <p className="text-center text-[10px] text-slate-400">
                Routing: {result.data_sources.routing} · Weather: {result.data_sources.weather} · {(result.timing_ms.total / 1000).toFixed(1)} s
              </p>
            </>
          )}

          {!result && !loading && !error && (
            <p className="rounded-lg border border-dashed border-slate-300 px-3 py-4 text-center text-xs text-slate-500">
              Enter a trip to compare three routes by weather risk at the truck's ETA along each one.
            </p>
          )}
        </div>
      </aside>

      <main className="relative h-[70vh] flex-1 md:h-full">
        <RouteMap
          result={result}
          selectedId={selectedId}
          onSelect={setSelectedId}
          hour={hour}
          heatMetric={heatMetric}
          heatScope={heatScope}
          showHeat={showHeat}
          focus={focus}
          loading={loading}
        />
        {result && (
          <div className="absolute bottom-6 left-3 right-3 z-[500] mx-auto max-w-2xl">
            <ForecastSlider
              hour={hour}
              onHour={setHour}
              startIso={result.corridor.start_iso}
              hours={result.corridor.hours}
              metric={heatMetric}
              onMetric={setHeatMetric}
              scope={heatScope}
              onScope={setHeatScope}
              show={showHeat}
              onShow={setShowHeat}
              playing={playing}
              onPlaying={setPlaying}
            />
          </div>
        )}
      </main>
    </div>
  )
}
