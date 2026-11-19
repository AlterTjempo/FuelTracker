// Small shared helpers for prices, times, routes and location.

export function eur3(n) {
  return n === null || n === undefined ? '–' : `€${Number(n).toFixed(3)}`
}

export function timeAgo(iso) {
  if (!iso) return ''
  const m = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000))
  if (m < 1) return 'just now'
  if (m < 60) return `${m} min ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} h ago`
  return `${Math.floor(h / 24)} d ago`
}

// Directions by coordinates (exact), falling back to a name search.
export function routeUrl({ lat, lon, name, city }) {
  if (lat !== null && lat !== undefined && lon !== null && lon !== undefined) {
    return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}`
  }
  const q = encodeURIComponent(`${name || ''} ${city || ''}`.trim())
  return `https://www.google.com/maps/search/?api=1&query=${q}`
}

export function distanceKm(a, b) {
  const R = 6371
  const rad = (d) => (d * Math.PI) / 180
  const dLat = rad(b.lat - a.lat)
  const dLon = rad(b.lon - a.lon)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

// Ask the browser for the location once per page load; it is never stored or sent
// anywhere except as query parameters of the request that needs it.
let positionPromise = null
export function getPosition() {
  if (!positionPromise) {
    positionPromise = new Promise((resolve, reject) => {
      if (!navigator.geolocation) return reject(new Error('unsupported'))
      navigator.geolocation.getCurrentPosition(
        (p) => resolve({ lat: p.coords.latitude, lon: p.coords.longitude }),
        reject,
        { timeout: 8000, maximumAge: 600000 }
      )
    }).catch((e) => {
      positionPromise = null // allow a retry later (e.g. after the user grants permission)
      throw e
    })
  }
  return positionPromise
}

export function readPref(key, fallback = null) {
  try {
    const v = localStorage.getItem(key)
    return v === null ? fallback : v
  } catch {
    return fallback
  }
}

export function writePref(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* private mode etc. */
  }
}
