/**
 * setInterval that skips ticks while the browser tab is hidden, so background
 * tabs don't keep hitting the API. Returns the interval id (use clearInterval).
 */
export function poll(fn, ms) {
  return setInterval(() => {
    if (typeof document === 'undefined' || !document.hidden) fn()
  }, ms)
}
