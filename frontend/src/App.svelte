<script>
  import PriceChart from './components/PriceChart.svelte'
  import CurrentPrices from './components/CurrentPrices.svelte'
  import LowestPrices from './components/LowestPrices.svelte'
  import Statistics from './components/Statistics.svelte'
  import MapView from './components/MapView.svelte'
  
  let selectedFuelType = 'e5'
  let selectedHours = 24
  
  const timeRanges = [
    { label: '24h', hours: 24 },
    { label: '3d', hours: 72 },
    { label: '7d', hours: 168 },
    { label: '1m', hours: 720 },
    { label: 'All', hours: 999999 }
  ]
</script>

<main>
  <header>
    <div class="container">
      <h1>⛽ FuelTracker</h1>
      <p class="subtitle">Live Fuel Price Tracking & Analysis</p>
    </div>
  </header>

  <div class="container">
    <div class="controls">
      <div class="fuel-selector">
        <label>Fuel Type:</label>
        <button 
          class:active={selectedFuelType === 'e5'} 
          on:click={() => selectedFuelType = 'e5'}
        >
          E5
        </button>
        <button 
          class:active={selectedFuelType === 'e10'} 
          on:click={() => selectedFuelType = 'e10'}
        >
          E10
        </button>
        <button 
          class:active={selectedFuelType === 'diesel'} 
          on:click={() => selectedFuelType = 'diesel'}
        >
          Diesel
        </button>
      </div>

      <div class="time-selector">
        <label>Time Range:</label>
        {#each timeRanges as range}
          <button 
            class:active={selectedHours === range.hours} 
            on:click={() => selectedHours = range.hours}
          >
            {range.label}
          </button>
        {/each}
      </div>
    </div>

    <div class="main-chart">
      <PriceChart fuelType={selectedFuelType} hours={selectedHours} />
    </div>

    <div class="grid">
      <div class="card">
        <h2>📊 Statistics</h2>
        <Statistics fuelType={selectedFuelType} hours={selectedHours} />
      </div>
      
      <div class="card">
        <h2>🏆 Lowest Prices</h2>
        <LowestPrices fuelType={selectedFuelType} hours={selectedHours} />
      </div>
    </div>

    <div class="card">
      <h2>🗺️ Stations on Map</h2>
      <MapView fuelType={selectedFuelType} />
    </div>

    <div class="card">
      <h2>⛽ Current Prices at Stations</h2>
      <CurrentPrices fuelType={selectedFuelType} />
    </div>
  </div>
</main>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    background: #0f1419;
    color: #e6edf3;
  }

  header {
    background: linear-gradient(135deg, #1f2937 0%, #111827 100%);
    border-bottom: 1px solid #30363d;
    padding: 2rem 0;
    margin-bottom: 2rem;
  }

  h1 {
    margin: 0;
    font-size: 2.5rem;
    font-weight: 700;
    background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .subtitle {
    margin: 0.5rem 0 0 0;
    color: #8b949e;
    font-size: 1.1rem;
  }

  .container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 0 2rem;
  }

  .controls {
    display: flex;
    gap: 2rem;
    margin-bottom: 2rem;
    flex-wrap: wrap;
  }

  .fuel-selector, .time-selector {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  label {
    font-weight: 600;
    color: #8b949e;
    margin-right: 0.5rem;
  }

  button {
    background: #21262d;
    border: 1px solid #30363d;
    color: #8b949e;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    cursor: pointer;
    font-weight: 500;
    transition: all 0.2s;
  }

  button:hover {
    background: #30363d;
    border-color: #3b82f6;
  }

  button.active {
    background: #3b82f6;
    border-color: #3b82f6;
    color: white;
  }

  .main-chart {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 2rem;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 1.5rem;
    margin-bottom: 2rem;
  }

  .card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 2rem;
  }

  h2 {
    margin: 0 0 1rem 0;
    font-size: 1.3rem;
    color: #e6edf3;
  }
</style>
