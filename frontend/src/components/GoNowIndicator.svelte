<script>
  import API_BASE, { safeFetch } from '../lib/api.js'
  
  export let fuelType = 'e5'
  
  let indicator = null
  let loading = true
  
  async function fetchIndicator() {
    try {
      indicator = await safeFetch(`${API_BASE}/prices/analytics/go-now?fuel_type=${encodeURIComponent(fuelType)}`)
      loading = false
    } catch (error) {
      console.error('Error fetching indicator:', error)
      loading = false
    }
  }
  
  $: fuelType && fetchIndicator()
  
  function getColor(recommendation) {
    const colors = {
      'excellent': '#10b981',
      'good': '#22c55e',
      'neutral': '#6b7280',
      'wait': '#f59e0b',
      'avoid': '#ef4444',
      'insufficient_data': '#9ca3af'
    }
    return colors[recommendation] || '#9ca3af'
  }
  
  function getIcon(recommendation) {
    const icons = {
      'excellent': '🎯',
      'good': '✅',
      'neutral': '➖',
      'wait': '⏰',
      'avoid': '❌',
      'insufficient_data': '⏳'
    }
    return icons[recommendation] || '⏳'
  }
  
  function getMessage(recommendation) {
    const messages = {
      'excellent': 'GO! Excellent price!',
      'good': 'Good time to refuel',
      'neutral': 'Average price',
      'wait': 'Consider waiting',
      'avoid': 'Wait for better price',
      'insufficient_data': 'Need more data'
    }
    return messages[recommendation] || 'No data'
  }

  function getTrendIcon(direction) {
    const icons = { 'falling': '📉', 'rising': '📈', 'stable': '➡️' }
    return icons[direction] || '➡️'
  }

  function getTrendLabel(direction, cents) {
    if (direction === 'falling') return `Falling ${Math.abs(cents)}¢/hr`
    if (direction === 'rising') return `Rising ${Math.abs(cents)}¢/hr`
    return 'Stable'
  }

  function getTrendColor(direction) {
    if (direction === 'falling') return '#10b981'
    if (direction === 'rising') return '#ef4444'
    return '#6b7280'
  }
</script>

<div class="go-now-container">
  {#if loading}
    <div class="loading">Loading...</div>
  {:else if indicator && indicator.recommendation !== 'insufficient_data'}
    <div class="card" style="border-color: {getColor(indicator.recommendation)}">
      <div class="header">
        <span class="icon">{getIcon(indicator.recommendation)}</span>
        <h3>Should I refuel now?</h3>
      </div>
      
      <div class="recommendation" style="color: {getColor(indicator.recommendation)}">
        {getMessage(indicator.recommendation)}
      </div>

      <div class="percentile-bar-section">
        <div class="percentile-label">
          Current best price: <strong>€{indicator.current_price}</strong>
        </div>
        <div class="percentile-track">
          <div class="percentile-fill" style="width: {indicator.percentile}%; background: {getColor(indicator.recommendation)}"></div>
          <div class="percentile-marker" style="left: {indicator.percentile}%">
            <div class="marker-dot" style="background: {getColor(indicator.recommendation)}"></div>
          </div>
          <div class="percentile-labels">
            <span class="cheapest">Cheapest</span>
            <span class="priciest">Priciest</span>
          </div>
        </div>
        <div class="percentile-detail">
          Cheaper than <strong>{Math.round(100 - indicator.percentile)}%</strong> of prices at this time of day
        </div>
      </div>

      {#if indicator.trend_direction}
        <div class="trend-section">
          <div class="trend-badge" style="background: {getTrendColor(indicator.trend_direction)}20; border-color: {getTrendColor(indicator.trend_direction)}40">
            <span class="trend-icon">{getTrendIcon(indicator.trend_direction)}</span>
            <span class="trend-text" style="color: {getTrendColor(indicator.trend_direction)}">
              {getTrendLabel(indicator.trend_direction, indicator.trend)}
            </span>
          </div>
        </div>
      {/if}
      
      <div class="week-range">
        <div class="range-item low">
          <div class="range-label">Week Low</div>
          <div class="range-value">€{indicator.week_low}</div>
        </div>
        <div class="range-item mid">
          <div class="range-label">Week Median</div>
          <div class="range-value">€{indicator.week_median}</div>
        </div>
        <div class="range-item high">
          <div class="range-label">Week High</div>
          <div class="range-value">€{indicator.week_high}</div>
        </div>
      </div>
    </div>
  {:else}
    <div class="card insufficient">
      <div class="header">
        <span class="icon">⏳</span>
        <h3>Should I refuel now?</h3>
      </div>
      <p class="no-data">Not enough data yet. Check back after more price data is collected!</p>
    </div>
  {/if}
</div>

<style>
  .go-now-container {
    margin-bottom: 1rem;
  }
  
  .card {
    background: #0d1117;
    border: 2px solid #30363d;
    border-radius: 8px;
    padding: 1rem;
    transition: all 0.3s ease;
  }
  
  .card:not(.insufficient):hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  }
  
  .header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }
  
  .icon {
    font-size: 1.25rem;
  }
  
  h3 {
    margin: 0;
    color: #c9d1d9;
    font-size: 1rem;
    font-weight: 600;
  }
  
  .recommendation {
    font-size: 1.1rem;
    font-weight: bold;
    text-align: center;
    margin-bottom: 1rem;
    padding: 0.5rem;
    background: rgba(255, 255, 255, 0.03);
    border-radius: 6px;
  }

  /* Percentile bar */
  .percentile-bar-section {
    margin-bottom: 1rem;
  }

  .percentile-label {
    font-size: 0.85rem;
    color: #c9d1d9;
    margin-bottom: 0.5rem;
    text-align: center;
  }

  .percentile-label strong {
    color: #e6edf3;
  }

  .percentile-track {
    position: relative;
    height: 10px;
    background: #21262d;
    border-radius: 5px;
    overflow: visible;
    margin-bottom: 0.25rem;
  }

  .percentile-fill {
    height: 100%;
    border-radius: 5px;
    transition: width 0.6s ease;
    opacity: 0.35;
  }

  .percentile-marker {
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    z-index: 1;
  }

  .marker-dot {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    border: 2px solid #0d1117;
    box-shadow: 0 0 6px rgba(0,0,0,0.5);
  }

  .percentile-labels {
    display: flex;
    justify-content: space-between;
    padding-top: 0.375rem;
  }

  .percentile-labels span {
    font-size: 0.65rem;
    color: #6e7681;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }

  .percentile-detail {
    text-align: center;
    font-size: 0.8rem;
    color: #8b949e;
    margin-top: 0.375rem;
  }

  .percentile-detail strong {
    color: #e6edf3;
  }

  /* Trend badge */
  .trend-section {
    display: flex;
    justify-content: center;
    margin-bottom: 1rem;
  }

  .trend-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.375rem 0.75rem;
    border: 1px solid;
    border-radius: 999px;
    font-size: 0.8rem;
  }

  .trend-icon {
    font-size: 0.9rem;
  }

  .trend-text {
    font-weight: 600;
  }

  /* Week range */
  .week-range {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    padding-top: 0.75rem;
    border-top: 1px solid #30363d;
    margin-top: 0.25rem;
  }

  .range-item {
    text-align: center;
    flex: 1;
  }

  .range-label {
    font-size: 0.6rem;
    color: #6e7681;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    margin-bottom: 0.2rem;
  }

  .range-value {
    font-size: 0.9rem;
    font-weight: 700;
    color: #c9d1d9;
  }

  .range-item.low .range-value {
    color: #10b981;
  }

  .range-item.high .range-value {
    color: #ef4444;
  }
  
  .loading, .no-data {
    text-align: center;
    padding: 1.5rem;
    color: #8b949e;
  }
  
  .insufficient {
    border-color: #30363d;
  }

  @media (min-width: 640px) {
    .go-now-container {
      margin-bottom: 1.5rem;
    }
    .card {
      padding: 1.25rem;
    }
    .header {
      gap: 0.75rem;
      margin-bottom: 1rem;
    }
    .icon {
      font-size: 1.5rem;
    }
    h3 {
      font-size: 1.125rem;
    }
    .recommendation {
      font-size: 1.35rem;
      margin-bottom: 1.25rem;
      padding: 0.75rem;
    }
    .percentile-label {
      font-size: 0.95rem;
    }
    .percentile-track {
      height: 12px;
    }
    .marker-dot {
      width: 18px;
      height: 18px;
    }
    .percentile-labels span {
      font-size: 0.7rem;
    }
    .percentile-detail {
      font-size: 0.85rem;
    }
    .trend-badge {
      font-size: 0.85rem;
      padding: 0.4rem 0.875rem;
    }
    .range-label {
      font-size: 0.65rem;
    }
    .range-value {
      font-size: 1rem;
    }
  }

  @media (min-width: 1024px) {
    .card {
      padding: 1.5rem;
    }
    .card:not(.insufficient):hover {
      transform: translateY(-2px);
    }
    .recommendation {
      font-size: 1.5rem;
      margin-bottom: 1.5rem;
    }
    .percentile-bar-section {
      margin-bottom: 1.25rem;
    }
    .percentile-label {
      font-size: 1rem;
    }
    .trend-badge {
      font-size: 0.9rem;
      padding: 0.5rem 1rem;
    }
    .range-label {
      font-size: 0.7rem;
    }
    .range-value {
      font-size: 1.1rem;
    }
  }
</style>
