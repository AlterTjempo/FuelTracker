// Helpers for turning API history rows into chart series.

/**
 * Convert rows to {x: epochMs, y} points. A `null` point is inserted wherever
 * consecutive observations are further apart than `gapMs`, so missing periods
 * show up as real gaps instead of a line that implies nothing happened.
 */
export function toPoints(rows, key, gapMs) {
  const pts = []
  let prev = null
  for (const r of rows) {
    const x = new Date(r.timestamp).getTime()
    if (prev !== null && x - prev > gapMs) pts.push({ x: prev + gapMs / 2, y: null })
    pts.push({ x, y: r[key] })
    prev = x
  }
  return pts
}

/**
 * Centered moving average that never crosses a gap (null point).
 * Visualisation only; the raw points are left untouched.
 */
export function smooth(points, windowSize) {
  const half = Math.floor(windowSize / 2)
  const out = []
  let start = 0
  const flush = (end) => {
    const seg = points.slice(start, end)
    for (let i = 0; i < seg.length; i++) {
      const lo = Math.max(0, i - half)
      const hi = Math.min(seg.length - 1, i + half)
      let sum = 0
      for (let j = lo; j <= hi; j++) sum += seg[j].y
      out.push({ x: seg[i].x, y: sum / (hi - lo + 1) })
    }
  }
  for (let i = 0; i < points.length; i++) {
    if (points[i].y === null) {
      flush(i)
      out.push(points[i])
      start = i + 1
    }
  }
  flush(points.length)
  return out
}

export function smoothingWindow(n) {
  const w = Math.round(n / 40)
  const clamped = Math.min(25, Math.max(3, w))
  return clamped % 2 === 0 ? clamped + 1 : clamped
}
