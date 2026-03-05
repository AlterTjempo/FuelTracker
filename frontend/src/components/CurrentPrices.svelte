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
    -webkit-overflow-scrolling: touch;
  }
  
  .load-more {
    text-align: center;
    padding: 1rem;
    color: #8b949e;
    font-size: 0.85rem;
    font-style: italic;
  }
  
  .price-list {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }
  
  .price-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 0.5rem;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    transition: all 0.2s;
  }
  
  .price-item:hover {
    border-color: #3b82f6;
  }
  
  .price-item.best {
    border-color: #10b981;
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(16, 185, 129, 0.05) 100%);
  }
  
  .rank {
    font-weight: 700;
    color: #8b949e;
    min-width: 2rem;
    font-size: 0.9rem;
    text-align: center;
    flex-shrink: 0;
  }
  
  .best .rank {
    color: #10b981;
  }
  
  .station-info {
    flex: 1;
    min-width: 0;
  }
  
  .station-name {
    font-weight: 600;
    color: #e6edf3;
    margin-bottom: 0.15rem;
    font-size: 0.85rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  .station-details {
    display: flex;
    gap: 0.5rem;
    font-size: 0.75rem;
    color: #8b949e;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  .brand {
    font-weight: 500;
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
  
  .price {
    font-size: 1rem;
    font-weight: 700;
    color: #3b82f6;
    white-space: nowrap;
    flex-shrink: 0;
    text-align: right;
  }
  
  .best .price {
    color: #10b981;
  }
  
  .loading, .no-data {
    text-align: center;
    padding: 1.5rem;
    color: #8b949e;
  }
  
  .current-prices::-webkit-scrollbar {
    width: 6px;
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

  @media (min-width: 640px) {
    .price-list {
      gap: 0.5rem;
    }
    .price-item {
      gap: 0.75rem;
      padding: 0.75rem;
    }
    .rank {
      min-width: 2.5rem;
      font-size: 1rem;
    }
    .station-name {
      font-size: 0.95rem;
    }
    .station-details {
      font-size: 0.85rem;
    }
    .price {
      font-size: 1.2rem;
    }
    .status-closed {
      font-size: 0.7rem;
    }
  }

  @media (min-width: 1024px) {
    .price-item {
      gap: 1rem;
    }
    .price-item:hover {
      transform: translateX(2px);
    }
    .price {
      font-size: 1.3rem;
      min-width: 6rem;
    }
  }
</style>
