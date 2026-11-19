<script>
  import { onMount } from 'svelte'
  import GoNowIndicator from './components/GoNowIndicator.svelte'
  import CurrentLowestPrices from './components/CurrentLowestPrices.svelte'
  import Favorites from './components/Favorites.svelte'
  import Outlook from './components/Outlook.svelte'
  import Stations from './components/Stations.svelte'
  import History from './components/History.svelte'
  import Savings from './components/Savings.svelte'
  import UserMenu from './components/UserMenu.svelte'
  import { currentUser } from './lib/auth.js'
  import { getMe, trackPageView } from './lib/api.js'
  import { readPref, writePref } from './lib/format.js'

  const fuelOptions = [
    { value: 'e5', label: 'E5' },
    { value: 'e10', label: 'E10' },
    { value: 'diesel', label: 'Diesel' },
  ]

  const tabs = [
    { id: 'now', icon: '⛽', label: 'Now' },
    { id: 'forecast', icon: '🔮', label: 'Forecast' },
    { id: 'stations', icon: '📍', label: 'Stations' },
    { id: 'history', icon: '📈', label: 'History' },
    { id: 'savings', icon: '💰', label: 'Savings', auth: true },
  ]
  // Old tab names still work in links/bookmarks.
  const LEGACY = { overview: 'now', outlook: 'forecast', statistics: 'history' }

  let selectedFuelType = readPref('fuel_type', 'e5')
  if (!fuelOptions.some((o) => o.value === selectedFuelType)) selectedFuelType = 'e5'
  $: writePref('fuel_type', selectedFuelType)

  function tabFromHash() {
    const h = window.location.hash.slice(1)
    const id = LEGACY[h] || h
    return tabs.some((t) => t.id === id) ? id : 'now'
  }

  let activeTab = tabFromHash()
  let lastTrackedPage = ''

  function openTab(id) {
    if (window.location.hash !== '#' + id) window.location.hash = id // adds a history entry (back button works)
    activeTab = id
    window.scrollTo({ top: 0 })
  }

  onMount(() => {
    const onHash = () => (activeTab = tabFromHash())
    window.addEventListener('hashchange', onHash)

    if ($currentUser) {
      getMe()
        .then((user) =>
          currentUser.updateUser({
            id: user.id,
            username: user.username,
            email: user.email,
            is_admin: user.is_admin,
          })
        )
        .catch(() => currentUser.logout())
    }

    return () => window.removeEventListener('hashchange', onHash)
  })

  $: visibleTabs = tabs.filter((t) => !t.auth || $currentUser)
  $: if (!$currentUser && activeTab === 'savings') activeTab = 'now'

  $: if (activeTab && activeTab !== lastTrackedPage) {
    lastTrackedPage = activeTab
    trackPageView(activeTab, window.location.pathname, document.referrer)
  }
</script>

<header>
  <div class="container header-row">
    <h1>⛽ FuelTracker</h1>
    <UserMenu />
  </div>
</header>

<div class="bar">
  <div class="container bar-row">
    <div class="seg fuel" role="group" aria-label="Fuel type">
      {#each fuelOptions as opt}
        <button
          class:active={selectedFuelType === opt.value}
          aria-pressed={selectedFuelType === opt.value}
          on:click={() => (selectedFuelType = opt.value)}
        >
          {opt.label}
        </button>
      {/each}
    </div>

    <nav class="tabs" aria-label="Sections">
      {#each visibleTabs as tab}
        <a
          href="#{tab.id}"
          class:active={activeTab === tab.id}
          aria-current={activeTab === tab.id ? 'page' : undefined}
          on:click|preventDefault={() => openTab(tab.id)}
        >
          <span class="tab-icon" aria-hidden="true">{tab.icon}</span><span>{tab.label}</span>
        </a>
      {/each}
    </nav>
  </div>
</div>

<main class="container">
  {#if activeTab === 'now'}
    <GoNowIndicator fuelType={selectedFuelType} />

    <div class="now-grid" class:single={!$currentUser}>
      <section class="card">
        <div class="card-head">
          <h2>Best prices now</h2>
          <a href="#stations" class="more" on:click|preventDefault={() => openTab('stations')}>All stations →</a>
        </div>
        <CurrentLowestPrices fuelType={selectedFuelType} />
      </section>

      {#if $currentUser}
        <section class="card">
          <Favorites {selectedFuelType} />
        </section>
      {/if}
    </div>
  {:else if activeTab === 'forecast'}
    <Outlook fuelType={selectedFuelType} />
  {:else if activeTab === 'stations'}
    <Stations fuelType={selectedFuelType} />
  {:else if activeTab === 'history'}
    <History fuelType={selectedFuelType} />
  {:else if activeTab === 'savings' && $currentUser}
    <section class="card">
      <Savings {selectedFuelType} />
    </section>
  {/if}
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

  :global(button:focus-visible),
  :global(a:focus-visible),
  :global(input:focus-visible),
  :global(select:focus-visible),
  :global(summary:focus-visible) {
    outline: 2px solid #58a6ff;
    outline-offset: 2px;
  }

  @media (prefers-reduced-motion: reduce) {
    :global(*) {
      transition: none !important;
      animation: none !important;
    }
  }

  .container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 0 0.75rem;
  }

  /* ---------- header ---------- */
  header {
    background: linear-gradient(135deg, #1f2937 0%, #111827 100%);
    border-bottom: 1px solid #30363d;
    padding: 0.6rem 0;
  }

  .header-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  h1 {
    margin: 0;
    font-size: 1.3rem;
    font-weight: 700;
    background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  /* ---------- sticky bar: fuel selector (+ tabs on wider screens) ---------- */
  .bar {
    position: sticky;
    top: 0;
    z-index: 20;
    /* No backdrop-filter here: it would make the fixed bottom tab bar (a child)
       position relative to this bar instead of the viewport. */
    background: #0f1419;
    border-bottom: 1px solid #30363d;
    margin-bottom: 1rem;
  }

  .bar-row {
    display: flex;
    align-items: center;
    padding-top: 0.5rem;
    padding-bottom: 0.5rem;
  }

  .seg {
    display: inline-flex;
    gap: 2px;
    padding: 3px;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
  }

  .seg button {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: #8b949e;
    font-size: 0.85rem;
    font-weight: 600;
    padding: 0.3rem 0.85rem;
    min-height: 2.25rem;
    cursor: pointer;
    touch-action: manipulation;
  }

  .seg button:hover {
    background: #21262d;
    color: #c9d1d9;
  }

  .seg button.active {
    background: rgba(59, 130, 246, 0.16);
    border-color: #3b82f6;
    color: #79b8ff;
  }

  .fuel {
    width: 100%;
  }

  .fuel button {
    flex: 1;
  }

  /* Phones: tabs are a bottom bar, within thumb reach. */
  .tabs {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 30;
    display: flex;
    background: rgba(13, 17, 23, 0.97);
    border-top: 1px solid #30363d;
    padding-bottom: env(safe-area-inset-bottom);
  }

  .tabs a {
    flex: 1 1 0;
    min-width: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.15rem;
    min-height: 3.5rem;
    color: #8b949e;
    text-decoration: none;
    font-size: 0.7rem;
    font-weight: 500;
    border-top: 2px solid transparent;
    touch-action: manipulation;
  }

  .tabs a.active {
    color: #58a6ff;
    border-top-color: #3b82f6;
  }

  .tab-icon {
    font-size: 1.15rem;
    line-height: 1;
  }

  main {
    padding-bottom: calc(4.5rem + env(safe-area-inset-bottom));
  }

  /* ---------- content ---------- */
  .card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 0.75rem;
    margin-bottom: 1rem;
  }

  .card-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  h2 {
    margin: 0;
    font-size: 1.1rem;
    color: #e6edf3;
  }

  .more {
    color: #58a6ff;
    font-size: 0.82rem;
    text-decoration: none;
    white-space: nowrap;
  }

  .more:hover {
    text-decoration: underline;
  }

  .now-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 0 1rem;
  }

  /* ---------- tablet and up ---------- */
  @media (min-width: 640px) {
    .container {
      padding: 0 1.25rem;
    }

    header {
      padding: 0.9rem 0;
    }

    h1 {
      font-size: 1.6rem;
    }

    .bar {
      margin-bottom: 1.5rem;
    }

    .bar-row {
      padding-top: 0;
      padding-bottom: 0;
      gap: 1rem;
    }

    .fuel {
      width: auto;
      order: 2;
      margin-left: auto;
    }

    .fuel button {
      flex: none;
    }

    .tabs {
      position: static;
      order: 1;
      background: transparent;
      border-top: none;
      padding-bottom: 0;
    }

    .tabs a {
      flex: none;
      flex-direction: row;
      gap: 0.45rem;
      min-height: 3rem;
      padding: 0 0.9rem;
      font-size: 0.95rem;
      border-top: none;
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
    }

    .tabs a:hover {
      color: #c9d1d9;
      border-bottom-color: #30363d;
    }

    .tabs a.active {
      color: #58a6ff;
      border-bottom-color: #3b82f6;
    }

    .tab-icon {
      font-size: 1rem;
    }

    main {
      padding-bottom: 2rem;
    }

    .card {
      padding: 1.25rem;
      margin-bottom: 1.5rem;
    }

    h2 {
      font-size: 1.2rem;
    }
  }

  /* ---------- desktop ---------- */
  @media (min-width: 1024px) {
    .container {
      padding: 0 2rem;
    }

    h1 {
      font-size: 1.85rem;
    }

    .card {
      padding: 1.5rem;
    }

    .now-grid {
      grid-template-columns: 1fr 1fr;
      gap: 0 1.5rem;
    }

    .now-grid.single {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
