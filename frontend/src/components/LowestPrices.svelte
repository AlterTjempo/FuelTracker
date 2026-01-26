<script>
  import { onMount } from 'svelte'
  
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
      const response = await fetch(`http://localhost:8001/api/prices/lowest?fuel_type=${fuelType}&hours=${hours}&limit=5`)
      lowestPrices = await response.json()
      
      // Fetch full station details for the cheapest one
      if (lowestPrices.length > 0) {
        const stationResponse = await fetch(`http://localhost:8001/api/stations/${lowestPrices[0].station_id}`)
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
        {#if index === 0}
          <a 
            href={getGoogleMapsUrl(item)} 
            target="_blank" 
            rel="noopener noreferrer"
            class="route-btn"
            title="Get directions"
          >
            🧭 Route
          </a>
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
    gap: 0.75rem;
  }
  
  .lowest-item {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    transition: all 0.2s;
  }
  
  .lowest-item:hover {
    border-color: #10b981;
    transform: scale(1.02);
  }
  
  .lowest-item.winner {
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(16, 185, 129, 0.05) 100%);
    border-color: #10b981;
  }
  
  .medal {
    font-size: 1.5rem;
    min-width: 2.5rem;
    text-align: center;
  }
  
  .info {
    flex: 1;
  }
  
  .name {
    font-weight: 600;
    color: #e6edf3;
    margin-bottom: 0.25rem;
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
  
  .city {
    font-size: 0.85rem;
    color: #8b949e;
  }
  
  .price {
    font-size: 1.4rem;
    font-weight: 700;
    color: #10b981;
  }
  
  .loading, .no-data {
    text-align: center;
    padding: 2rem;
    color: #8b949e;
  }
</style>
