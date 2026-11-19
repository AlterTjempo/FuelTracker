<script>
  import { onMount } from 'svelte'
  import { getFavorites, removeFavorite } from '../lib/api.js'
  import StationRow from './StationRow.svelte'
  import StationDetail from './StationDetail.svelte'

  export let selectedFuelType = 'e5'

  let favorites = []
  let loading = true
  let error = null
  let selectedStationId = null

  async function loadFavorites() {
    loading = true
    error = null
    try {
      favorites = await getFavorites()
    } catch (err) {
      error = err.message || 'Failed to load favorites'
    } finally {
      loading = false
    }
  }

  async function handleRemoveFavorite(stationId) {
    try {
      await removeFavorite(stationId)
      favorites = favorites.filter((f) => f.id !== stationId)
    } catch (err) {
      error = err.message || 'Failed to remove favorite'
    }
  }

  // The response carries every fuel's price, so switching fuel needs no reload.
  const priceOf = (station, fuel) => station[`current_${fuel}`] ?? null
  $: sorted = [...favorites].sort(
    (a, b) => (priceOf(a, selectedFuelType) ?? Infinity) - (priceOf(b, selectedFuelType) ?? Infinity)
  )

  onMount(loadFavorites)
</script>

<h2>Your stations</h2>

{#if loading}
  <div class="state">Loading…</div>
{:else if error}
  <div class="state">
    {error}
    <button class="retry" on:click={loadFavorites}>Retry</button>
  </div>
{:else if favorites.length === 0}
  <p class="state">Star stations in the <strong>Stations</strong> tab to see them here.</p>
{:else}
  <div class="list">
    {#each sorted as station (station.id)}
      <StationRow
        name={station.name}
        brand={station.brand}
        city={station.city}
        price={priceOf(station, selectedFuelType)}
        closed={!station.is_open}
        lat={station.latitude}
        lon={station.longitude}
        on:open={() => (selectedStationId = station.id)}
      >
        <button class="unstar" on:click={() => handleRemoveFavorite(station.id)}
          title="Remove from your stations" aria-label="Remove {station.name} from your stations">★</button>
      </StationRow>
    {/each}
  </div>
{/if}

{#if selectedStationId}
  <StationDetail stationId={selectedStationId} on:close={() => (selectedStationId = null)} />
{/if}

<style>
  h2 {
    margin: 0 0 0.5rem;
    font-size: 1.1rem;
    color: #e6edf3;
  }

  .list {
    display: flex;
    flex-direction: column;
  }

  .state {
    color: #8b949e;
    font-size: 0.85rem;
    margin: 0;
    padding: 0.25rem 0;
  }

  .retry {
    margin-left: 0.5rem;
    background: #21262d;
    border: 1px solid #30363d;
    color: #c9d1d9;
    border-radius: 6px;
    padding: 0.25rem 0.6rem;
    cursor: pointer;
  }

  .unstar {
    background: none;
    border: none;
    color: #f59e0b;
    font-size: 1.15rem;
    cursor: pointer;
    padding: 0.25rem;
    min-width: 2rem;
    min-height: 2rem;
  }

  .unstar:hover {
    color: #6e7681;
  }

  @media (min-width: 640px) {
    h2 {
      font-size: 1.2rem;
    }
  }
</style>
