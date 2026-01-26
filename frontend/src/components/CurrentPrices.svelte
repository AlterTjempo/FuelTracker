<script>
  import { onMount } from 'svelte'
  import API_BASE from '../lib/api.js'
  
  export let fuelType = 'e5'
  
  let prices = []
  let loading = true
  let displayCount = 20
  let scrollContainer
  
  async function fetchPrices() {
    try {
      const response = await fetch(`${API_BASE}/prices/current?limit=500`)
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
  
  function handleScroll() {
    if (!scrollContainer) return
    
    const { scrollTop, scrollHeight, clientHeight } = scrollContainer
    const scrolledToBottom = scrollTop + clientHeight >= scrollHeight - 100
    
    if (scrolledToBottom && displayCount < prices.length) {
      displayCount += 20
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
    displayCount = 20
  }
  
  function getPrice(station) {
    return station[fuelType]
  }
</script>

<div class="current-prices" bind:this={scrollContainer} on:scroll={handleScroll}>
  {#if loading}
    <div class="loading">Loading stations...</div>
  {:else if prices.length === 0}
    <div class="no-data">No station data available yet.</div>
  {:else}
    <div class="price-list">
      {#each prices.slice(0, displayCount) as station, index}
        {#if getPrice(station)}
          <div class="price-item" class:best={index === 0}>
            <div class="rank">#{index + 1}</div>
            <div class="station-info">
              <div class="station-name">
                {station.station_name}
                {#if !station.is_open}
                  <span class="status-closed">CLOSED</span>
                {/if}
              </div>
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
      {#if displayCount < prices.length}
        <div class="load-more">Scroll for more... ({displayCount}/{prices.length})</div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .current-prices {
    max-height: 600px;
    overflow-y: auto;
  }
  
  .load-more {
    text-align: center;
    padding: 1rem;
    color: #8b949e;
    font-size: 0.9rem;
    font-style: italic;
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
