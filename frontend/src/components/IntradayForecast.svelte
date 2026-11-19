<script>
  // Next 12 hours, hour by hour: real prices (solid), forecast (dotted grey) and
  // a grey band showing how sure the model is (from its own backtest).
  import { onDestroy, onMount } from 'svelte'
  import { Chart } from '../lib/chartSetup.js'
  import { poll } from '../lib/poll.js'
  import { getIntraday } from '../lib/api.js'
  import { eur3 } from '../lib/format.js'

  export let fuelType = 'e5'

  let data = null
  let loading = true
  let error = false
  let canvas
  let chart

  const HOUR = 3600 * 1000
  const ms = (iso) => new Date(iso).getTime()
  const hhmm = (v) =>
    new Date(v).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' })
  const signedCents = (c) => `${c > 0 ? '+' : c < 0 ? '−' : '±'}${Math.abs(c).toFixed(1)}¢`

  async function load() {
    const key = fuelType
    try {
      const d = await getIntraday(key)
      if (key !== fuelType) return
      data = d
      error = false
    } catch (e) {
      console.error('Error loading 12-hour forecast:', e)
      error = true
    } finally {
      loading = false
    }
  }

  $: fuelType, load()

  onMount(() => {
    const iv = poll(load, 5 * 60 * 1000) // the server regenerates it every 15 minutes
    return () => clearInterval(iv)
  })
  onDestroy(() => chart?.destroy())

  $: ok = data && !data.insufficient_data
  $: acc = data?.accuracy
  $: band = acc?.mae_by_hour_ahead?.length
    ? Math.max(...acc.mae_by_hour_ahead.map((r) => r.mae_cents))
    : null
  $: baselineText = acc
    ? Object.entries(acc.baselines)
        .map(([m, v]) => `${v}¢ for “${m === 'persistence' ? 'stays as it is now' : 'same hour yesterday'}”`)
        .join(' and ')
    : ''

  function render() {
    if (!canvas || !ok) return
    const hist = []
    let prev = null
    for (const h of data.history) {
      const x = ms(h.t)
      if (prev !== null && x - prev > 1.5 * HOUR) hist.push({ x: prev + HOUR / 2, y: null }) // real gap
      hist.push({ x, y: h.price })
      prev = x
    }
    const o = { x: ms(data.origin.t), y: data.origin.price }
    const line = [o, ...data.forecast.map((r) => ({ x: ms(r.t), y: r.price }))]
    const withBand = data.forecast.filter((r) => r.low !== undefined)
    const lower = [o, ...withBand.map((r) => ({ x: ms(r.t), y: r.low }))]
    const upper = [o, ...withBand.map((r) => ({ x: ms(r.t), y: r.high }))]

    const ys = [...hist, ...line, ...lower, ...upper].map((p) => p.y).filter((v) => v !== null)
    const lo = Math.min(...ys)
    const hi = Math.max(...ys)
    const pad = Math.max((hi - lo) * 0.1, 0.005)

    const nowMarker = {
      id: 'nowMarker',
      afterDatasetsDraw(c) {
        const { ctx, chartArea, scales } = c
        const px = scales.x.getPixelForValue(o.x)
        ctx.save()
        ctx.strokeStyle = '#6e7681'
        ctx.setLineDash([2, 4])
        ctx.beginPath()
        ctx.moveTo(px, chartArea.top)
        ctx.lineTo(px, chartArea.bottom)
        ctx.stroke()
        ctx.setLineDash([])
        ctx.fillStyle = '#8b949e'
        ctx.font = '11px sans-serif'
        ctx.fillText('Now', px + 4, chartArea.top + 12)
        ctx.restore()
      },
    }

    chart?.destroy()
    chart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        datasets: [
          {
            label: 'Real price',
            data: hist,
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59,130,246,0.08)',
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 4,
            spanGaps: false,
            order: 1,
          },
          { label: 'band-low', data: lower, borderColor: 'transparent', pointRadius: 0, fill: false, order: 3 },
          {
            label: 'How sure (80% band)',
            data: upper,
            borderColor: 'transparent',
            backgroundColor: 'rgba(139,148,158,0.18)',
            pointRadius: 0,
            fill: '-1',
            order: 3,
          },
          {
            label: 'Forecast',
            data: line,
            borderColor: '#8b949e',
            borderWidth: 2,
            borderDash: [3, 4],
            pointRadius: 2,
            pointBackgroundColor: '#8b949e',
            fill: false,
            order: 0,
          },
        ],
      },
      plugins: [nowMarker],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        parsing: false,
        animation: false,
        interaction: { mode: 'nearest', axis: 'x', intersect: false },
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: '#8b949e', boxWidth: 18, font: { size: 11 }, filter: (i) => i.text !== 'band-low' },
          },
          tooltip: {
            backgroundColor: '#161b22',
            borderColor: '#30363d',
            borderWidth: 1,
            titleColor: '#e6edf3',
            bodyColor: '#8b949e',
            filter: (i) => i.parsed.y !== null && i.dataset.label !== 'band-low',
            callbacks: {
              title: (items) => (items.length ? hhmm(items[0].parsed.x) : ''),
              label: (c) =>
                c.dataset.label === 'How sure (80% band)'
                  ? `Likely up to: €${c.parsed.y.toFixed(3)}`
                  : `${c.dataset.label}: €${c.parsed.y.toFixed(3)}`,
            },
          },
        },
        scales: {
          x: {
            type: 'linear',
            min: hist.length ? hist[0].x : o.x,
            max: line[line.length - 1].x,
            grid: { color: '#21262d' },
            // Ticks on whole hours, every 3 h (Berlin offsets are whole hours, so UTC alignment works).
            afterBuildTicks: (axis) => {
              const ticks = []
              for (let v = Math.ceil(axis.min / (3 * HOUR)) * 3 * HOUR; v <= axis.max; v += 3 * HOUR) ticks.push({ value: v })
              axis.ticks = ticks
            },
            ticks: { color: '#8b949e', maxRotation: 0, autoSkip: true, callback: (v) => hhmm(v) },
          },
          y: {
            min: lo - pad,
            max: hi + pad,
            grid: { color: '#30363d' },
            ticks: { color: '#8b949e', callback: (v) => '€' + v.toFixed(2) },
          },
        },
      },
    })
  }

  $: if (canvas && ok && data) render() // `data` listed so new results redraw
  $: if (!ok && chart) {
    chart.destroy()
    chart = null
  }
</script>

<section class="panel" aria-labelledby="intraday-h">
  <div class="head">
    <h3 id="intraday-h">Next 12 hours</h3>
    {#if acc}
      <span class="badge" data-tone={acc.level} title="Typical error in testing on {acc.test_hours} past hours">
        How sure: {acc.level}
      </span>
    {/if}
  </div>

  {#if loading && !data}
    <p class="muted">Loading…</p>
  {:else if error && !data}
    <p class="muted">Couldn't load the forecast. Retrying automatically…</p>
  {:else if !ok}
    <p class="muted">{data?.reason || 'No forecast available right now.'}</p>
  {:else}
    <div class="summary">
      <span>
        Cheapest: <strong>{hhmm(ms(data.summary.cheapest.t))}</strong>
        {eur3(data.summary.cheapest.price)}
        {#if data.summary.cheapest_vs_now_cents < 0}<em class="good">({signedCents(data.summary.cheapest_vs_now_cents)} vs now)</em>{/if}
      </span>
      {#if data.summary.biggest_rise && data.summary.biggest_rise.cents >= 2}
        <span>
          Price jump expected at <strong>{hhmm(ms(data.summary.biggest_rise.t))}</strong>
          <em class="warn">({signedCents(data.summary.biggest_rise.cents)})</em>
        </span>
      {/if}
    </div>

    <div class="chart" role="img" aria-label="Price over the last and next 12 hours"><canvas bind:this={canvas}></canvas></div>

    <p class="caption">
      Dotted line: expected area-average price. Typical error {acc.mae_cents}¢ (about
      {acc.mae_by_hour_ahead[0].mae_cents}¢ one hour ahead, {band}¢ at most further out), against {baselineText}.
      {#if !acc.beats_baselines}<strong>Right now it is not more accurate than these simple rules.</strong>{/if}
      {#if acc.band_coverage !== null}
        In testing on {acc.test_hours} past hours the real price fell inside the grey band
        {Math.round(acc.band_coverage * 100)}% of the time (aim: {Math.round(acc.band_target * 100)}%).
      {/if}
      Unexpected events (oil shocks, tax changes) are not foreseen.
    </p>
    <p class="caption method">Method: {data.method_name}.</p>
  {/if}
</section>

<style>
  .panel {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    margin-bottom: 0.6rem;
  }

  h3 {
    margin: 0;
    font-size: 1.05rem;
    color: #e6edf3;
  }

  .badge {
    font-size: 0.78rem;
    font-weight: 600;
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    border: 1px solid #30363d;
    color: #8b949e;
    background: #1c2128;
    white-space: nowrap;
  }

  .badge[data-tone='High'] {
    color: #10b981;
    border-color: rgba(16, 185, 129, 0.5);
  }

  .badge[data-tone='Medium'] {
    color: #58a6ff;
    border-color: rgba(88, 166, 255, 0.5);
  }

  .badge[data-tone='Low'] {
    color: #f59e0b;
    border-color: rgba(245, 158, 11, 0.45);
  }

  .summary {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem 1.25rem;
    color: #c9d1d9;
    font-size: 0.9rem;
    margin-bottom: 0.6rem;
  }

  .summary strong {
    color: #e6edf3;
  }

  em {
    font-style: normal;
  }

  .good {
    color: #10b981;
  }

  .warn {
    color: #f59e0b;
  }

  .chart {
    position: relative;
    height: 230px;
  }

  .muted {
    color: #8b949e;
    font-size: 0.9rem;
    margin: 0;
  }

  .caption.method {
    margin-top: 0.25rem;
    color: #6e7681;
  }

  .caption {
    color: #8b949e;
    font-size: 0.78rem;
    line-height: 1.5;
    margin: 0.75rem 0 0;
  }

  @media (min-width: 640px) {
    .panel {
      padding: 1.25rem;
    }
    .chart {
      height: 280px;
    }
  }
</style>
