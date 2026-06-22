<script>
  import { onMount } from 'svelte'
  import PriceChart from './components/PriceChart.svelte'
  import CurrentPrices from './components/CurrentPrices.svelte'
  import LowestPrices from './components/LowestPrices.svelte'
  import CurrentLowestPrices from './components/CurrentLowestPrices.svelte'
  import Statistics from './components/Statistics.svelte'
  import GoNowIndicator from './components/GoNowIndicator.svelte'
  import OilPrice from './components/OilPrice.svelte'
  import PriceHeatmap from './components/PriceHeatmap.svelte'
  import UserMenu from './components/UserMenu.svelte'
  import Favorites from './components/Favorites.svelte'
  import { currentUser } from './lib/auth.js'
  import { getMe, trackPageView } from './lib/api.js'
  
  let selectedFuelType = 'e5'
  let selectedHours = 24
  let activeTab = 'overview'
  let lastTrackedPage = ''
  
  // Calculate YTD hours (from Jan 1 of current year to now)
  function getYTDHours() {
    const now = new Date()
    const startOfYear = new Date(now.getFullYear(), 0, 1)
    const diffMs = now - startOfYear
    return Math.floor(diffMs / (1000 * 60 * 60))
  }
  
  const timeRanges = [
    { label: '24h', hours: 24 },
    { label: '3d', hours: 72 },
    { label: '7d', hours: 168 },
    { label: '1m', hours: 720 },
    { label: 'YTD', hours: getYTDHours() },
    { label: 'All', hours: 999999 }
  ]

  onMount(() => {
    const refreshCurrentUser = async () => {
      if ($currentUser) {
        try {
          const user = await getMe()
          currentUser.updateUser({
            id: user.id,
            username: user.username,
            email: user.email,
            is_admin: user.is_admin,
          })
        } catch {
          currentUser.logout()
        }
      }
    }

    refreshCurrentUser()
  })

  $: if (activeTab && activeTab !== lastTrackedPage) {
    lastTrackedPage = activeTab
    trackPageView(activeTab, window.location.pathname, document.referrer)
  }
</script>

<main>
  <header>
    <div class="container header-row">
      <div>
        <h1>⛽ FuelTracker</h1>
        <p class="subtitle">Live Fuel Price Tracking & Analysis</p>
      </div>
      <UserMenu />
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
        <button 
          class:active={selectedFuelType === 'oil'} 
          on:click={() => selectedFuelType = 'oil'}
        >
          Oil
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
      <button class:active={activeTab === 'statistics'} on:click={() => activeTab = 'statistics'}>
        📈 Statistics
      </button>
      <button class:active={activeTab === 'leaderboard'} on:click={() => activeTab = 'leaderboard'}>
        🏆 Literboard
      </button>
      <button class:active={activeTab === 'stations'} on:click={() => activeTab = 'stations'}>
        ⛽ All Stations
      </button>
    </div>

    {#if activeTab === 'overview'}
      {#if selectedFuelType === 'oil'}
        <OilPrice hours={selectedHours} />
      {:else}
        <GoNowIndicator fuelType={selectedFuelType} />

        <div class="main-chart">
          <PriceChart fuelType={selectedFuelType} hours={selectedHours} />
        </div>

        {#if $currentUser}
          <div class="card">
            <Favorites selectedFuelType={selectedFuelType} />
          </div>
        {/if}

        <div class="card">
          <h2>Best Prices Now</h2>
          <CurrentLowestPrices fuelType={selectedFuelType} />
        </div>
      {/if}

    {:else if activeTab === 'statistics'}
      {#if selectedFuelType === 'oil'}
        <div class="card">
          <div class="oil-notice">📊 Statistics are not available for crude oil. <br> Switch to E5, E10, or Diesel to see station statistics.</div>
        </div>
      {:else}
        <div class="grid">
          <div class="card">
            <h2>📊 Statistics</h2>
            <Statistics fuelType={selectedFuelType} hours={selectedHours} />
          </div>

          <div class="card">
            <h2>🏆 Lowest Prices Today</h2>
            <LowestPrices fuelType={selectedFuelType} hours={selectedHours} />
          </div>
        </div>
        <div class="card">
          <PriceHeatmap fuelType={selectedFuelType} />
        </div>
      {/if}
    {:else if activeTab === 'leaderboard'}
      {#if selectedFuelType === 'oil'}
        <div class="card">
          <div class="oil-notice">🏆 The Literboard is not available for crude oil <br> Switch to E5, E10, or Diesel to see station statistics.</div>
        </div>
      {:else}
        <div class="card">
          <h2>🏆 Top Stations Leaderboard</h2>
          <Statistics fuelType={selectedFuelType} hours={selectedHours} leaderboardOnly={true} />
        </div>
      {/if}
    {:else if activeTab === 'stations'}
      {#if selectedFuelType === 'oil'}
        <div class="card">
          <div class="oil-notice">No petrol stations pump crude oil. <br> Switch to E5, E10, or Diesel to see station prices.</div>
        </div>
      {:else}
        <div class="card">
          <h2>⛽ Current Prices at All Stations</h2>
          <CurrentPrices fuelType={selectedFuelType} />
        </div>
      {/if}
    {/if}
  </div>
</main>

<style>
  :global(*) {
    box-sizing: border-box;
  }

  :global(body) {
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    background: #0f1419;
    color: #e6edf3;
    -webkit-text-size-adjust: 100%;
    overflow-x: hidden;
  }

  header {
    background: linear-gradient(135deg, #1f2937 0%, #111827 100%);
    border-bottom: 1px solid #30363d;
    padding: 1.25rem 0;
    margin-bottom: 1rem;
  }

  .header-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  h1 {
    margin: 0;
    font-size: 1.75rem;
    font-weight: 700;
    background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .subtitle {
    margin: 0.25rem 0 0 0;
    color: #8b949e;
    font-size: 0.9rem;
  }

  .container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 0 0.75rem;
  }

  .controls {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }

  .fuel-selector, .time-selector {
    display: flex;
    gap: 0.375rem;
    align-items: center;
    flex-wrap: wrap;
  }

  .tabs {
    display: flex;
    gap: 0;
    margin-bottom: 1rem;
    border-bottom: 2px solid #30363d;
    padding-bottom: 0;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }

  .tabs::-webkit-scrollbar {
    display: none;
  }

  .tabs button {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: #8b949e;
    padding: 0.625rem 0.875rem;
    border-radius: 0;
    cursor: pointer;
    font-weight: 500;
    font-size: 0.875rem;
    transition: all 0.2s;
    margin-bottom: -2px;
    white-space: nowrap;
    flex-shrink: 0;
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
    margin-right: 0.25rem;
    font-size: 0.85rem;
    white-space: nowrap;
  }

  button {
    background: #21262d;
    border: 1px solid #30363d;
    color: #8b949e;
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    cursor: pointer;
    font-weight: 500;
    font-size: 0.85rem;
    transition: all 0.2s;
    min-height: 2.5rem;
    touch-action: manipulation;
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
    padding: 0.75rem;
    margin-bottom: 1rem;
  }

  .grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
  }

  .grid .card {
    margin-bottom: 0;
  }

  .oil-notice {
    padding: 1.25rem;
    background: #1c2128;
    border: 1px solid #30363d;
    border-left: 3px solid #f59e0b;
    border-radius: 6px;
    color: #8b949e;
    font-size: 0.9rem;
    line-height: 1.5;
  }

  h2 {
    margin: 0 0 0.75rem 0;
    font-size: 1.1rem;
    color: #e6edf3;
  }

  /* Tablet and up */
  @media (min-width: 640px) {
    header {
      padding: 1.5rem 0;
      margin-bottom: 1.5rem;
    }

    h1 {
      font-size: 2rem;
    }

    .subtitle {
      font-size: 1rem;
    }

    .container {
      padding: 0 1.25rem;
    }

    .controls {
      flex-direction: row;
      gap: 1.5rem;
      margin-bottom: 1.5rem;
    }

    .fuel-selector, .time-selector {
      gap: 0.5rem;
    }

    .tabs button {
      padding: 0.75rem 1.25rem;
      font-size: 0.95rem;
    }

    label {
      font-size: 0.9rem;
      margin-right: 0.5rem;
    }

    button {
      padding: 0.5rem 1rem;
      font-size: 0.9rem;
    }

    .main-chart {
      padding: 1.25rem;
      margin-bottom: 1.5rem;
    }

    .card {
      padding: 1.25rem;
      margin-bottom: 1.5rem;
    }

    h2 {
      font-size: 1.2rem;
    }
  }

  /* Desktop */
  @media (min-width: 1024px) {
    header {
      padding: 2rem 0;
      margin-bottom: 2rem;
    }

    h1 {
      font-size: 2.5rem;
    }

    .subtitle {
      font-size: 1.1rem;
    }

    .container {
      padding: 0 2rem;
    }

    .controls {
      gap: 2rem;
      margin-bottom: 2rem;
    }

    .tabs button {
      padding: 0.75rem 1.5rem;
      font-size: 1rem;
    }

    .main-chart {
      padding: 1.5rem;
      margin-bottom: 2rem;
    }

    .grid {
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 1.5rem;
      margin-bottom: 2rem;
    }

    .card {
      padding: 1.5rem;
      margin-bottom: 2rem;
    }

    h2 {
      font-size: 1.3rem;
    }
  }
</style>
