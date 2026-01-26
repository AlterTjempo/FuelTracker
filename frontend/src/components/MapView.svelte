<script>
  import { onMount } from 'svelte'
  
  export let fuelType = 'e5'
  
  let stations = []
  let loading = true
  let mapInitialized = false
  
  async function fetchStations() {
    try {
      const response = await fetch('http://localhost:8001/api/prices/current?limit=100')
      const data = await response.json()
      stations = data.filter(s => s[fuelType] !== null && s.latitude && s.longitude)
      loading = false
      initMap()
    } catch (error) {
      console.error('Error fetching stations:', error)
      loading = false
    }
  }
  
  function initMap() {
    if (mapInitialized || stations.length === 0) return
    
    // Simple text-based map since we don't have a maps library
    mapInitialized = true
  }
  
  onMount(() => {
    fetchStations()
    const interval = setInterval(fetchStations, 60000)
    return () => clearInterval(interval)
  })
  
  $: if (fuelType) {
    stations = [...stations].filter(s => s[fuelType] !== null)
  }
  
  function getGoogleMapsUrl(station) {
    return `https://www.google.com/maps/search/?api=1&query=${station.latitude},${station.longitude}`
  }
  
  function getPriceColor(price) {
    if (!price) return '#8b949e'
    const minPrice = Math.min(...stations.map(s => s[fuelType]).filter(p => p))
    const maxPrice = Math.max(...stations.map(s => s[fuelType]).filter(p => p))
    const ratio = (price - minPrice) / (maxPrice - minPrice)
    
    if (ratio < 0.33) return '#10b981' // Green - cheap
    if (ratio < 0.66) return '#f59e0b' // Orange - medium
    return '#ef4444' // Red - expensive
  }
</script>

<div class="map-container">
  {#if loading}
    <div class="loading">Loading map data...</div>
  {:else if stations.length === 0}
    <div class="no-data">No station data available</div>
  {:else}
    <div class="map-info">
      <div class="legend">
        <div class="legend-item">
          <span class="dot" style="background: #10b981;"></span> Cheap
        </div>
        <div class="legend-item">
          <span class="dot" style="background: #f59e0b;"></span> Medium
        </div>
        <div class="legend-item">
          <span class="dot" style="background: #ef4444;"></span> Expensive
        </div>
      </div>
      
      <div class="station-grid">
        {#each stations.slice(0, 20) as station}
          <a 
            href={getGoogleMapsUrl(station)} 
            target="_blank" 
            rel="noopener noreferrer"
            class="station-marker"
          >
            <div class="marker-dot" style="background: {getPriceColor(station[fuelType])};"></div>
            <div class="marker-info">
              <div class="marker-name">{station.station_name}</div>
              <div class="marker-price">€{station[fuelType].toFixed(3)}</div>
              {#if station.city}
                <div class="marker-city">{station.city}</div>
              {/if}
            </div>
          </a>
        {/each}
      </div>
      
      <div class="map-note">
        💡 Click any station to view on Google Maps
      </div>
    </div>
  {/if}
</div>

<style>
  .map-container {
    min-height: 400px;
  }
  
  .map-info {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  
  .legend {
    display: flex;
    gap: 1.5rem;
    padding: 1rem;
    background: #0d1117;
    border-radius: 6px;
    justify-content: center;
  }
  
  .legend-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
    color: #8b949e;
  }
  
  .dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    display: inline-block;
  }
  
  .station-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 1rem;
    max-height: 500px;
    overflow-y: auto;
    padding: 0.5rem;
  }
  
  .station-marker {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    text-decoration: none;
    transition: all 0.2s;
  }
  
  .station-marker:hover {
    border-color: #3b82f6;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.2);
  }
  
  .marker-dot {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    flex-shrink: 0;
    box-shadow: 0 0 10px currentColor;
  }
  
  .marker-info {
    flex: 1;
  }
  
  .marker-name {
    font-weight: 600;
    color: #e6edf3;
    margin-bottom: 0.25rem;
    font-size: 0.95rem;
  }
  
  .marker-price {
    font-size: 1.2rem;
    font-weight: 700;
    color: #3b82f6;
    margin-bottom: 0.25rem;
  }
  
  .marker-city {
    font-size: 0.8rem;
    color: #8b949e;
  }
  
  .map-note {
    text-align: center;
    color: #8b949e;
    font-size: 0.9rem;
    padding: 0.5rem;
  }
  
  .station-grid::-webkit-scrollbar {
    width: 8px;
  }
  
  .station-grid::-webkit-scrollbar-track {
    background: #0d1117;
  }
  
  .station-grid::-webkit-scrollbar-thumb {
    background: #30363d;
    border-radius: 4px;
  }
  
  .station-grid::-webkit-scrollbar-thumb:hover {
    background: #3b82f6;
  }
  
  .loading, .no-data {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 400px;
    color: #8b949e;
    font-size: 1.1rem;
  }
</style>
