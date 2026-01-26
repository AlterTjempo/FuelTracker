<script>
  import { onMount } from 'svelte'
  import API_BASE from '../lib/api.js'
  
  export let fuelType = 'e5'
  export let hours = 24
  export let leaderboardOnly = false
  
  let avgPrice = null
  let minPrice = null
  let maxPrice = null
  let timePatterns = null
  let topStations = null
  let lowestEver = null
  let loading = true
  
  async function fetchStats() {
    try {
      if (!leaderboardOnly) {
        // Fetch basic stats
        const response = await fetch(`${API_BASE}/prices/history/all?fuel_type=${fuelType}&hours=${hours}`)
        const data = await response.json()
        
        if (data.length > 0) {
          const prices = data.map(d => d.avg_price).filter(p => p !== null)
          avgPrice = prices.reduce((a, b) => a + b, 0) / prices.length
          minPrice = Math.min(...data.map(d => d.min_price).filter(p => p !== null))
          maxPrice = Math.max(...data.map(d => d.max_price).filter(p => p !== null))
        }
        
        // Fetch time patterns
        const patternsResponse = await fetch(`${API_BASE}/prices/analytics/time-patterns?fuel_type=${fuelType}&hours=${hours}`)
        timePatterns = await patternsResponse.json()
        
        // Fetch lowest ever
        const lowestResponse = await fetch(`${API_BASE}/prices/analytics/lowest-ever?fuel_type=${fuelType}`)
        lowestEver = await lowestResponse.json()
      }
      
      // Fetch top stations (always, for leaderboard)
      const stationsResponse = await fetch(`${API_BASE}/prices/analytics/top-stations?fuel_type=${fuelType}&hours=${hours}&limit=${leaderboardOnly ? 10 : 3}`)
      topStations = await stationsResponse.json()
      
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
  
  $: if (fuelType || hours || leaderboardOnly) {
    fetchStats()
  }
  
  function getVolatilityLabel(volatility) {
    if (volatility < 0.01) return 'Very Stable'
    if (volatility < 0.02) return 'Stable'
    if (volatility < 0.03) return 'Moderate'
    if (volatility < 0.05) return 'Volatile'
    return 'Very Volatile'
  }
  
  function getVolatilityColor(volatility) {
    if (volatility < 0.01) return '#10b981'
    if (volatility < 0.02) return '#22c55e'
    if (volatility < 0.03) return '#f59e0b'
    if (volatility < 0.05) return '#f97316'
    return '#ef4444'
  }
  
  function formatDate(timestamp) {
    const date = new Date(timestamp)
    // Use Intl.DateTimeFormat with Europe/Berlin timezone to handle DST automatically
    const formatter = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Europe/Berlin',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    })
    
    return formatter.format(date)
  }
</script>

<div class="statistics">
  {#if loading}
    <div class="loading">Loading...</div>
  {:else if !leaderboardOnly && avgPrice === null}
    <div class="no-data">No data available</div>
  {:else}
    {#if !leaderboardOnly}
      {#if lowestEver && lowestEver.price}
        <div class="record-card">
          <h3>🏆 All-Time Lowest Price</h3>
          <div class="record-content">
            <div class="record-price">€{lowestEver.price}</div>
            <div class="record-details">
              <div class="record-date">📅 {formatDate(lowestEver.timestamp)}</div>
              <div class="record-station">⛽ {lowestEver.station_name}</div>
              {#if lowestEver.city}
                <div class="record-location">📍 {lowestEver.city}</div>
              {/if}
            </div>
          </div>
        </div>
      {/if}
      
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
    
    {#if !leaderboardOnly && timePatterns}
      {#if timePatterns.insufficient_data}
        <div class="time-patterns">
          <h3>🕐 Best Times to Refuel</h3>
          <div class="no-data-message">
            <p>⏳ Not enough data yet</p>
            <p class="detail">Collected {timePatterns.days_collected} of {timePatterns.days_needed} days needed for accurate patterns</p>
            <p class="detail">Check back after more price data is collected!</p>
          </div>
        </div>
      {:else}
        <div class="time-patterns">
          <h3>🕐 Best Times to Refuel</h3>
          <div class="pattern-grid">
            <div class="pattern-card">
              <div class="pattern-icon">📅</div>
              <div class="pattern-label">Cheapest Day</div>
              <div class="pattern-value">{timePatterns.cheapest_day?.day || 'N/A'}</div>
              {#if timePatterns.cheapest_day?.avg_price}
                <div class="pattern-price">€{timePatterns.cheapest_day.avg_price.toFixed(3)}</div>
              {/if}
            </div>
            
            <div class="pattern-card">
              <div class="pattern-icon">⏰</div>
              <div class="pattern-label">Cheapest Time</div>
              <div class="pattern-value">
                {#if timePatterns.cheapest_hour?.hour !== null}
                  {String(timePatterns.cheapest_hour.hour).padStart(2, '0')}:00
                {:else}
                  N/A
                {/if}
              </div>
              {#if timePatterns.cheapest_hour?.avg_price}
                <div class="pattern-price">€{timePatterns.cheapest_hour.avg_price.toFixed(3)}</div>
              {/if}
            </div>
          </div>
        </div>
      {/if}
    {/if}
    
    {#if leaderboardOnly && topStations && topStations.length > 0}
      <div class="top-stations">
        <h3>🏆 Top 10 Stations</h3>
        <div class="stations-list">
          {#each topStations as station, index}
            <div class="station-card">
              <div class="station-rank">#{index + 1}</div>
              <div class="station-info">
                <div class="station-name">{station.name}</div>
                <div class="station-city">{station.city || station.brand}</div>
              </div>
              <div class="station-stats">
                <div class="station-stat">
                  <span class="label">Avg Price:</span>
                  <span class="value">€{station.avg_price}</span>
                </div>
                <div class="station-stat">
                  <span class="label">Cheapest:</span>
                  <span class="value">{station.cheapest_percentage}% of time</span>
                </div>
                <div class="station-stat">
                  <span class="label">Range:</span>
                  <span class="value">€{(station.max_price - station.min_price).toFixed(3)}</span>
                </div>
                <div class="station-stat volatility">
                  <span class="label">Stability:</span>
                  <span class="value" style="color: {getVolatilityColor(station.volatility)}">
                    {getVolatilityLabel(station.volatility)}
                  </span>
                </div>
              </div>
              <div class="volatility-bar">
                <div class="volatility-fill" style="width: {Math.min(station.volatility * 1000, 100)}%; background-color: {getVolatilityColor(station.volatility)}"></div>
              </div>
            </div>
          {/each}
        </div>
        
        {#if topStations.length > 1}
          <div class="insight">
            💡 <strong>{topStations[0].name}</strong> is cheapest {topStations[0].cheapest_percentage}% of the time
            {#if topStations[1].min_price < topStations[0].min_price}
              , but <strong>{topStations[1].name}</strong> dips lower (€{topStations[1].min_price} vs €{topStations[0].min_price})
            {/if}
          </div>
        {/if}
      </div>
    {/if}
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
    margin-bottom: 2rem;
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
  
  /* Time Patterns */
  .time-patterns {
    margin-bottom: 2rem;
    padding: 1.5rem;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
  }
  
  .time-patterns h3 {
    margin: 0 0 1rem 0;
    color: #c9d1d9;
  }
  
  .pattern-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
  }
  
  .pattern-card {
    padding: 1.5rem;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    text-align: center;
  }
  
  .pattern-icon {
    font-size: 2rem;
    margin-bottom: 0.5rem;
  }
  
  .pattern-label {
    color: #8b949e;
    font-size: 0.875rem;
    margin-bottom: 0.5rem;
  }
  
  .pattern-value {
    color: #58a6ff;
    font-size: 1.25rem;
    font-weight: bold;
    margin-bottom: 0.25rem;
  }
  
  .pattern-price {
    color: #6e7681;
    font-size: 0.875rem;
  }
  
  .no-data-message {
    text-align: center;
    padding: 2rem;
    color: #8b949e;
  }
  
  .no-data-message p {
    margin: 0.5rem 0;
  }
  
  .no-data-message .detail {
    font-size: 0.875rem;
    color: #6e7681;
  }
  
  /* Top Stations */
  .top-stations {
    padding: 1.5rem;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
  }
  
  .top-stations h3 {
    margin: 0 0 1rem 0;
    color: #c9d1d9;
  }
  
  .stations-list {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    margin-bottom: 1rem;
  }
  
  .station-card {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 1rem;
    padding: 1rem;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    transition: all 0.2s;
  }
  
  .station-card:hover {
    border-color: #58a6ff;
    transform: translateX(4px);
  }
  
  .station-rank {
    font-size: 1.5rem;
    font-weight: bold;
    color: #58a6ff;
    display: flex;
    align-items: center;
  }
  
  .station-info {
    grid-column: 2;
  }
  
  .station-name {
    font-weight: bold;
    color: #c9d1d9;
    margin-bottom: 0.25rem;
  }
  
  .station-city {
    color: #8b949e;
    font-size: 0.875rem;
  }
  
  .station-stats {
    grid-column: 1 / -1;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 0.75rem;
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid #30363d;
  }
  
  .station-stat {
    display: flex;
    justify-content: space-between;
    font-size: 0.875rem;
  }
  
  .station-stat .label {
    color: #8b949e;
  }
  
  .station-stat .value {
    color: #c9d1d9;
    font-weight: 600;
  }
  
  .volatility-bar {
    grid-column: 1 / -1;
    height: 4px;
    background: #21262d;
    border-radius: 2px;
    overflow: hidden;
    margin-top: 0.5rem;
  }
  
  .volatility-fill {
    height: 100%;
    transition: width 0.3s ease;
  }
  
  .insight {
    padding: 1rem;
    background: #161b22;
    border-left: 3px solid #58a6ff;
    border-radius: 4px;
    color: #c9d1d9;
    font-size: 0.9rem;
    line-height: 1.5;
  }
  
  .insight strong {
    color: #58a6ff;
  }
  
  /* Record Card */
  .record-card {
    background: linear-gradient(135deg, #1e3a8a 0%, #7c3aed 100%);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 2rem;
    color: white;
    box-shadow: 0 4px 6px rgba(0,0,0,0.2);
  }
  
  .record-card h3 {
    margin: 0 0 1rem 0;
    font-size: 1.25rem;
  }
  
  .record-content {
    display: flex;
    align-items: center;
    gap: 2rem;
  }
  
  .record-price {
    font-size: 3rem;
    font-weight: bold;
    color: #fbbf24;
  }
  
  .record-details {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .record-date, .record-station, .record-location {
    font-size: 0.95rem;
    opacity: 0.95;
  }
</style>

