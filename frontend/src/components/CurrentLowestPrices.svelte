<script>
  import { onMount } from 'svelte'
  import { poll } from '../lib/poll.js'
  import API_BASE, { safeFetch } from '../lib/api.js'
  import { timeAgo } from '../lib/format.js'
  import StationRow from './StationRow.svelte'
  import StationDetail from './StationDetail.svelte'

  export let fuelType = 'e5'

  let lowestPrices = []
  let loading = true
  let error = false
  let selectedStationId = null

  async function fetchCurrentLowest() {
    try {
      const data = await safeFetch(`${API_BASE}/prices/current-lowest?fuel_type=${encodeURIComponent(fuelType)}&limit=5`)
      if (!Array.isArray(data)) throw new Error('Unexpected response format')
      lowestPrices = data
      error = false
    } catch (err) {
      console.error('Error fetching current lowest prices:', err)
      error = true
    } finally {
      loading = false
    }
  }

  onMount(() => {
    const interval = poll(fetchCurrentLowest, 60000)
    return () => clearInterval(interval)
  })

  $: fuelType, fetchCurrentLowest()
</script>

{#if loading}
  <div class="state">Loading…</div>
{:else if error && lowestPrices.length === 0}
  <div class="state">Couldn't load prices. Retrying automatically…</div>
{:else if lowestPrices.length === 0}
  <div class="state">No current prices yet.</div>
{:else}
  <div class="list">
    {#each lowestPrices as item, index (item.station_id)}
      <StationRow
        rank={index + 1}
        highlight={index === 0}
        name={item.station_name}
        city={item.city}
        meta={timeAgo(item.timestamp)}
        price={item.price}
        closed={!item.is_open}
        lat={item.latitude}
        lon={item.longitude}
        on:open={() => (selectedStationId = item.station_id)}
      />
    {/each}
  </div>
{/if}

{#if selectedStationId}
  <StationDetail stationId={selectedStationId} on:close={() => (selectedStationId = null)} />
{/if}

<style>
  .list {
    display: flex;
    flex-direction: column;
  }

  .state {
    text-align: center;
    padding: 1.5rem;
    color: #8b949e;
  }
</style>
