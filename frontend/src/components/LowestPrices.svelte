<script>
  import { onMount } from 'svelte'
  import API_BASE from '../lib/api.js'
  
  export let fuelType = 'e5'
  export let hours = 24
  
  let lowestPrices = []
  let loading = true
  let stations = []
  
  function getGoogleMapsUrl(station) {
    if (!station || !station.station_name) return '#'
    const query = encodeURIComponent(station.station_name + ' ' + (station.city || ''))
    return `https://www.google.com/maps/search/?api=1&query=${query}`
  }
  
  async function fetchLowest() {
    try {
      const response = await fetch(`${API_BASE}/prices/lowest?fuel_type=${fuelType}&hours=${hours}&limit=5`)
      lowestPrices = await response.json()
      
      // Fetch full station details for the cheapest one
      if (lowestPrices.length > 0) {
        const stationResponse = await fetch(`${API_BASE}/stations/${lowestPrices[0].station_id}`)
        const stationData = await stationResponse.json()
        stations = [stationData]
      }
      
      loading = false
    } catch (error) {
      console.error('Error fetching lowest prices:', error)
      loading = false
    }
  }
  
  onMount(() => {
    fetchLowest()
    const interval = setInterval(fetchLowest, 60000)
    return () => clearInterval(interval)
  })
  
  $: if (fuelType || hours) {
    fetchLowest()
  }
</script>

<div class="lowest-prices">
  {#if loading}
    <div class="loading">Loading...</div>
  {:else if lowestPrices.length === 0}
    <div class="no-data">No data available</div>
  {:else}
    {#each lowestPrices as item, index}
      <div class="lowest-item" class:winner={index === 0}>
        <div class="medal">
          {#if index === 0}🥇
          {:else if index === 1}🥈
          {:else if index === 2}🥉
          {:else}#{index + 1}
          {/if}
        </div>
        <div class="info">
          <div class="name">
            {item.station_name}
            {#if !item.is_open}
              <span class="status-closed">CLOSED</span>
            {/if}
          </div>
          {#if item.city}
            <div class="city">{item.city}</div>
          {/if}
        </div>
        <div class="price">€{item.price.toFixed(3)}</div>
      </div>
    {/each}
  {/if}
</div>

<style>
  .lowest-prices {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .lowest-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 0.5rem;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    transition: all 0.2s;
  }
  
  .lowest-item:hover {
    border-color: #10b981;
  }
  
  .lowest-item.winner {
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(16, 185, 129, 0.05) 100%);
    border-color: #10b981;
  }
  
  .medal {
    font-size: 1.25rem;
    min-width: 2rem;
    text-align: center;
    flex-shrink: 0;
  }
  
  .info {
    flex: 1;
    min-width: 0;
  }
  
  .name {
    font-weight: 600;
    color: #e6edf3;
    margin-bottom: 0.15rem;
    font-size: 0.85rem;
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
  
  .city {
    font-size: 0.75rem;
    color: #8b949e;
  }
  
  .price {
    font-size: 1.1rem;
    font-weight: 700;
    color: #10b981;
    white-space: nowrap;
    flex-shrink: 0;
  }
  
  .loading, .no-data {
    text-align: center;
    padding: 1.5rem;
    color: #8b949e;
  }

  @media (min-width: 640px) {
    .lowest-prices {
      gap: 0.75rem;
    }
    .lowest-item {
      gap: 0.75rem;
      padding: 0.875rem 0.75rem;
    }
    .medal {
      font-size: 1.5rem;
      min-width: 2.5rem;
    }
    .name {
      font-size: 0.95rem;
    }
    .city {
      font-size: 0.85rem;
    }
    .price {
      font-size: 1.3rem;
    }
    .status-closed {
      font-size: 0.7rem;
    }
  }

  @media (min-width: 1024px) {
    .lowest-item {
      gap: 1rem;
      padding: 1rem;
    }
    .lowest-item:hover {
      transform: scale(1.02);
    }
    .price {
      font-size: 1.4rem;
    }
    .route-btn {
      padding: 0.5rem 1rem;
      font-size: 0.9rem;
    }
    .route-btn:hover {
      transform: scale(1.05);
    }
  }
</style>
