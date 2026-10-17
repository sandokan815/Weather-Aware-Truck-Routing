import { useEffect, useRef, useState } from 'react'
import { geocode } from '../api'

/**
 * Text input with geocoding autocomplete (debounced, cancels stale requests).
 * `value` = { text, place } where place = { label, lat, lon } once a suggestion is picked.
 */
export default function AddressInput({ id, label, value, onChange, placeholder, marker }) {
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [searching, setSearching] = useState(false)
  const abortRef = useRef(null)

  // Debounced lookup whenever the user types (not when a place was just picked).
  useEffect(() => {
    if (value.place || value.text.trim().length < 3) {
      setSuggestions([])
      return
    }
    const timer = setTimeout(async () => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      setSearching(true)
      try {
        const results = await geocode(value.text, { signal: controller.signal, autocomplete: true })
        setSuggestions(results)
        setActive(-1)
        setOpen(true)
      } catch {
        // Ignore aborted / failed lookups: submit will retry geocoding.
      } finally {
        if (abortRef.current === controller) setSearching(false)
      }
    }, 400)
    return () => clearTimeout(timer)
  }, [value.text, value.place])

  const pick = (place) => {
    onChange({ text: place.label, place })
    setOpen(false)
  }

  const onKeyDown = (e) => {
    if (!open || !suggestions.length) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => (a + 1) % suggestions.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => (a <= 0 ? suggestions.length - 1 : a - 1))
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault()
      pick(suggestions[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="relative">
      <label htmlFor={id} className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </label>
      <div className="relative">
        <span className="pointer-events-none absolute left-2.5 top-1/2 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full bg-slate-800 text-[10px] font-bold text-white">
          {marker}
        </span>
        <input
          id={id}
          type="text"
          autoComplete="off"
          className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-8 text-sm shadow-sm outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-600/20"
          placeholder={placeholder}
          value={value.text}
          onChange={(e) => onChange({ text: e.target.value, place: null })}
          onKeyDown={onKeyDown}
          onFocus={() => suggestions.length && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          role="combobox"
          aria-expanded={open}
          aria-controls={`${id}-list`}
        />
        <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs">
          {searching ? (
            <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-300 border-t-teal-600" />
          ) : value.place ? (
            <span className="text-teal-600" title="Location confirmed">✓</span>
          ) : null}
        </span>
      </div>
      {open && suggestions.length > 0 && (
        <ul id={`${id}-list`} role="listbox" className="absolute z-[1000] mt-1 max-h-60 w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 text-sm shadow-lg">
          {suggestions.map((s, i) => (
            <li
              key={`${s.lat},${s.lon},${i}`}
              role="option"
              aria-selected={i === active}
              className={`cursor-pointer px-3 py-2 ${i === active ? 'bg-teal-50 text-teal-900' : 'hover:bg-slate-50'}`}
              onMouseDown={(e) => {
                e.preventDefault()
                pick(s)
              }}
            >
              {s.label}
            </li>
          ))}
        </ul>
      )}
      {open && !searching && suggestions.length === 0 && value.text.length >= 3 && !value.place && (
        <div className="absolute z-[1000] mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500 shadow">
          No matches found
        </div>
      )}
    </div>
  )
}
