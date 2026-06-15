<script>
  import { onMount } from 'svelte';
  import { getFavorites, removeFavorite } from '../lib/api.js';
  import StationDetail from './StationDetail.svelte';
  
  export let selectedFuelType = 'e5';
  
  let favorites = [];
  let loading = true;
  let error = null;
  let selectedStationId = null;
  
  async function loadFavorites() {
    loading = true;
    error = null;
    
    try {
      favorites = await getFavorites();
    } catch (err) {
      error = err.message || 'Failed to load favorites';
    } finally {
      loading = false;
    }
  }
  
  async function handleRemoveFavorite(stationId) {
    try {
      await removeFavorite(stationId);
      favorites = favorites.filter(f => f.id !== stationId);
    } catch (err) {
      error = err.message || 'Failed to remove favorite';
    }
  }
  
  function getPriceForFuelType(station) {
    switch(selectedFuelType) {
      case 'e5': return station.current_e5;
      case 'e10': return station.current_e10;
      case 'diesel': return station.current_diesel;
      default: return null;
    }
  }
  
  function formatPrice(price) {
    if (price === null || price === undefined) return 'N/A';
    return `€${price.toFixed(3)}`;
  }
  
  onMount(loadFavorites);
  
  // Reload when fuel type changes
  $: if (selectedFuelType) {
    loadFavorites();
  }
</script>

<div class="favorites">
  <h2>⭐ Your Favorite Stations</h2>
  
  {#if loading}
    <div class="loading">Loading favorites...</div>
  {:else if error}
    <div class="error">
      {error}
      <button on:click={loadFavorites}>Retry</button>
    </div>
  {:else if favorites.length === 0}
    <div class="empty">
      <p>No favorite stations yet. Star a station from the All Stations tab!</p>
    </div>
  {:else}
    <div class="favorites-list">
      {#each favorites as station (station.id)}
        <div class="favorite-row">
          <div class="row-left">
            <button class="name-link" on:click={() => selectedStationId = station.id}>
              {station.name}
            </button>
            {#if station.brand}
              <span class="brand-tag">{station.city}</span>
            {/if}
            {#if !station.is_open}
              <span class="closed-tag">CLOSED</span>
            {/if}
          </div>
          <div class="row-right">
            <span class="city">{station.city || ''}</span>
            <span class="price">{formatPrice(getPriceForFuelType(station))}</span>
            <button 
              class="remove-btn" 
              on:click={() => handleRemoveFavorite(station.id)}
              title="Remove from favorites"
            >✕</button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if selectedStationId}
  <StationDetail stationId={selectedStationId} on:close={() => selectedStationId = null} />
{/if}

<style>
  .favorites {
    padding: 0;
  }
  
  h2 {
    margin: 0 0 0.75rem 0;
    color: #c9d1d9;
    font-size: 1.1rem;
  }
  
  .loading {
    text-align: center;
    padding: 1.5rem;
    color: #8b949e;
  }
  
  .error {
    background: #3f1f1f;
    color: #ff7b72;
    padding: 0.75rem;
    border-radius: 6px;
    text-align: center;
    border: 1px solid #5a2828;
    font-size: 0.85rem;
  }
  
  .error button {
    margin-left: 0.5rem;
    padding: 0.25rem 0.75rem;
    background: #dc2626;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.8rem;
    min-height: auto;
  }
  
  .empty {
    text-align: center;
    padding: 1.5rem;
    color: #8b949e;
    font-size: 0.9rem;
  }
  
  .empty p {
    margin: 0;
  }
  
  .favorites-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .favorite-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    transition: border-color 0.2s;
  }
  
  .favorite-row:hover {
    border-color: #3b82f6;
  }
  
  .row-left {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-width: 0;
    flex: 1;
  }
  
  .row-right {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-shrink: 0;
  }
  
  .name-link {
    background: none;
    border: none;
    color: #e6edf3;
    font-weight: 600;
    font-size: 0.95rem;
    padding: 0;
    cursor: pointer;
    min-height: auto;
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  
  .name-link:hover {
    color: #3b82f6;
    text-decoration: underline;
  }
  
  .brand-tag {
    font-size: 0.8rem;
    color: #3fb950;
    font-weight: 600;
    white-space: nowrap;
  }
  
  .closed-tag {
    font-size: 0.6rem;
    font-weight: 700;
    color: #fff;
    background: #ef4444;
    padding: 0.1rem 0.3rem;
    border-radius: 3px;
    white-space: nowrap;
  }
  
  .city {
    color: #8b949e;
    font-size: 0.85rem;
    white-space: nowrap;
  }
  
  .price {
    font-size: 1.1rem;
    font-weight: 700;
    color: #3b82f6;
    white-space: nowrap;
    min-width: 4.5rem;
    text-align: right;
  }
  
  .remove-btn {
    background: none;
    border: none;
    color: #8b949e;
    font-size: 0.85rem;
    cursor: pointer;
    padding: 0.25rem;
    min-height: auto;
    line-height: 1;
    opacity: 0.5;
    transition: opacity 0.2s, color 0.2s;
  }
  
  .remove-btn:hover {
    opacity: 1;
    color: #f85149;
  }

  @media (max-width: 600px) {
    .city {
      display: none;
    }
  }
</style>
