<script>
  // "Usually cheapest" ranking (Literboard): which stations are cheap most of the
  // time, not just right now. Each row shows the two key numbers; tap for details.
  import { onMount } from 'svelte'
  import { poll } from '../lib/poll.js'
  import API_BASE, { safeFetch } from '../lib/api.js'
  import { readPref, writePref } from '../lib/format.js'
  import StationDetail from './StationDetail.svelte'

  export let fuelType = 'e5'

  const WINDOWS = [
    { label: '7 days', hours: 168 },
    { label: '30 days', hours: 720 },
  ]

  let hours = Number(readPref('fuel_lb_hours', '168')) || 168
  // Relate 'cheapest X% of the time' to the hours a station was open (had data).
  let weighted = readPref('fuel_lb_weighted') === '1'
  let stations = []
  let loading = true
  let error = false
  let expanded = null
  let selectedStationId = null

  async function fetchTop() {
    try {
      const params = new URLSearchParams({ fuel_type: fuelType, hours: String(hours), limit: '10' })
      if (weighted) params.set('opening_hours_weighted', 'true')
      const data = await safeFetch(`${API_BASE}/prices/analytics/top-stations?${params}`)
      stations = Array.isArray(data) ? data : []
      error = false
    } catch (e) {
      console.error('Error fetching top stations:', e)
      error = true
    } finally {
      loading = false
    }
  }

  onMount(() => {
    const interval = poll(fetchTop, 5 * 60 * 1000)
    return () => clearInterval(interval)
  })

  $: fuelType, hours, weighted, fetchTop()
  $: writePref('fuel_lb_hours', String(hours))
  $: writePref('fuel_lb_weighted', weighted ? '1' : '0')

  // Stability compares a station's typical daily price swing with the other stations.
  const STABILITY = {
    very_stable: { label: 'Very stable', color: '#10b981' },
    stable: { label: 'Stable', color: '#22c55e' },
    typical: { label: 'Typical', color: '#8b949e' },
    volatile: { label: 'Volatile', color: '#f59e0b' },
    very_volatile: { label: 'Very volatile', color: '#f97316' },
  }
  const stabilityInfo = (s) => STABILITY[s.stability] || { label: 'Not enough data', color: '#6e7681' }
  // Bar length: 50% = same swing as the typical station, capped at 100%.
  const swingBar = (s) => (s.swing_vs_market ? Math.min(s.swing_vs_market * 50, 100) : 0)

  $: ranked = stations.filter((s) => s.enough_data)
  $: unranked = stations.filter((s) => !s.enough_data)
</script>

<div class="controls">
  <div class="seg" role="group" aria-label="Ranking window">
    {#each WINDOWS as w}
      <button class:active={hours === w.hours} aria-pressed={hours === w.hours} on:click={() => (hours = w.hours)}>{w.label}</button>
    {/each}
  </div>
  <label class="check" title="Count 'cheapest X% of the time' only over the hours a station was open (had prices)">
    <input type="checkbox" bind:checked={weighted} />
    Only opening hours
  </label>
</div>

{#if loading}
  <div class="state">Loading…</div>
{:else if error && stations.length === 0}
  <div class="state">Couldn't load the ranking. Retrying automatically…</div>
{:else if ranked.length === 0}
  <div class="state">Not enough data to rank stations yet.</div>
{:else}
  {#if ranked.length > 1}
    <p class="insight">
      <strong>{ranked[0].name}</strong> is the cheapest station {ranked[0].cheapest_percentage}% of the time{#if ranked[1].min_price < ranked[0].min_price},
        but <strong>{ranked[1].name}</strong> dips lower (€{ranked[1].min_price} vs €{ranked[0].min_price}){/if}.
    </p>
  {/if}

  <div class="head" aria-hidden="true">
    <span></span><span>Station</span><span class="r">Avg</span><span class="r">Cheapest</span>
  </div>
  <ol class="list">
    {#each ranked as s (s.station_id)}
      <li class:open={expanded === s.station_id}>
        <button class="summary" aria-expanded={expanded === s.station_id} on:click={() => (expanded = expanded === s.station_id ? null : s.station_id)}>
          <span class="rank">{s.rank ?? '–'}</span>
          <span class="who">
            <span class="name">{s.name}</span>
            <span class="city">{s.city || s.brand || ''}</span>
          </span>
          <span class="r num">€{s.avg_price}</span>
          <span class="r num pct">{s.cheapest_percentage}%</span>
        </button>
        {#if expanded === s.station_id}
          <div class="details">
            <div class="kv"><span>Price range</span><span>€{(s.max_price - s.min_price).toFixed(3)} (€{s.min_price} – €{s.max_price})</span></div>
            <div class="kv">
              <span>Stability</span>
              <span style="color: {stabilityInfo(s).color}" title="Average daily price swing over 30 days compared with the typical station">
                {stabilityInfo(s).label}{#if s.daily_swing_cents !== null}{' · ' + s.daily_swing_cents + '¢ daily swing'}{/if}
              </span>
            </div>
            <div class="bar"><div style="width: {swingBar(s)}%; background: {stabilityInfo(s).color}"></div></div>
            <div class="data">Based on {s.hours_with_data} h over {s.days_with_data} days{#if s.stability_days}{' · stability from ' + s.stability_days + ' days'}{/if}</div>
            <button class="link" on:click={() => (selectedStationId = s.station_id)}>Station details →</button>
          </div>
        {/if}
      </li>
    {/each}
  </ol>

  {#if unranked.length}
    <p class="unranked">
      Not ranked (too little data): {unranked.map((s) => s.name).join(', ')}.
    </p>
  {/if}
{/if}

{#if selectedStationId}
  <StationDetail stationId={selectedStationId} on:close={() => (selectedStationId = null)} />
{/if}

<style>
  .controls {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem 1rem;
    margin-bottom: 0.75rem;
  }

  .seg {
    display: inline-flex;
    gap: 2px;
    padding: 3px;
    background: #0f1419;
    border: 1px solid #30363d;
    border-radius: 8px;
  }

  .seg button {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: #8b949e;
    font-size: 0.82rem;
    font-weight: 500;
    padding: 0.3rem 0.75rem;
    min-height: 2rem;
    cursor: pointer;
  }

  .seg button.active {
    background: rgba(59, 130, 246, 0.16);
    border-color: #3b82f6;
    color: #79b8ff;
  }

  .check {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    color: #c9d1d9;
    font-size: 0.85rem;
    cursor: pointer;
    min-height: 2rem;
  }

  .check input {
    width: 1.05rem;
    height: 1.05rem;
    accent-color: #3b82f6;
  }

  .insight {
    margin: 0 0 0.75rem;
    padding: 0.6rem 0.75rem;
    background: rgba(59, 130, 246, 0.08);
    border-radius: 6px;
    color: #c9d1d9;
    font-size: 0.85rem;
    line-height: 1.45;
  }

  .head,
  .summary {
    display: grid;
    grid-template-columns: 1.5rem 1fr 4.25rem 4.25rem;
    gap: 0.5rem;
    align-items: center;
  }

  .head {
    padding: 0 0.25rem 0.35rem;
    font-size: 0.68rem;
    color: #6e7681;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 1px solid #30363d;
  }

  .r {
    text-align: right;
  }

  .list {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .list li {
    border-bottom: 1px solid #21262d;
  }

  .list li.open {
    background: #1c2128;
    border-radius: 6px;
  }

  .summary {
    width: 100%;
    background: none;
    border: none;
    color: inherit;
    font: inherit;
    text-align: left;
    padding: 0.6rem 0.25rem;
    min-height: 3rem;
    cursor: pointer;
  }

  .summary:hover .name {
    color: #58a6ff;
  }

  .rank {
    text-align: center;
    color: #6e7681;
    font-size: 0.8rem;
    font-weight: 600;
  }

  .list li:first-child .rank {
    color: #58a6ff;
  }

  .who {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .name {
    font-weight: 600;
    color: #e6edf3;
    font-size: 0.9rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .city {
    color: #8b949e;
    font-size: 0.75rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .num {
    font-weight: 700;
    color: #e6edf3;
    font-variant-numeric: tabular-nums;
    font-size: 0.9rem;
  }

  .pct {
    color: #10b981;
  }

  .details {
    padding: 0 0.75rem 0.75rem 2.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    font-size: 0.82rem;
  }

  .kv {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    color: #c9d1d9;
  }

  .kv span:first-child {
    color: #8b949e;
  }

  .kv span:last-child {
    text-align: right;
  }

  .bar {
    height: 4px;
    background: #21262d;
    border-radius: 2px;
    overflow: hidden;
  }

  .bar div {
    height: 100%;
  }

  .data {
    color: #6e7681;
    font-size: 0.75rem;
  }

  .link {
    align-self: flex-start;
    background: none;
    border: none;
    color: #58a6ff;
    padding: 0.25rem 0;
    font-size: 0.82rem;
    cursor: pointer;
  }

  .unranked {
    color: #6e7681;
    font-size: 0.75rem;
    margin: 0.75rem 0 0;
  }

  .state {
    text-align: center;
    padding: 2rem 1rem;
    color: #8b949e;
  }

  @media (min-width: 640px) {
    .head,
    .summary {
      grid-template-columns: 2rem 1fr 6rem 6rem;
      gap: 0.75rem;
    }
    .num {
      font-size: 1rem;
    }
  }
</style>
