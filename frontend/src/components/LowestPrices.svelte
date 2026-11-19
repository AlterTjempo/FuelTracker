<script>
  // Lowest price each station reached within the selected period.
  import { onMount } from 'svelte'
  import { poll } from '../lib/poll.js'
  import API_BASE, { safeFetch } from '../lib/api.js'
  import StationRow from './StationRow.svelte'
  import StationDetail from './StationDetail.svelte'

  export let fuelType = 'e5'
  export let hours = 24

  let lowestPrices = []
  let loading = true
  let selectedStationId = null

  async function fetchLowest() {
    try {
      const data = await safeFetch(`${API_BASE}/prices/lowest?fuel_type=${encodeURIComponent(fuelType)}&hours=${hours}&limit=5`)
      if (!Array.isArray(data)) throw new Error('Unexpected response format')
      lowestPrices = data
    } catch (error) {
      console.error('Error fetching lowest prices:', error)
    } finally {
      loading = false
    }
  }

  onMount(() => {
    const interval = poll(fetchLowest, 60000)
    return () => clearInterval(interval)
  })

  $: fuelType, hours, fetchLowest()
</script>

{#if loading}
  <div class="state">Loading…</div>
{:else if lowestPrices.length === 0}
  <div class="state">No data in this period.</div>
{:else}
  <div class="list">
    {#each lowestPrices as item, index (item.station_id)}
      <StationRow
        rank={index + 1}
        highlight={index === 0}
        name={item.station_name}
        city={item.city}
        price={item.price}
        route={false}
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
