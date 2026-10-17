import { useState } from 'react'
import { geocode } from '../api'
import AddressInput from './AddressInput'

const EMPTY = { text: '', place: null }

/** Current local time formatted for <input type="datetime-local">. */
function nowLocal() {
  const d = new Date()
  d.setSeconds(0, 0)
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

const EXAMPLE = {
  origin: { text: 'Los Angeles, California, USA', place: { label: 'Los Angeles, California, USA', lat: 34.0522, lon: -118.2437 } },
  destination: { text: 'Denver, Colorado, USA', place: { label: 'Denver, Colorado, USA', lat: 39.7392, lon: -104.9903 } },
}

export default function TripForm({ onSubmit, loading }) {
  const [origin, setOrigin] = useState(EMPTY)
  const [destination, setDestination] = useState(EMPTY)
  const [departure, setDeparture] = useState(nowLocal)
  const [load, setLoad] = useState('40500')
  const [formError, setFormError] = useState('')

  // If the user typed an address but never picked a suggestion, take the top match.
  async function resolve(value, name) {
    if (value.place) return value.place
    if (!value.text.trim()) throw new Error(`Please enter an ${name}.`)
    const results = await geocode(value.text)
    if (!results.length) throw new Error(`Could not find "${value.text}". Try a city name.`)
    return results[0]
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setFormError('')
    const loadNum = Number(load)
    if (load === '' || Number.isNaN(loadNum) || loadNum < 0 || loadNum > 80000) {
      setFormError('Load weight must be between 0 and 80,000 lb.')
      return
    }
    try {
      const [o, d] = await Promise.all([resolve(origin, 'origin'), resolve(destination, 'destination')])
      setOrigin({ text: o.label, place: o })
      setDestination({ text: d.label, place: d })
      onSubmit({
        origin: o,
        destination: d,
        departure_iso: departure ? new Date(departure).toISOString() : new Date().toISOString(),
        load_weight_lb: loadNum,
      })
    } catch (err) {
      setFormError(err.message || 'Could not look up the addresses.')
    }
  }

  const swap = () => {
    setOrigin(destination)
    setDestination(origin)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <AddressInput id="origin" label="Origin" marker="A" value={origin} onChange={setOrigin} placeholder="e.g. Los Angeles, CA" />
      <div className="-my-1 flex justify-end">
        <button type="button" onClick={swap} className="text-xs font-medium text-slate-500 hover:text-teal-700" title="Swap origin and destination">
          ⇅ Swap
        </button>
      </div>
      <AddressInput id="destination" label="Destination" marker="B" value={destination} onChange={setDestination} placeholder="e.g. Denver, CO" />

      <div>
        <label htmlFor="departure" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
          Departure
        </label>
        <div className="flex gap-2">
          <input
            id="departure"
            type="datetime-local"
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-600/20"
            value={departure}
            onChange={(e) => setDeparture(e.target.value)}
          />
          <button type="button" onClick={() => setDeparture(nowLocal())} className="rounded-lg border border-slate-300 bg-white px-3 text-xs font-medium text-slate-600 hover:bg-slate-50">
            Now
          </button>
        </div>
      </div>

      <div>
        <label htmlFor="load" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
          Load weight (lb)
        </label>
        <input
          id="load"
          type="number"
          min="0"
          max="80000"
          step="500"
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-600/20"
          value={load}
          onChange={(e) => setLoad(e.target.value)}
        />
      </div>

      {formError && <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{formError}</p>}

      <button
        type="submit"
        disabled={loading}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-800 disabled:cursor-wait disabled:opacity-70"
      >
        {loading && <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />}
        {loading ? 'Planning routes…' : 'Plan safest route'}
      </button>
      <button
        type="button"
        onClick={() => {
          setOrigin(EXAMPLE.origin)
          setDestination(EXAMPLE.destination)
          setLoad('40500')
          setDeparture(nowLocal())
        }}
        className="w-full text-center text-xs text-slate-500 hover:text-teal-700"
      >
        Fill example: Los Angeles → Denver, 40,500 lb
      </button>
    </form>
  )
}
