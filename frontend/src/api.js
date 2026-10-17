import axios from 'axios'

const api = axios.create({
  baseURL: `${import.meta.env.VITE_API_BASE || ''}/api`,
  timeout: 60000,
})

/** Pull a readable message out of an axios error. */
export function errorMessage(err) {
  const data = err?.response?.data
  if (data?.details) {
    return Object.entries(data.details)
      .map(([field, msgs]) => `${field === 'non_field_errors' ? '' : field + ': '}${[].concat(msgs).join(' ')}`)
      .join(' · ')
  }
  if (data?.error) return data.error
  if (err?.code === 'ECONNABORTED') return 'The request timed out. Please try again.'
  if (err?.request && !err?.response) return 'Cannot reach the server. Is the Django backend running on port 8000?'
  return err?.message || 'Something went wrong.'
}

export async function geocode(q, { signal, autocomplete = false } = {}) {
  const { data } = await api.get('/geocode', { params: { q, autocomplete: autocomplete ? 1 : 0 }, signal })
  return data.results
}

export async function planTrip(payload) {
  const { data } = await api.post('/plan-trip', payload)
  return data
}
