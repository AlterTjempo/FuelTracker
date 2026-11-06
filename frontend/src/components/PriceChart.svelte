<script>
  import { onMount, onDestroy } from 'svelte'
  import { poll } from '../lib/poll.js'
  import { Chart } from '../lib/chartSetup.js'
  import API_BASE, { safeFetch } from '../lib/api.js'
  import { toPoints, smooth, smoothingWindow } from '../lib/series.js'

  export let fuelType = 'e5'
  export let hours = 24

  const FINE_MAX_SPAN_MS = 3 * 24 * 3600 * 1000 // zooming into <= 3 days loads 15-min data
  const MIN_ZOOM_MS = 30 * 60 * 1000

  let chartCanvas
  let chart
  let data = []        // rows currently shown (hourly, or 15-min when zoomed in)
  let loading = true
  let error = false
  let smoothed = readPref('fuel_chart_smooth') === '1'
  let zoom = null      // { min, max } in epoch ms, or null for the full range
  let bucketMinutes = 60
  let selection = null // live drag selection in pixels
  let lastFetched = null
  let abortCtl = null

  function readPref(key) {
    try { return localStorage.getItem(key) } catch { return null }
  }
  function writePref(key, value) {
    try { localStorage.setItem(key, value) } catch { /* private mode etc. */ }
  }

  function toggleSmooth() {
    smoothed = !smoothed
    writePref('fuel_chart_smooth', smoothed ? '1' : '0')
  }

  async function fetchData() {
    if (abortCtl) abortCtl.abort()
    abortCtl = new AbortController()
    const params = new URLSearchParams({ fuel_type: fuelType })
    if (zoom && zoom.max - zoom.min <= FINE_MAX_SPAN_MS) {
      const pad = (zoom.max - zoom.min) * 0.1
      params.set('start', new Date(zoom.min - pad).toISOString())
      params.set('end', new Date(zoom.max + pad).toISOString())
      params.set('bucket_minutes', '15')
      bucketMinutes = 15
    } else {
      params.set('hours', String(hours))
      bucketMinutes = 60
    }
    try {
      const result = await safeFetch(`${API_BASE}/prices/history/all?${params}`, {
        signal: abortCtl.signal,
      })
      data = Array.isArray(result) ? result : []
      error = false
      lastFetched = new Date()
    } catch (e) {
      if (e.name === 'AbortError') return
      console.error('Error fetching data:', e)
      error = true
      data = []
    } finally {
      loading = false
    }
  }

  // ----- chart building -----

  function tickLabel(ms, spanMs) {
    const d = new Date(ms)
    const tz = 'Europe/Berlin'
    if (spanMs <= 2 * 24 * 3600 * 1000) {
      return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: tz })
    }
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: tz })
  }

  function fullLabel(ms) {
    return new Date(ms).toLocaleString('en-GB', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin',
    })
  }

  function buildDatasets() {
    const gapMs = bucketMinutes * 60 * 1000 * 3
    const avg = toPoints(data, 'avg_price', gapMs)
    const min = toPoints(data, 'min_price', gapMs)
    const max = toPoints(data, 'max_price', gapMs)
    const w = smoothingWindow(data.length)
    const base = { pointRadius: 0, spanGaps: false }
    const datasets = []
    if (smoothed) {
      datasets.push({
        ...base, label: 'Average (raw)', data: avg, borderColor: 'rgba(59,130,246,0.25)',
        borderWidth: 1, fill: false, pointHoverRadius: 0,
      })
    }
    datasets.push(
      {
        ...base, label: smoothed ? 'Average (smoothed)' : 'Average Price',
        data: smoothed ? smooth(avg, w) : avg,
        borderColor: '#3b82f6', backgroundColor: 'rgba(59, 130, 246, 0.1)',
        borderWidth: 2, fill: true, pointHoverRadius: 6, tension: smoothed ? 0.3 : 0,
      },
      {
        ...base, label: 'Min Price', data: smoothed ? smooth(min, w) : min,
        borderColor: '#10b981', borderWidth: 1, borderDash: [5, 5], fill: false,
        tension: smoothed ? 0.3 : 0,
      },
      {
        ...base, label: 'Max Price', data: smoothed ? smooth(max, w) : max,
        borderColor: '#ef4444', borderWidth: 1, borderDash: [5, 5], fill: false,
        tension: smoothed ? 0.3 : 0,
      }
    )
    return datasets
  }

  // Y range that fits what is visible (zooming rescales y too). With many
  // points we ignore the extreme 1% on each side so a single price spike
  // doesn't flatten the whole chart; spiked points still show in the tooltip.
  function yBounds(datasets, xMin, xMax) {
    const ys = []
    for (const ds of datasets) {
      for (const p of ds.data) {
        if (p.y !== null && p.x >= xMin && p.x <= xMax) ys.push(p.y)
      }
    }
    if (ys.length === 0) return {}
    ys.sort((a, b) => a - b)
    const cut = ys.length > 200 ? Math.floor(ys.length * 0.01) : 0
    const lo = ys[cut]
    const hi = ys[ys.length - 1 - cut]
    const pad = Math.max((hi - lo) * 0.08, 0.005)
    return { min: lo - pad, max: hi + pad }
  }

  const selectionPlugin = {
    id: 'zoomSelection',
    afterDraw(c) {
      if (!selection) return
      const { ctx, chartArea } = c
      const x1 = Math.max(chartArea.left, Math.min(selection.x0, selection.x1))
      const x2 = Math.min(chartArea.right, Math.max(selection.x0, selection.x1))
      ctx.save()
      ctx.fillStyle = 'rgba(59,130,246,0.15)'
      ctx.strokeStyle = 'rgba(59,130,246,0.6)'
      ctx.fillRect(x1, chartArea.top, x2 - x1, chartArea.bottom - chartArea.top)
      ctx.strokeRect(x1, chartArea.top, x2 - x1, chartArea.bottom - chartArea.top)
      ctx.restore()
    },
  }

  function render() {
    if (!chartCanvas || data.length === 0) return
    const datasets = buildDatasets()
    const firstX = datasets[0].data[0].x
    const lastX = datasets[0].data[datasets[0].data.length - 1].x
    const xMin = zoom ? zoom.min : firstX
    const xMax = zoom ? zoom.max : lastX
    const y = yBounds(datasets, xMin, xMax)
    const span = xMax - xMin

    if (!chart) {
      chart = new Chart(chartCanvas.getContext('2d'), {
        type: 'line',
        data: { datasets },
        plugins: [selectionPlugin],
        options: {
          responsive: true,
          maintainAspectRatio: false,
          parsing: false,
          normalized: true,
          animation: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { display: true, position: 'top', labels: { color: '#8b949e', font: { size: 12 } } },
            tooltip: {
              backgroundColor: '#161b22', borderColor: '#30363d', borderWidth: 1,
              titleColor: '#e6edf3', bodyColor: '#8b949e',
              filter: (item) => item.parsed.y !== null,
              callbacks: {
                title: (items) => (items.length ? fullLabel(items[0].parsed.x) : ''),
                label: (ctx) => ctx.dataset.label + ': €' + ctx.parsed.y.toFixed(3),
              },
            },
          },
          scales: {
            x: {
              type: 'linear',
              grid: { color: '#30363d' },
              ticks: { color: '#8b949e', maxRotation: 0, maxTicksLimit: 7 },
            },
            y: {
              grid: { color: '#30363d' },
              ticks: { color: '#8b949e', callback: (v) => '€' + v.toFixed(3) },
            },
          },
        },
      })
    } else {
      chart.data.datasets = datasets
    }

    const xs = chart.options.scales.x
    xs.min = xMin
    xs.max = xMax
    xs.ticks.callback = (v) => tickLabel(v, span)
    const ys = chart.options.scales.y
    ys.min = y.min
    ys.max = y.max
    chart.update('none')
  }

  // ----- drag-to-zoom -----

  let dragStartX = null

  function localX(e) {
    const rect = chartCanvas.getBoundingClientRect()
    return e.clientX - rect.left
  }

  function onPointerDown(e) {
    if (!chart || e.button > 0) return
    dragStartX = localX(e)
    selection = null
    chartCanvas.setPointerCapture?.(e.pointerId)
  }

  function onPointerMove(e) {
    if (dragStartX === null || !chart) return
    selection = { x0: dragStartX, x1: localX(e) }
    chart.draw()
  }

  function onPointerUp(e) {
    if (dragStartX === null || !chart) return
    const x0 = dragStartX
    const x1 = localX(e)
    dragStartX = null
    selection = null
    if (Math.abs(x1 - x0) < 12) { chart.draw(); return } // a click, not a drag
    const scale = chart.scales.x
    let a = scale.getValueForPixel(Math.min(x0, x1))
    let b = scale.getValueForPixel(Math.max(x0, x1))
    if (b - a < MIN_ZOOM_MS) {
      const mid = (a + b) / 2
      a = mid - MIN_ZOOM_MS / 2
      b = mid + MIN_ZOOM_MS / 2
    }
    zoom = { min: a, max: b }
    fetchData()
  }

  function onPointerCancel() {
    dragStartX = null
    selection = null
    chart?.draw()
  }

  function resetZoom() {
    zoom = null
    fetchData()
  }

  // ----- lifecycle -----

  let interval
  onMount(() => {
    interval = poll(fetchData, 60000)
  })
  onDestroy(() => {
    clearInterval(interval)
    abortCtl?.abort()
    chart?.destroy()
  })

  // A new fuel type or range resets zoom and reloads. (Svelte runs this once
  // on init, which doubles as the initial fetch.)
  let lastKey = ''
  $: {
    const key = fuelType + '|' + hours
    if (key !== lastKey) {
      lastKey = key
      zoom = null
      loading = true
      fetchData()
    }
  }

  // Re-render whenever data / smoothing change; drop the chart when it has no data.
  $: if (chartCanvas && data.length > 0) {
    smoothed, render()
  } else if (chart) {
    chart.destroy()
    chart = null
  }

  $: zoomLabel = zoom
    ? `${fullLabel(zoom.min)} – ${fullLabel(zoom.max)}`
    : ''
</script>

<div class="chart-wrap">
  <div class="chart-toolbar">
    <span class="hint">
      {#if zoom}
        Zoomed: {zoomLabel}{bucketMinutes === 15 ? ' · 15-min data' : ''}
      {:else}
        Drag on the chart to zoom into a period
      {/if}
    </span>
    <div class="tools">
      {#if zoom}
        <button class="tool" on:click={resetZoom}>Reset zoom</button>
      {/if}
      <button
        class="tool"
        class:active={smoothed}
        aria-pressed={smoothed}
        on:click={toggleSmooth}
        title="Show a smoothed line (moving average). Stored data is not changed."
      >
        ∿ Smooth
      </button>
    </div>
  </div>

  <div class="chart-container">
    {#if loading}
      <div class="state">Loading price data...</div>
    {:else if error}
      <div class="state">Couldn't load price data. Retrying automatically…</div>
    {:else if data.length === 0}
      <div class="state">No data in this period{zoom ? ' — try a wider range' : ' yet. Data collection in progress...'}</div>
    {:else}
      <canvas
        bind:this={chartCanvas}
        on:pointerdown={onPointerDown}
        on:pointermove={onPointerMove}
        on:pointerup={onPointerUp}
        on:pointercancel={onPointerCancel}
        on:dblclick={resetZoom}
      ></canvas>
    {/if}
  </div>
</div>

<style>
  .chart-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
    flex-wrap: wrap;
  }

  .hint {
    color: #8b949e;
    font-size: 0.8rem;
  }

  .tools {
    display: flex;
    gap: 0.375rem;
  }

  .tool {
    min-height: 2rem;
    padding: 0.25rem 0.75rem;
    font-size: 0.8rem;
    background: #21262d;
    border: 1px solid #30363d;
    color: #8b949e;
    border-radius: 6px;
    cursor: pointer;
    font-weight: 500;
    transition: background 0.2s, border-color 0.2s;
  }

  .tool:hover {
    background: #30363d;
    border-color: #3b82f6;
  }

  .tool.active {
    background: #3b82f6;
    border-color: #3b82f6;
    color: #fff;
  }

  .chart-container {
    height: 250px;
    position: relative;
  }

  canvas {
    max-height: 250px;
    cursor: crosshair;
    touch-action: pan-y; /* vertical scroll still works; horizontal drag selects */
  }

  .state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #8b949e;
    font-size: 0.95rem;
    text-align: center;
    padding: 0 1rem;
  }

  @media (min-width: 640px) {
    .chart-container { height: 350px; }
    canvas { max-height: 350px; }
  }

  @media (min-width: 1024px) {
    .chart-container { height: 400px; }
    canvas { max-height: 400px; }
  }
</style>
