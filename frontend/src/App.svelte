<script>
  import PriceChart from './components/PriceChart.svelte'
  import CurrentPrices from './components/CurrentPrices.svelte'
  import LowestPrices from './components/LowestPrices.svelte'
  import CurrentLowestPrices from './components/CurrentLowestPrices.svelte'
  import Statistics from './components/Statistics.svelte'
  import GoNowIndicator from './components/GoNowIndicator.svelte'
  
  let selectedFuelType = 'e5'
  let selectedHours = 24
  let activeTab = 'overview'
  
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

    <div class="tabs">
      <button class:active={activeTab === 'overview'} on:click={() => activeTab = 'overview'}>
        📊 Overview
      </button>
      <button class:active={activeTab === 'leaderboard'} on:click={() => activeTab = 'leaderboard'}>
        🏆 Literboard
      </button>
      <button class:active={activeTab === 'stations'} on:click={() => activeTab = 'stations'}>
        ⛽ All Stations
      </button>
    </div>

    {#if activeTab === 'overview'}
      <GoNowIndicator fuelType={selectedFuelType} />

      <div class="main-chart">
        <PriceChart fuelType={selectedFuelType} hours={selectedHours} />
      </div>

      <div class="card">
        <h2>Best Prices Now</h2>
        <CurrentLowestPrices fuelType={selectedFuelType} />
      </div>

      <div class="grid">
        <div class="card">
          <h2>📊 Statistics</h2>
          <Statistics fuelType={selectedFuelType} hours={selectedHours} />
        </div>
        
        <div class="card">
          <h2>🏆 Lowest Prices Ever</h2>
          <LowestPrices fuelType={selectedFuelType} hours={selectedHours} />
        </div>
      </div>
    {:else if activeTab === 'leaderboard'}
      <div class="card">
        <h2>🏆 Top Stations Leaderboard</h2>
        <Statistics fuelType={selectedFuelType} hours={selectedHours} leaderboardOnly={true} />
      </div>
    {:else if activeTab === 'stations'}
      <div class="card">
        <h2>⛽ Current Prices at All Stations</h2>
        <CurrentPrices fuelType={selectedFuelType} />
      </div>
    {/if}
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

  .tabs {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 2rem;
    border-bottom: 2px solid #30363d;
    padding-bottom: 0;
  }

  .tabs button {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: #8b949e;
    padding: 0.75rem 1.5rem;
    border-radius: 0;
    cursor: pointer;
    font-weight: 500;
    font-size: 1rem;
    transition: all 0.2s;
    margin-bottom: -2px;
  }

  .tabs button:hover {
    background: transparent;
    border-bottom-color: #58a6ff;
    color: #c9d1d9;
  }

  .tabs button.active {
    background: transparent;
    border-bottom-color: #3b82f6;
    color: #3b82f6;
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
