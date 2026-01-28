<script>
  import { onMount } from 'svelte'
  import API_BASE from '../lib/api.js'
  
  export let fuelType = 'e5'
  
  let lowestPrices = []
  let loading = true
  
  function getGoogleMapsUrl(station) {
    if (!station || !station.station_name) return '#'
    const query = encodeURIComponent(station.station_name + ' ' + (station.city || ''))
    return `https://www.google.com/maps/search/?api=1&query=${query}`
  }
  
  function formatTimeSince(timestamp) {
    const now = new Date()
    const then = new Date(timestamp)
    const diffMs = now - then
    const diffMins = Math.floor(diffMs / 60000)
    
    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    
    const diffHours = Math.floor(diffMins / 60)
    if (diffHours < 24) return `${diffHours}h ago`
    
    const diffDays = Math.floor(diffHours / 24)
    return `${diffDays}d ago`
  }
  
  async function fetchCurrentLowest() {
    try {
      const response = await fetch(`${API_BASE}/prices/current-lowest?fuel_type=${fuelType}&limit=5`)
      lowestPrices = await response.json()
      loading = false
    } catch (error) {
      console.error('Error fetching current lowest prices:', error)
      loading = false
    }
  }
  
  onMount(() => {
    fetchCurrentLowest()
    const interval = setInterval(fetchCurrentLowest, 60000)
    return () => clearInterval(interval)
  })
  
  $: if (fuelType) {
    fetchCurrentLowest()
  }
</script>

<div class="current-lowest">
  {#if loading}
    <div class="loading">Loading...</div>
  {:else if lowestPrices.length === 0}
    <div class="no-data">No data available</div>
  {:else}
    {#each lowestPrices as item, index}
      <div class="price-item" class:best={index === 0}>
        <div class="rank">
          {#if index === 0}🥇
          {:else if index === 1}🥈
          {:else if index === 2}🥉
          {:else}#{index + 1}
          {/if}
        </div>
        <div class="details">
          <div class="station-info">
            <div class="name">
              {item.station_name}
              {#if !item.is_open}
                <span class="status-closed">CLOSED</span>
              {/if}
            </div>
            {#if item.city}
              <div class="location">📍 {item.city}</div>
            {/if}
            <div class="time-updated">
              Updated {formatTimeSince(item.timestamp)}
            </div>
          </div>
        </div>
        <div class="price-section">
          <div class="price">€{item.price.toFixed(3)}</div>
          <a 
            href={getGoogleMapsUrl(item)} 
            target="_blank" 
            rel="noopener noreferrer"
            class="route-btn"
            title="Get directions"
          >
            🧭 Route
          </a>
        </div>
      </div>
    {/each}
  {/if}
</div>

<style>
  .current-lowest {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .price-item {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    transition: all 0.2s;
  }
  
  .price-item:hover {
    border-color: #3b82f6;
    transform: translateX(4px);
  }
  
  .price-item.best {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.15) 0%, rgba(59, 130, 246, 0.05) 100%);
    border-color: #3b82f6;
  }
  
  .rank {
    font-size: 1.5rem;
    min-width: 2.5rem;
    text-align: center;
  }
  
  .details {
    flex: 1;
  }
  
  .station-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .name {
    font-weight: 600;
    color: #e6edf3;
    font-size: 1rem;
  }
  
  .status-closed {
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 700;
    color: #fff;
    background: #ef4444;
    padding: 0.2rem 0.5rem;
    border-radius: 3px;
    margin-left: 0.5rem;
  }
  
  .location {
    font-size: 0.85rem;
    color: #8b949e;
  }
  
  .time-updated {
    font-size: 0.8rem;
    color: #6e7681;
    font-style: italic;
  }
  
  .price-section {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.5rem;
  }
  
  .price {
    font-size: 1.6rem;
    font-weight: 700;
    color: #3b82f6;
  }
  
  .route-btn {
    padding: 0.5rem 1rem;
    background: #3b82f6;
    color: white;
    text-decoration: none;
    border-radius: 6px;
    font-size: 0.9rem;
    font-weight: 600;
    transition: all 0.2s;
    white-space: nowrap;
  }
  
  .route-btn:hover {
    background: #2563eb;
    transform: scale(1.05);
  }
  
  .loading, .no-data {
    text-align: center;
    padding: 2rem;
    color: #8b949e;
  }
</style>
