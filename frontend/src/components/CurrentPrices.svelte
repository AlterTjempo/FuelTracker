<script>
  import { onMount } from 'svelte'
  
  export let fuelType = 'e5'
  
  let prices = []
  let loading = true
  
  async function fetchPrices() {
    try {
      const response = await fetch('http://localhost:8001/api/prices/current?limit=100')
      const data = await response.json()
      prices = data.sort((a, b) => {
        const priceA = a[fuelType] || Infinity
        const priceB = b[fuelType] || Infinity
        return priceA - priceB
      })
      loading = false
    } catch (error) {
      console.error('Error fetching prices:', error)
      loading = false
    }
  }
  
  onMount(() => {
    fetchPrices()
    const interval = setInterval(fetchPrices, 60000)
    return () => clearInterval(interval)
  })
  
  $: if (fuelType) {
    prices = [...prices].sort((a, b) => {
      const priceA = a[fuelType] || Infinity
      const priceB = b[fuelType] || Infinity
      return priceA - priceB
    })
  }
  
  function getPrice(station) {
    return station[fuelType]
  }
</script>

<div class="current-prices">
  {#if loading}
    <div class="loading">Loading stations...</div>
  {:else if prices.length === 0}
    <div class="no-data">No station data available yet.</div>
  {:else}
    <div class="price-list">
      {#each prices.slice(0, 20) as station, index}
        {#if getPrice(station)}
          <div class="price-item" class:best={index === 0}>
            <div class="rank">#{index + 1}</div>
            <div class="station-info">
              <div class="station-name">{station.station_name}</div>
              <div class="station-details">
                {#if station.brand}
                  <span class="brand">{station.brand}</span>
                {/if}
                {#if station.city}
                  <span class="city">{station.city}</span>
                {/if}
              </div>
            </div>
            <div class="price">€{getPrice(station).toFixed(3)}</div>
          </div>
        {/if}
      {/each}
    </div>
  {/if}
</div>

<style>
  .current-prices {
    max-height: 600px;
    overflow-y: auto;
  }
  
  .price-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .price-item {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.75rem;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    transition: all 0.2s;
  }
  
  .price-item:hover {
    border-color: #3b82f6;
    transform: translateX(2px);
  }
  
  .price-item.best {
    border-color: #10b981;
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(16, 185, 129, 0.05) 100%);
  }
  
  .rank {
    font-weight: 700;
    color: #8b949e;
    min-width: 2.5rem;
    font-size: 1.1rem;
  }
  
  .best .rank {
    color: #10b981;
  }
  
  .station-info {
    flex: 1;
  }
  
  .station-name {
    font-weight: 600;
    color: #e6edf3;
    margin-bottom: 0.25rem;
  }
  
  .station-details {
    display: flex;
    gap: 0.75rem;
    font-size: 0.85rem;
    color: #8b949e;
  }
  
  .brand {
    font-weight: 500;
  }
  
  .price {
    font-size: 1.3rem;
    font-weight: 700;
    color: #3b82f6;
    min-width: 6rem;
    text-align: right;
  }
  
  .best .price {
    color: #10b981;
  }
  
  .loading, .no-data {
    text-align: center;
    padding: 2rem;
    color: #8b949e;
  }
  
  .current-prices::-webkit-scrollbar {
    width: 8px;
  }
  
  .current-prices::-webkit-scrollbar-track {
    background: #0d1117;
  }
  
  .current-prices::-webkit-scrollbar-thumb {
    background: #30363d;
    border-radius: 4px;
  }
  
  .current-prices::-webkit-scrollbar-thumb:hover {
    background: #3b82f6;
  }
</style>
