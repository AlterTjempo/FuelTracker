<script>
  import { onDestroy } from 'svelte'
  import { Chart } from '../lib/chartSetup.js'

  // history:  [{ date: 'YYYY-MM-DD', price }]  (real daily levels, gaps stay gaps)
  // horizons: [{ date, expected_price, interval_cents, beats_baseline }]
  export let history = []
  export let horizons = []
  export let originDate = null
  export let originPrice = null

  let canvas
  let chart

  const DAY = 24 * 3600 * 1000
  const ms = (iso) => new Date(iso + 'T12:00:00').getTime()
  const fmtDay = (v) =>
    new Date(v).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'Europe/Berlin' })

  function buildHistory() {
    const pts = []
    let prev = null
    for (const h of history) {
      const x = ms(h.date)
      if (prev !== null && x - prev > 1.5 * DAY) pts.push({ x: prev + DAY / 2, y: null }) // real gap
      pts.push({ x, y: h.price })
      prev = x
    }
    return pts
  }

  function buildForecast() {
    if (!originDate || originPrice === null || !horizons.length) return { line: [], lower: [], upper: [] }
    const x0 = ms(originDate)
    const line = [{ x: x0, y: originPrice }]
    const lower = [{ x: x0, y: originPrice }]
    const upper = [{ x: x0, y: originPrice }]
    for (const h of horizons) {
      const x = ms(h.date)
      const band = (h.interval_cents ?? 0) / 100
      line.push({ x, y: h.expected_price })
      lower.push({ x, y: h.expected_price - band })
      upper.push({ x, y: h.expected_price + band })
    }
    return { line, lower, upper }
  }

  // vertical dotted marker where the forecast starts, and "today"
  const markers = {
    id: 'markers',
    afterDatasetsDraw(c) {
      const { ctx, chartArea, scales } = c
      const draw = (x, label, color) => {
        if (x < scales.x.min || x > scales.x.max) return
        const px = scales.x.getPixelForValue(x)
        ctx.save()
        ctx.strokeStyle = color
        ctx.setLineDash([2, 4])
        ctx.beginPath()
        ctx.moveTo(px, chartArea.top)
        ctx.lineTo(px, chartArea.bottom)
        ctx.stroke()
        ctx.setLineDash([])
        ctx.fillStyle = color
        ctx.font = '11px sans-serif'
        ctx.textAlign = 'left'
        ctx.fillText(label, px + 4, chartArea.top + 12)
        ctx.restore()
      }
      if (originDate) draw(ms(originDate), 'Forecast starts', '#6e7681')
    },
  }

  function render() {
    if (!canvas) return
    const hist = buildHistory()
    const fc = buildForecast()
    if (hist.length === 0) return

    const values = [...hist, ...fc.lower, ...fc.upper].map((p) => p.y).filter((v) => v !== null)
    const lo = Math.min(...values)
    const hi = Math.max(...values)
    const pad = Math.max((hi - lo) * 0.12, 0.01)

    const datasets = [
      {
        label: 'Historical price',
        data: hist,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59,130,246,0.08)',
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        spanGaps: false,
        order: 1,
      },
    ]
    if (fc.line.length > 1) {
      datasets.push(
        {
          label: 'range-lower',
          data: fc.lower,
          borderColor: 'transparent',
          pointRadius: 0,
          fill: false,
          order: 3,
        },
        {
          label: '80% range',
          data: fc.upper,
          borderColor: 'transparent',
          backgroundColor: 'rgba(245,158,11,0.14)',
          pointRadius: 0,
          fill: '-1',
          order: 3,
        },
        {
          label: 'Forecast',
          data: fc.line,
          borderColor: '#f59e0b',
          borderWidth: 2,
          borderDash: [6, 5],
          pointRadius: 3,
          pointBackgroundColor: '#f59e0b',
          fill: false,
          order: 0,
        }
      )
    }

    if (chart) chart.destroy()
    chart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { datasets },
      plugins: [markers],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        parsing: false,
        animation: false,
        interaction: { mode: 'nearest', axis: 'x', intersect: false },
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              color: '#8b949e',
              boxWidth: 18,
              font: { size: 11 },
              filter: (item) => item.text !== 'range-lower',
            },
          },
          tooltip: {
            backgroundColor: '#161b22',
            borderColor: '#30363d',
            borderWidth: 1,
            titleColor: '#e6edf3',
            bodyColor: '#8b949e',
            filter: (item) => item.parsed.y !== null && item.dataset.label !== 'range-lower',
            callbacks: {
              title: (items) => (items.length ? fmtDay(items[0].parsed.x) : ''),
              label: (c) => `${c.dataset.label}: €${c.parsed.y.toFixed(3)}/L`,
            },
          },
        },
        scales: {
          x: {
            type: 'linear',
            min: hist[0].x,
            max: Math.max(hist[hist.length - 1].x, ...(fc.line.length ? [fc.line[fc.line.length - 1].x] : [])),
            grid: { color: '#21262d' },
            ticks: { color: '#8b949e', maxRotation: 0, maxTicksLimit: 6, callback: (v) => fmtDay(v) },
          },
          y: {
            min: lo - pad,
            max: hi + pad,
            grid: { color: '#30363d' },
            ticks: { color: '#8b949e', callback: (v) => '€' + v.toFixed(2) },
            title: { display: true, text: '€ per litre', color: '#6e7681', font: { size: 11 } },
          },
        },
      },
    })
  }

  $: if (canvas && history) {
    horizons, originDate, originPrice
    render()
  }

  onDestroy(() => chart?.destroy())
</script>

<div class="wrap">
  <canvas bind:this={canvas} role="img" aria-label="Price history with forecast"></canvas>
</div>

<style>
  .wrap {
    position: relative;
    height: 260px;
  }

  @media (min-width: 640px) {
    .wrap {
      height: 320px;
    }
  }
</style>
