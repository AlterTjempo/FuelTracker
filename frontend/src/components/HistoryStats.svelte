<script>
  // Period statistics (from the chart's rows) plus the all-time lowest price.
  import API_BASE, { safeFetch } from '../lib/api.js'
  import { eur3 } from '../lib/format.js'

  export let fuelType = 'e5'
  export let rows = []
  export let periodLabel = ''

  let lowestEver = null

  async function fetchLowestEver() {
    try {
      lowestEver = await safeFetch(`${API_BASE}/prices/analytics/lowest-ever?fuel_type=${encodeURIComponent(fuelType)}`)
    } catch (e) {
      console.error('Error fetching lowest-ever price:', e)
      lowestEver = null
    }
  }

  $: fuelType, fetchLowestEver()

  $: avgs = rows.map((d) => d.avg_price).filter((p) => p !== null)
  $: mins = rows.map((d) => d.min_price).filter((p) => p !== null)
  $: maxs = rows.map((d) => d.max_price).filter((p) => p !== null)
  $: stats = avgs.length
    ? {
        avg: avgs.reduce((a, b) => a + b, 0) / avgs.length,
        min: Math.min(...mins),
        max: Math.max(...maxs),
      }
    : null

  const dateFormatter = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Berlin',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
</script>

<h2>Prices <span class="period">{periodLabel}</span></h2>

{#if stats}
  <div class="tiles">
    <div class="tile low"><span class="l">Lowest</span><span class="v">{eur3(stats.min)}</span></div>
    <div class="tile"><span class="l">Average</span><span class="v">{eur3(stats.avg)}</span></div>
    <div class="tile high"><span class="l">Highest</span><span class="v">{eur3(stats.max)}</span></div>
    <div class="tile">
      <span class="l">Spread</span>
      <span class="v">{eur3(stats.max - stats.min)}</span>
      <span class="s">{(((stats.max - stats.min) / stats.min) * 100).toFixed(1)}%</span>
    </div>
  </div>
{:else}
  <p class="state">No data in this period.</p>
{/if}

{#if lowestEver && lowestEver.price}
  <div class="record">
    <span class="l">All-time lowest</span>
    <span class="v">€{lowestEver.price}</span>
    <span class="s">
      {dateFormatter.format(new Date(lowestEver.timestamp))} · {lowestEver.station_name}{lowestEver.city ? `, ${lowestEver.city}` : ''}
    </span>
  </div>
{/if}

<style>
  h2 {
    margin: 0 0 0.75rem;
    font-size: 1.1rem;
    color: #e6edf3;
  }

  .period {
    color: #8b949e;
    font-weight: 400;
    font-size: 0.85em;
  }

  .tiles {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.5rem;
  }

  .tile,
  .record {
    background: #1c2128;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 0.6rem 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }

  .l {
    color: #8b949e;
    font-size: 0.75rem;
  }

  .v {
    font-size: 1.2rem;
    font-weight: 700;
    color: #e6edf3;
    font-variant-numeric: tabular-nums;
  }

  .s {
    color: #6e7681;
    font-size: 0.75rem;
  }

  .low .v {
    color: #10b981;
  }

  .high .v {
    color: #ef4444;
  }

  .record {
    margin-top: 0.75rem;
    border-left: 3px solid #f59e0b;
  }

  .state {
    color: #8b949e;
    margin: 0;
  }

  @media (min-width: 640px) {
    h2 {
      font-size: 1.2rem;
    }
    .tiles {
      grid-template-columns: repeat(4, 1fr);
    }
  }
</style>
