<script>
  // History tab: one period control that applies to everything on this tab.
  import PriceChart from './PriceChart.svelte'
  import HistoryStats from './HistoryStats.svelte'
  import LowestPrices from './LowestPrices.svelte'
  import OilPrice from './OilPrice.svelte'
  import { readPref, writePref } from '../lib/format.js'

  export let fuelType = 'e5'

  // Hours from 1 January (local) to now.
  function ytdHours() {
    const now = new Date()
    return Math.max(24, Math.floor((now - new Date(now.getFullYear(), 0, 1)) / 3600000))
  }

  const ranges = [
    { key: '24h', label: '24h', hours: 24, text: 'last 24 hours' },
    { key: '3d', label: '3d', hours: 72, text: 'last 3 days' },
    { key: '7d', label: '7d', hours: 168, text: 'last 7 days' },
    { key: '1m', label: '1m', hours: 720, text: 'last 30 days' },
    { key: 'ytd', label: 'YTD', hours: ytdHours(), text: 'since 1 January' },
    { key: 'all', label: 'All', hours: 999999, text: 'all recorded data' },
  ]

  let rangeKey = readPref('fuel_period', '24h')
  if (!ranges.some((r) => r.key === rangeKey)) rangeKey = '24h'
  $: range = ranges.find((r) => r.key === rangeKey)
  $: writePref('fuel_period', rangeKey)

  let rows = []
  let oilOpen = false
</script>

<div class="period">
  <span class="label" id="period-label">Period</span>
  <div class="seg" role="group" aria-labelledby="period-label">
    {#each ranges as r}
      <button class:active={rangeKey === r.key} aria-pressed={rangeKey === r.key} on:click={() => (rangeKey = r.key)}>
        {r.label}
      </button>
    {/each}
  </div>
</div>

<div class="card">
  <PriceChart {fuelType} hours={range.hours} on:data={(e) => (rows = e.detail)} />
</div>

<div class="grid">
  <div class="card">
    <HistoryStats {fuelType} {rows} periodLabel={range.text} />
  </div>
  <div class="card">
    <h2>Cheapest stations <span class="sub">{range.text}</span></h2>
    <LowestPrices {fuelType} hours={range.hours} />
  </div>
</div>

<details class="card fold" bind:open={oilOpen}>
  <summary>Brent crude oil &amp; energy news</summary>
  {#if oilOpen}
    <div class="oil"><OilPrice hours={range.hours} /></div>
  {/if}
</details>

<style>
  .period {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
    overflow-x: auto;
  }

  .label {
    font-weight: 600;
    color: #6e7681;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .seg {
    display: inline-flex;
    gap: 2px;
    padding: 3px;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
  }

  .seg button {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: #8b949e;
    font-size: 0.8rem;
    font-weight: 500;
    padding: 0.3rem 0.65rem;
    min-height: 2rem;
    cursor: pointer;
  }

  .seg button:hover {
    background: #21262d;
    color: #c9d1d9;
  }

  .seg button.active {
    background: rgba(59, 130, 246, 0.16);
    border-color: #3b82f6;
    color: #79b8ff;
  }

  .card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 0.75rem;
    margin-bottom: 1rem;
  }

  .grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 0 1rem;
  }

  h2 {
    margin: 0 0 0.75rem;
    font-size: 1.1rem;
    color: #e6edf3;
  }

  .sub {
    color: #8b949e;
    font-weight: 400;
    font-size: 0.85em;
  }

  .fold > summary {
    cursor: pointer;
    list-style: none;
    font-weight: 600;
    color: #e6edf3;
    display: flex;
    align-items: center;
    min-height: 1.75rem;
  }

  .fold > summary::-webkit-details-marker {
    display: none;
  }

  .fold > summary::before {
    content: '▸';
    color: #8b949e;
    display: inline-block;
    width: 1rem;
    transition: transform 0.15s;
  }

  .fold[open] > summary::before {
    transform: rotate(90deg);
  }

  .oil {
    margin-top: 0.75rem;
  }

  @media (min-width: 640px) {
    .card {
      padding: 1.25rem;
      margin-bottom: 1.5rem;
    }
    .seg button {
      padding: 0.3rem 0.85rem;
    }
    h2 {
      font-size: 1.2rem;
    }
  }

  @media (min-width: 1024px) {
    .card {
      padding: 1.5rem;
    }
    .grid {
      grid-template-columns: 1fr 1fr;
      gap: 0 1.5rem;
    }
  }
</style>
