<script>
  import { onMount } from 'svelte'
  import API_BASE, { safeFetch } from '../lib/api.js'

  export let fuelType = 'e5'

  const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
  const HOURS = Array.from({ length: 24 }, (_, i) => i)

  let rawData = []
  let grid = []   // grid[hour][day] = avg_price | null
  let globalMin = 0
  let globalMax = 0
  let loading = true
  let noData = false
  let hoveredPrice = null

  async function fetchHeatmap() {
    loading = true
    noData = false
    try {
      const res = await safeFetch(`${API_BASE}/prices/analytics/heatmap?fuel_type=${encodeURIComponent(fuelType)}&days=30`)
      rawData = res

      if (!rawData.length) { noData = true; loading = false; return }

      grid = HOURS.map(() => Array(7).fill(null))
      rawData.forEach(({ day_of_week, hour_of_day, avg_price }) => {
        grid[hour_of_day][day_of_week] = avg_price
      })

      const prices = rawData.map(d => d.avg_price)
      globalMin = Math.min(...prices)
      globalMax = Math.max(...prices)
    } catch (e) {
      console.error('Heatmap fetch error', e)
      noData = true
    } finally {
      loading = false
    }
  }

  function lerpColor(a, b, t) {
    const ah = parseInt(a.slice(1), 16)
    const bh = parseInt(b.slice(1), 16)
    const ar = (ah >> 16) & 0xff, ag = (ah >> 8) & 0xff, ab = ah & 0xff
    const br = (bh >> 16) & 0xff, bg = (bh >> 8) & 0xff, bb = bh & 0xff
    const r = Math.round(ar + (br - ar) * t)
    const g = Math.round(ag + (bg - ag) * t)
    const b_ = Math.round(ab + (bb - ab) * t)
    return `rgb(${r},${g},${b_})`
  }

  // calm cool-to-warm: deep blue → steel blue → soft amber  (no red)
  function cellColor(price) {
    if (price === null || globalMax === globalMin) return '#1c2128'
    const t = (price - globalMin) / (globalMax - globalMin)
    if (t < 0.5) return lerpColor('#1e40af', '#38bdf8', t * 2)
    return lerpColor('#38bdf8', '#d97706', (t - 0.5) * 2)
  }

  onMount(() => {
    fetchHeatmap()
    const iv = setInterval(fetchHeatmap, 5 * 60 * 1000)
    return () => clearInterval(iv)
  })

  $: if (fuelType) fetchHeatmap()
</script>

<div class="heatmap-wrap">
  <div class="header">
    <h3>🌡️ Price Heatmap</h3>
  </div>

  {#if loading}
    <div class="state">Loading…</div>
  {:else if noData}
    <div class="state">Not enough data yet.</div>
  {:else}
    <div class="legend-row">
      <div class="legend">
        <span class="legend-label">Low €{globalMin.toFixed(3)}</span>
        <div class="legend-bar"></div>
        <span class="legend-label">High €{globalMax.toFixed(3)}</span>
      </div>
      {#if hoveredPrice !== null}
        <span class="hover-price">€{hoveredPrice.toFixed(3)}</span>
      {/if}
    </div>

    <div class="grid-wrap">
      <!-- Day headers -->
      <div class="row header-row">
        <div class="hour-label"></div>
        {#each DAYS as day}
          <div class="day-label">{day}</div>
        {/each}
      </div>

      <!-- Hour rows -->
      {#each HOURS as hour}
        <div class="row">
          <div class="hour-label">{String(hour).padStart(2, '0')}</div>
          {#each Array(7) as _, day}
            {@const price = grid[hour]?.[day] ?? null}
            <div
              class="cell"
              class:empty={price === null}
              style="background:{cellColor(price)}"
              title={price !== null ? `${DAYS[day]} ${String(hour).padStart(2,'0')}:00 — €${price.toFixed(3)}` : ''}
              on:mouseenter={() => { if (price !== null) hoveredPrice = price }}
              on:mouseleave={() => hoveredPrice = null}
            ></div>
          {/each}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .heatmap-wrap {
    /* parent card provides the container */
  }

  .header {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }

  h3 {
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
    color: #e6edf3;
  }

  .subtitle {
    font-size: 0.75rem;
    color: #6e7681;
  }

  .state {
    color: #8b949e;
    font-size: 0.85rem;
    padding: 2rem 0;
    text-align: center;
  }

  /* ── Legend ── */
  .legend-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.75rem;
    min-height: 1.25rem;
  }

  .legend {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .legend-label {
    font-size: 0.68rem;
    color: #6e7681;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }

  .legend-bar {
    width: 100px;
    height: 6px;
    border-radius: 99px;
    background: linear-gradient(to right, #1e40af, #38bdf8, #d97706);
  }

  .hover-price {
    font-size: 0.8rem;
    font-weight: 700;
    color: #e6edf3;
    font-variant-numeric: tabular-nums;
    transition: opacity 0.15s;
  }

  /* ── Grid ── */
  .grid-wrap {
    display: flex;
    flex-direction: column;
    gap: 2px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .row {
    display: grid;
    grid-template-columns: 28px repeat(7, 1fr);
    gap: 2px;
    min-width: 320px;
  }

  .header-row {
    margin-bottom: 2px;
  }

  .hour-label {
    font-size: 0.6rem;
    color: #484f58;
    text-align: right;
    padding-right: 4px;
    line-height: 1;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    user-select: none;
    font-variant-numeric: tabular-nums;
  }

  .day-label {
    font-size: 0.6rem;
    color: #6e7681;
    text-align: center;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    user-select: none;
  }

  /* ── Cell ── */
  .cell {
    height: 10px;
    border-radius: 2px;
    cursor: default;
    transition: transform 0.1s, box-shadow 0.1s;
  }

  .cell:hover {
    transform: scaleY(1.5);
    box-shadow: 0 0 0 1px rgba(255,255,255,0.3);
    z-index: 2;
    position: relative;
  }

  .cell.empty {
    background: #161b22 !important;
  }

  /* Tablet */
  @media (min-width: 640px) {
    .row {
      grid-template-columns: 32px repeat(7, 1fr);
      gap: 3px;
    }
    .grid-wrap { gap: 3px; }
    .hour-label { font-size: 0.65rem; }
    .day-label  { font-size: 0.65rem; }
    .legend-bar { width: 120px; }
    .cell { height: 13px; border-radius: 3px; }
  }

  /* Desktop */
  @media (min-width: 1024px) {
    .row {
      grid-template-columns: 36px repeat(7, 1fr);
    }
    .cell { height: 15px; border-radius: 3px; }
  }
</style>
