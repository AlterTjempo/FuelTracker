<script>
  import API_BASE, { safeFetch } from '../lib/api.js'
  import { eur3, getPosition, readPref, routeUrl, timeAgo, writePref } from '../lib/format.js'
  import StationDetail from './StationDetail.svelte'

  export let fuelType = 'e5'

  let indicator = null
  let loading = true
  let selectedStationId = null

  // Which stations count. "Within x km" asks the browser for the location once
  // and sends it with the request; it is never stored.
  const scopes = [
    { value: 'all', label: 'All stations' },
    { value: '5', label: 'Within 5 km' },
    { value: '10', label: 'Within 10 km' },
    { value: '25', label: 'Within 25 km' },
  ]
  let scope = readPref('fuel_go_scope', 'all')
  let scopeNote = ''

  async function onScopeChange() {
    writePref('fuel_go_scope', scope)
    await fetchIndicator()
  }

  async function fetchIndicator() {
    try {
      const params = new URLSearchParams({ fuel_type: fuelType })
      scopeNote = ''
      if (scope !== 'all') {
        try {
          const coords = await getPosition()
          params.set('lat', coords.lat)
          params.set('lon', coords.lon)
          params.set('max_distance_km', scope)
        } catch {
          scope = 'all'
          scopeNote = 'Location not available, showing all stations.'
        }
      }
      indicator = await safeFetch(`${API_BASE}/prices/analytics/go-now?${params}`)
    } catch (error) {
      console.error('Error fetching indicator:', error)
    } finally {
      loading = false
    }
  }

  $: fuelType && fetchIndicator()

  const LOOK = {
    excellent: { color: '#10b981', text: 'Go! Excellent price' },
    good: { color: '#22c55e', text: 'Good time to refuel' },
    neutral: { color: '#8b949e', text: 'Average price' },
    wait: { color: '#f59e0b', text: 'Consider waiting' },
    avoid: { color: '#ef4444', text: 'Wait for a better price' },
  }

  const TREND = {
    falling: { color: '#10b981', arrow: '↘', word: 'Falling' },
    rising: { color: '#ef4444', arrow: '↗', word: 'Rising' },
    stable: { color: '#8b949e', arrow: '→', word: 'Stable' },
  }

  $: ok = indicator && indicator.recommendation !== 'insufficient_data'
  $: look = ok ? LOOK[indicator.recommendation] || LOOK.neutral : null
  $: trend = ok && indicator.trend_direction ? TREND[indicator.trend_direction] || TREND.stable : null
  $: trendText = trend
    ? indicator.trend_direction === 'stable'
      ? 'Stable'
      : `${trend.word} ${Math.abs(indicator.trend)}¢/h`
    : ''
</script>

<section class="go" style="--tone: {look ? look.color : '#30363d'}">
  <div class="top">
    <h2>Should I refuel now?</h2>
    <select class="scope" bind:value={scope} on:change={onScopeChange} aria-label="Which stations count">
      {#each scopes as o}<option value={o.value}>{o.label}</option>{/each}
    </select>
  </div>
  {#if scopeNote}<div class="note">{scopeNote}</div>{/if}

  {#if loading}
    <div class="note">Loading…</div>
  {:else if !ok}
    <p class="note">
      {#if scope !== 'all'}No current prices from stations in this range. Try a wider range.{:else}Not enough data yet. Check back after more price data is collected.{/if}
    </p>
  {:else}
    <div class="verdict">{look.text}</div>

    <div class="best">
      <div class="best-main">
        <span class="price">{eur3(indicator.current_price)}</span>
        {#if indicator.station_name}
          <span class="where">
            at <button class="station" on:click={() => (selectedStationId = indicator.station_id)}>{indicator.station_name}</button>
            {#if indicator.price_timestamp}<span class="age">· {timeAgo(indicator.price_timestamp)}</span>{/if}
          </span>
        {/if}
      </div>
      {#if indicator.station_name}
        <a class="route" target="_blank" rel="noopener noreferrer"
          href={routeUrl({ lat: indicator.station_lat, lon: indicator.station_lon, name: indicator.station_name })}>Route</a>
      {/if}
    </div>

    <div class="chips">
      <span class="chip">Cheaper than <strong>{Math.round(100 - indicator.percentile)}%</strong> of prices at this hour</span>
      {#if trend}
        <span class="chip" style="color: {trend.color}">{trend.arrow} {trendText}</span>
      {/if}
    </div>

    <details class="more">
      <summary>Compare with this week</summary>
      <div class="track" aria-hidden="true">
        <div class="fill" style="width: {indicator.percentile}%"></div>
        <div class="dot" style="left: {indicator.percentile}%"></div>
      </div>
      <div class="track-labels"><span>Cheapest</span><span>Priciest</span></div>
      <div class="week">
        <div><span class="lbl">Week low</span><span class="val low">{eur3(indicator.week_low)}</span></div>
        <div><span class="lbl">Median</span><span class="val">{eur3(indicator.week_median)}</span></div>
        <div><span class="lbl">Week high</span><span class="val high">{eur3(indicator.week_high)}</span></div>
      </div>
    </details>
  {/if}
</section>

{#if selectedStationId}
  <StationDetail stationId={selectedStationId} on:close={() => (selectedStationId = null)} />
{/if}

<style>
  .go {
    background: #161b22;
    border: 1px solid #30363d;
    border-left: 4px solid var(--tone);
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
  }

  .top {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  h2 {
    margin: 0;
    font-size: 0.85rem;
    font-weight: 600;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .scope {
    margin-left: auto;
    background: #0f1419;
    border: 1px solid #30363d;
    color: #8b949e;
    border-radius: 6px;
    padding: 0.25rem 0.5rem;
    font-size: 0.78rem;
    min-height: 2rem;
  }

  .note {
    color: #8b949e;
    font-size: 0.85rem;
    margin: 0.25rem 0 0;
  }

  .verdict {
    font-size: 1.45rem;
    font-weight: 700;
    color: var(--tone);
    line-height: 1.2;
    margin-bottom: 0.6rem;
  }

  .best {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .best-main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.15rem 0.5rem;
  }

  .price {
    font-size: 2rem;
    font-weight: 700;
    color: #e6edf3;
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
  }

  .where {
    color: #8b949e;
    font-size: 0.85rem;
    min-width: 0;
  }

  .station {
    background: none;
    border: none;
    padding: 0;
    color: #c9d1d9;
    font: inherit;
    font-weight: 600;
    cursor: pointer;
    text-align: left;
  }

  .station:hover {
    color: #58a6ff;
    text-decoration: underline;
  }

  .age {
    color: #6e7681;
  }

  .route {
    flex-shrink: 0;
    background: #3b82f6;
    color: #fff;
    text-decoration: none;
    font-weight: 600;
    font-size: 0.9rem;
    border-radius: 8px;
    padding: 0.6rem 1rem;
    touch-action: manipulation;
  }

  .route:hover {
    background: #2563eb;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-top: 0.75rem;
  }

  .chip {
    font-size: 0.78rem;
    color: #8b949e;
    background: #1c2128;
    border: 1px solid #30363d;
    border-radius: 999px;
    padding: 0.2rem 0.65rem;
    font-weight: 500;
  }

  .chip strong {
    color: #e6edf3;
  }

  .more {
    margin-top: 0.75rem;
  }

  .more summary {
    cursor: pointer;
    color: #58a6ff;
    font-size: 0.82rem;
    list-style: none;
    min-height: 1.75rem;
    display: flex;
    align-items: center;
  }

  .more summary::-webkit-details-marker {
    display: none;
  }

  .more summary::before {
    content: '▸';
    display: inline-block;
    width: 1rem;
    color: #8b949e;
    transition: transform 0.15s;
  }

  .more[open] summary::before {
    transform: rotate(90deg);
  }

  .track {
    position: relative;
    height: 8px;
    background: #21262d;
    border-radius: 4px;
    margin-top: 0.75rem;
  }

  .fill {
    height: 100%;
    border-radius: 4px;
    background: var(--tone);
    opacity: 0.35;
  }

  .dot {
    position: absolute;
    top: 50%;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--tone);
    border: 2px solid #161b22;
    transform: translate(-50%, -50%);
  }

  .track-labels {
    display: flex;
    justify-content: space-between;
    font-size: 0.65rem;
    color: #6e7681;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-top: 0.3rem;
  }

  .week {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.5rem;
    margin-top: 0.75rem;
    text-align: center;
  }

  .week > div {
    display: flex;
    flex-direction: column;
  }

  .lbl {
    font-size: 0.68rem;
    color: #6e7681;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .val {
    font-weight: 700;
    color: #c9d1d9;
    font-variant-numeric: tabular-nums;
  }

  .val.low {
    color: #10b981;
  }

  .val.high {
    color: #ef4444;
  }

  @media (min-width: 640px) {
    .go {
      padding: 1.25rem 1.5rem;
      margin-bottom: 1.5rem;
    }
    .verdict {
      font-size: 1.75rem;
    }
    .price {
      font-size: 2.4rem;
    }
    .where {
      font-size: 0.95rem;
    }
  }
</style>
