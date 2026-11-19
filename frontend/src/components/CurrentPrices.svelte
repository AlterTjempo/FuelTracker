<script>
  import { onMount } from 'svelte'
  import { poll } from '../lib/poll.js'
  import API_BASE, { safeFetch, addFavorite, removeFavorite, getFavorites } from '../lib/api.js'
  import { currentUser } from '../lib/auth.js'
  import { distanceKm, getPosition, readPref, timeAgo, writePref } from '../lib/format.js'
  import StationRow from './StationRow.svelte'
  import StationDetail from './StationDetail.svelte'

  export let fuelType = 'e5'

  const PAGE = 20

  let prices = []
  let loading = true
  let error = false
  let displayCount = PAGE
  let favoriteIds = new Set()
  let selectedStationId = null

  let query = ''
  let openOnly = readPref('fuel_stations_open') === '1'
  let sortBy = 'price' // 'price' | 'distance' (distance is not remembered: it needs a fresh location)
  let coords = null
  let locNote = ''

  async function loadFavorites() {
    try {
      const favs = await getFavorites()
      favoriteIds = new Set(favs.map((f) => f.id))
    } catch {
      favoriteIds = new Set()
    }
  }

  async function toggleFavorite(stationId) {
    try {
      if (favoriteIds.has(stationId)) {
        await removeFavorite(stationId)
        favoriteIds.delete(stationId)
      } else {
        await addFavorite(stationId)
        favoriteIds.add(stationId)
      }
      favoriteIds = favoriteIds
    } catch (err) {
      console.error('Favorite toggle failed:', err)
    }
  }

  async function fetchPrices() {
    try {
      const data = await safeFetch(`${API_BASE}/prices/current?limit=500`)
      if (!Array.isArray(data)) throw new Error('Unexpected response format')
      prices = data
      error = false
    } catch (err) {
      console.error('Error fetching prices:', err)
      error = true
    } finally {
      loading = false
    }
  }

  async function setSort(value) {
    locNote = ''
    if (value === 'distance' && !coords) {
      try {
        coords = await getPosition()
      } catch {
        locNote = 'Location not available, sorted by price.'
        sortBy = 'price'
        return
      }
    }
    sortBy = value
  }

  onMount(() => {
    fetchPrices()
    const interval = poll(fetchPrices, 60000)
    return () => clearInterval(interval)
  })

  $: if ($currentUser) loadFavorites()
  else favoriteIds = new Set()

  $: writePref('fuel_stations_open', openOnly ? '1' : '0')

  // Reset paging whenever what is shown changes.
  $: fuelType, query, openOnly, sortBy, (displayCount = PAGE)

  $: needle = query.trim().toLowerCase()
  $: rows = prices
    .filter((s) => s[fuelType] !== null && s[fuelType] !== undefined)
    .filter((s) => !openOnly || s.is_open)
    .filter((s) => !needle || [s.station_name, s.brand, s.city].some((v) => v && v.toLowerCase().includes(needle)))
    .map((s) => ({
      ...s,
      km: coords && s.latitude !== null && s.latitude !== undefined
        ? distanceKm(coords, { lat: s.latitude, lon: s.longitude })
        : null,
    }))
    .sort((a, b) =>
      sortBy === 'distance'
        ? (a.km ?? Infinity) - (b.km ?? Infinity) || a[fuelType] - b[fuelType]
        : a[fuelType] - b[fuelType]
    )
  $: cheapest = rows.length ? Math.min(...rows.map((r) => r[fuelType])) : null
</script>

<div class="toolbar">
  <input
    class="search"
    type="search"
    placeholder="Search name, brand or town"
    aria-label="Search stations"
    bind:value={query}
  />
  <div class="filters">
    <div class="seg" role="group" aria-label="Sort stations">
      <button class:active={sortBy === 'price'} aria-pressed={sortBy === 'price'} on:click={() => setSort('price')}>Cheapest</button>
      <button class:active={sortBy === 'distance'} aria-pressed={sortBy === 'distance'} on:click={() => setSort('distance')}>Nearest</button>
    </div>
    <label class="check">
      <input type="checkbox" bind:checked={openOnly} />
      Open now
    </label>
  </div>
</div>
{#if locNote}<div class="note">{locNote}</div>{/if}

{#if loading}
  <div class="state">Loading stations…</div>
{:else if error && prices.length === 0}
  <div class="state">Couldn't load stations. Retrying automatically…</div>
{:else if rows.length === 0}
  <div class="state">{prices.length ? 'No stations match.' : 'No station data available yet.'}</div>
{:else}
  <div class="count">{rows.length} station{rows.length === 1 ? '' : 's'}</div>
  <div class="list">
    {#each rows.slice(0, displayCount) as station, index (station.station_id)}
      <StationRow
        rank={sortBy === 'price' && !needle ? index + 1 : null}
        highlight={station[fuelType] === cheapest}
        name={station.station_name}
        brand={station.brand}
        city={station.city}
        meta={station.km !== null && sortBy === 'distance' ? `${station.km.toFixed(1)} km` : timeAgo(station.timestamp)}
        price={station[fuelType]}
        closed={!station.is_open}
        lat={station.latitude}
        lon={station.longitude}
        on:open={() => (selectedStationId = station.station_id)}
      >
        {#if $currentUser}
          <button
            class="star"
            class:on={favoriteIds.has(station.station_id)}
            on:click={() => toggleFavorite(station.station_id)}
            aria-pressed={favoriteIds.has(station.station_id)}
            aria-label={favoriteIds.has(station.station_id) ? `Remove ${station.station_name} from your stations` : `Add ${station.station_name} to your stations`}
          >{favoriteIds.has(station.station_id) ? '★' : '☆'}</button>
        {/if}
      </StationRow>
    {/each}
  </div>
  {#if displayCount < rows.length}
    <button class="more" on:click={() => (displayCount += PAGE)}>
      Show more <span>({displayCount} of {rows.length})</span>
    </button>
  {/if}
{/if}

{#if selectedStationId}
  <StationDetail stationId={selectedStationId} on:close={() => (selectedStationId = null)} />
{/if}

<style>
  .toolbar {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }

  .search {
    width: 100%;
    background: #0f1419;
    border: 1px solid #30363d;
    border-radius: 8px;
    color: #e6edf3;
    font-size: 1rem; /* 16px avoids iOS zoom-on-focus */
    padding: 0.55rem 0.75rem;
    min-height: 2.5rem;
  }

  .search:focus {
    border-color: #3b82f6;
    outline: none;
  }

  .filters {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
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

  .note,
  .count {
    color: #6e7681;
    font-size: 0.75rem;
    margin-bottom: 0.25rem;
  }

  .list {
    display: flex;
    flex-direction: column;
  }

  .state {
    text-align: center;
    padding: 2rem 1rem;
    color: #8b949e;
  }

  .star {
    background: none;
    border: none;
    color: #6e7681;
    font-size: 1.2rem;
    cursor: pointer;
    padding: 0.25rem;
    min-width: 2.25rem;
    min-height: 2.25rem;
  }

  .star.on {
    color: #f59e0b;
  }

  .star:hover {
    color: #f59e0b;
  }

  .more {
    display: block;
    width: 100%;
    margin-top: 0.75rem;
    background: #21262d;
    border: 1px solid #30363d;
    color: #c9d1d9;
    border-radius: 8px;
    padding: 0.6rem;
    min-height: 2.75rem;
    font-weight: 500;
    cursor: pointer;
  }

  .more span {
    color: #6e7681;
    font-weight: 400;
  }

  .more:hover {
    border-color: #3b82f6;
  }

  @media (min-width: 640px) {
    .toolbar {
      flex-direction: row;
      align-items: center;
    }
    .search {
      flex: 1;
      font-size: 0.9rem;
    }
    .filters {
      gap: 1rem;
    }
  }
</style>
