<script>
  import API_BASE from '../lib/api.js'
  
  export let fuelType = 'e5'
  
  let indicator = null
  let loading = true
  
  async function fetchIndicator() {
    try {
      const response = await fetch(`${API_BASE}/prices/analytics/go-now?fuel_type=${fuelType}`)
      indicator = await response.json()
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
      
      <div class="price-comparison">
        <div class="price-box current" style="border-color: {getColor(indicator.recommendation)}">
          <div class="label">Current Price</div>
          <div class="value">€{indicator.current_price}</div>
        </div>
        
        <div class="vs">vs</div>
        
        <div class="price-box average">
          <div class="label">24h Average</div>
          <div class="value">€{indicator.avg_24h}</div>
        </div>
      </div>
      
      <div class="difference" style="color: {indicator.percentage < 0 ? '#10b981' : '#ef4444'}">
        <span class="percentage">
          {indicator.percentage > 0 ? '+' : ''}{indicator.percentage}%
        </span>
        <span class="amount">
          ({indicator.difference > 0 ? '+' : ''}€{Math.abs(indicator.difference).toFixed(3)})
        </span>
      </div>
    </div>
  {:else}
    <div class="card insufficient">
      <div class="header">
        <span class="icon">⏳</span>
        <h3>Should I refuel now?</h3>
      </div>
      <p class="no-data">Not enough data yet. Check back after 24 hours of price collection!</p>
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
  
  .price-comparison {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }
  
  .price-box {
    flex: 1;
    max-width: 140px;
    padding: 0.625rem 0.5rem;
    background: #161b22;
    border: 2px solid #30363d;
    border-radius: 8px;
    text-align: center;
  }
  
  .price-box.current {
    border-width: 2px;
  }
  
  .price-box .label {
    font-size: 0.65rem;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 0.25rem;
  }
  
  .price-box .value {
    font-size: 1.15rem;
    font-weight: bold;
    color: #c9d1d9;
  }
  
  .vs {
    color: #6e7681;
    font-size: 0.75rem;
    font-weight: 600;
    flex-shrink: 0;
  }
  
  .difference {
    text-align: center;
    font-size: 1rem;
    font-weight: bold;
  }
  
  .difference .amount {
    font-size: 0.8rem;
    opacity: 0.8;
    margin-left: 0.35rem;
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
    .price-comparison {
      gap: 1.25rem;
      margin-bottom: 1rem;
    }
    .price-box {
      max-width: 150px;
      padding: 0.875rem;
    }
    .price-box .label {
      font-size: 0.75rem;
      margin-bottom: 0.5rem;
    }
    .price-box .value {
      font-size: 1.35rem;
    }
    .vs {
      font-size: 0.875rem;
    }
    .difference {
      font-size: 1.15rem;
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
    .price-comparison {
      gap: 1.5rem;
    }
    .price-box .value {
      font-size: 1.5rem;
    }
    .difference {
      font-size: 1.25rem;
    }
    .difference .amount {
      font-size: 0.875rem;
    }
  }
</style>
