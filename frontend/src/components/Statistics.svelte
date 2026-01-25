<script>
  import { onMount } from 'svelte'
  
  export let fuelType = 'e5'
  export let hours = 24
  
  let avgPrice = null
  let minPrice = null
  let maxPrice = null
  let loading = true
  
  async function fetchStats() {
    try {
      const response = await fetch(`http://localhost:8000/api/prices/history/all?fuel_type=${fuelType}&hours=${hours}`)
      const data = await response.json()
      
      if (data.length > 0) {
        const prices = data.map(d => d.avg_price).filter(p => p !== null)
        avgPrice = prices.reduce((a, b) => a + b, 0) / prices.length
        minPrice = Math.min(...data.map(d => d.min_price).filter(p => p !== null))
        maxPrice = Math.max(...data.map(d => d.max_price).filter(p => p !== null))
      }
      
      loading = false
    } catch (error) {
      console.error('Error fetching stats:', error)
      loading = false
    }
  }
  
  onMount(() => {
    fetchStats()
    const interval = setInterval(fetchStats, 60000)
    return () => clearInterval(interval)
  })
  
  $: if (fuelType || hours) {
    fetchStats()
  }
  
  function getPriceDiff(current, reference) {
    if (!current || !reference) return null
    return ((current - reference) / reference * 100).toFixed(2)
  }
</script>

<div class="statistics">
  {#if loading}
    <div class="loading">Loading...</div>
  {:else if avgPrice === null}
    <div class="no-data">No data available</div>
  {:else}
    <div class="stat-grid">
      <div class="stat-item lowest">
        <div class="stat-label">Lowest Price</div>
        <div class="stat-value">€{minPrice.toFixed(3)}</div>
        <div class="stat-subtitle">in last {hours}h</div>
      </div>
      
      <div class="stat-item average">
        <div class="stat-label">Average Price</div>
        <div class="stat-value">€{avgPrice.toFixed(3)}</div>
        <div class="stat-subtitle">mean price</div>
      </div>
      
      <div class="stat-item highest">
        <div class="stat-label">Highest Price</div>
        <div class="stat-value">€{maxPrice.toFixed(3)}</div>
        <div class="stat-subtitle">in last {hours}h</div>
      </div>
      
      <div class="stat-item range">
        <div class="stat-label">Price Range</div>
        <div class="stat-value">€{(maxPrice - minPrice).toFixed(3)}</div>
        <div class="stat-subtitle">{((maxPrice - minPrice) / minPrice * 100).toFixed(1)}% spread</div>
      </div>
    </div>
  {/if}
</div>

<style>
  .statistics {
    min-height: 200px;
  }
  
  .stat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 1rem;
  }
  
  .stat-item {
    padding: 1rem;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    text-align: center;
    transition: all 0.2s;
  }
  
  .stat-item:hover {
    transform: translateY(-2px);
  }
  
  .stat-item.lowest {
    border-color: #10b981;
  }
  
  .stat-item.highest {
    border-color: #ef4444;
  }
  
  .stat-item.average {
    border-color: #3b82f6;
  }
  
  .stat-item.range {
    border-color: #8b5cf6;
  }
  
  .stat-label {
    font-size: 0.85rem;
    color: #8b949e;
    margin-bottom: 0.5rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  
  .stat-value {
    font-size: 1.5rem;
    font-weight: 700;
    margin-bottom: 0.25rem;
  }
  
  .lowest .stat-value {
    color: #10b981;
  }
  
  .highest .stat-value {
    color: #ef4444;
  }
  
  .average .stat-value {
    color: #3b82f6;
  }
  
  .range .stat-value {
    color: #8b5cf6;
  }
  
  .stat-subtitle {
    font-size: 0.75rem;
    color: #6e7681;
  }
  
  .loading, .no-data {
    text-align: center;
    padding: 2rem;
    color: #8b949e;
  }
</style>
