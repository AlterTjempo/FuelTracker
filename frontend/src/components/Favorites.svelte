<script>
  import { onMount } from 'svelte';
  import { getFavorites, removeFavorite } from '../lib/api.js';
  
  export let selectedFuelType = 'e5';
  
  let favorites = [];
  let loading = true;
  let error = null;
  
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
  <h2>Your Favorite Stations</h2>
  
  {#if loading}
    <div class="loading">Loading favorites...</div>
  {:else if error}
    <div class="error">
      {error}
      <button on:click={loadFavorites}>Retry</button>
    </div>
  {:else if favorites.length === 0}
    <div class="empty">
      <p>You haven't added any favorite stations yet.</p>
      <p>Browse the map or current prices to add favorites!</p>
    </div>
  {:else}
    <div class="favorites-list">
      {#each favorites as station (station.id)}
        <div class="favorite-card">
          <div class="station-info">
            <h3>{station.name}</h3>
            <p class="brand">{station.brand || 'Unknown Brand'}</p>
            <p class="address">
              {station.street} {station.house_number}<br>
              {station.post_code} {station.city}
            </p>
          </div>
          
          <div class="price-info">
            <div class="current-price">
              <span class="price">{formatPrice(getPriceForFuelType(station))}</span>
            </div>
            
            <div class="status {station.is_open ? 'open' : 'closed'}">
              {station.is_open ? '🟢 Open' : '🔴 Closed'}
            </div>
          </div>
          
          <button 
            class="remove-btn" 
            on:click={() => handleRemoveFavorite(station.id)}
            title="Remove from favorites"
          >
            ❌
          </button>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .favorites {
    padding: 1rem;
  }
  
  h2 {
    margin: 0 0 1.5rem 0;
    color: #c9d1d9;
  }
  
  .loading {
    text-align: center;
    padding: 3rem;
    color: #8b949e;
    font-size: 1.1rem;
  }
  
  .error {
    background: #3f1f1f;
    color: #ff7b72;
    padding: 1rem;
    border-radius: 4px;
    text-align: center;
    border: 1px solid #5a2828;
  }
  
  .error button {
    margin-top: 0.5rem;
    padding: 0.5rem 1rem;
    background: #dc2626;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  }
  
  .error button:hover {
    background: #b91c1c;
  }
  
  .empty {
    text-align: center;
    padding: 3rem;
    color: #8b949e;
  }
  
  .empty p {
    margin: 0.5rem 0;
  }
  
  .favorites-list {
    display: grid;
    gap: 1rem;
  }
  
  .favorite-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 1.25rem;
    position: relative;
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 1rem;
    transition: box-shadow 0.3s;
  }
  
  .favorite-card:hover {
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.4);
    border-color: #58a6ff;
  }
  
  .station-info h3 {
    margin: 0 0 0.5rem 0;
    color: #c9d1d9;
    font-size: 1.1rem;
  }
  
  .brand {
    margin: 0 0 0.5rem 0;
    color: #3fb950;
    font-weight: 600;
  }
  
  .address {
    margin: 0;
    color: #8b949e;
    font-size: 0.9rem;
    line-height: 1.4;
  }
  
  .price-info {
    text-align: right;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 0.5rem;
  }
  
  .current-price {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
  }
  
  .fuel-type {
    font-size: 0.75rem;
    color: #8b949e;
    text-transform: uppercase;
    font-weight: 600;
  }
  
  .price {
    font-size: 1.5rem;
    font-weight: bold;
    color: #3b82f6;
  }
  
  .status {
    font-size: 0.85rem;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    display: inline-block;
  }
  
  .status.open {
    background: rgba(63, 185, 80, 0.15);
    color: #3fb950;
    border: 1px solid #3fb950;
  }
  
  .status.closed {
    background: rgba(248, 81, 73, 0.15);
    color: #f85149;
    border: 1px solid #f85149;
  }
  
  .remove-btn {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    background: none;
    border: none;
    font-size: 1rem;
    cursor: pointer;
    opacity: 0.5;
    transition: opacity 0.3s;
    padding: 0.25rem;
  }
  
  .remove-btn:hover {
    opacity: 1;
  }
  
  @media (max-width: 600px) {
    .favorite-card {
      grid-template-columns: 1fr;
    }
    
    .price-info {
      text-align: left;
      flex-direction: row;
      justify-content: space-between;
      align-items: center;
    }
    
    .current-price {
      align-items: flex-start;
    }
  }
</style>
