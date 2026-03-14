<script>
  import { onMount } from 'svelte'
  import API_BASE, { safeFetch } from '../lib/api.js'
  
  export let fuelType = 'e5'
  
  let lowestPrices = []
  let loading = true
  let error = null
  
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
      error = null
      const data = await safeFetch(`${API_BASE}/prices/current-lowest?fuel_type=${encodeURIComponent(fuelType)}&limit=5`)
      if (!Array.isArray(data)) throw new Error('Unexpected response format')
      lowestPrices = data
      loading = false
    } catch (err) {
      console.error('Error fetching current lowest prices:', err)
      error = err.message
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
    gap: 0.5rem;
  }
  
  .price-item {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    padding: 0.75rem 0.5rem;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    transition: all 0.2s;
  }
  
  .price-item:hover {
    border-color: #3b82f6;
  }
  
  .price-item.best {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.15) 0%, rgba(59, 130, 246, 0.05) 100%);
    border-color: #3b82f6;
  }
  
  .rank {
    font-size: 1.25rem;
    min-width: 2rem;
    text-align: center;
    flex-shrink: 0;
    padding-top: 0.125rem;
  }
  
  .details {
    flex: 1;
    min-width: 0;
  }
  
  .station-info {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }
  
  .name {
    font-weight: 600;
    color: #e6edf3;
    font-size: 0.875rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  .status-closed {
    display: inline-block;
    font-size: 0.6rem;
    font-weight: 700;
    color: #fff;
    background: #ef4444;
    padding: 0.1rem 0.35rem;
    border-radius: 3px;
    margin-left: 0.35rem;
    vertical-align: middle;
  }
  
  .location {
    font-size: 0.75rem;
    color: #8b949e;
  }
  
  .time-updated {
    font-size: 0.7rem;
    color: #6e7681;
    font-style: italic;
  }
  
  .price-section {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.375rem;
    flex-shrink: 0;
  }
  
  .price {
    font-size: 1.2rem;
    font-weight: 700;
    color: #3b82f6;
    white-space: nowrap;
  }
  
  .route-btn {
    padding: 0.4rem 0.75rem;
    background: #3b82f6;
    color: white;
    text-decoration: none;
    border-radius: 6px;
    font-size: 0.8rem;
    font-weight: 600;
    transition: all 0.2s;
    white-space: nowrap;
    touch-action: manipulation;
  }
  
  .route-btn:hover {
    background: #2563eb;
  }
  
  .loading, .no-data {
    text-align: center;
    padding: 1.5rem;
    color: #8b949e;
  }

  @media (min-width: 640px) {
    .current-lowest {
      gap: 0.75rem;
    }
    .price-item {
      align-items: center;
      gap: 0.75rem;
      padding: 0.875rem 0.75rem;
    }
    .rank {
      font-size: 1.5rem;
      min-width: 2.5rem;
    }
    .name {
      font-size: 1rem;
    }
    .location {
      font-size: 0.85rem;
    }
    .time-updated {
      font-size: 0.8rem;
    }
    .price {
      font-size: 1.4rem;
    }
    .route-btn {
      padding: 0.5rem 1rem;
      font-size: 0.9rem;
    }
  }

  @media (min-width: 1024px) {
    .price-item {
      gap: 1rem;
      padding: 1rem;
    }
    .price-item:hover {
      transform: translateX(4px);
    }
    .price {
      font-size: 1.6rem;
    }
    .route-btn:hover {
      transform: scale(1.05);
    }
  }
</style>
