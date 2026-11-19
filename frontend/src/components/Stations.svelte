<script>
  // Stations tab: the live list, or the "usually cheapest" ranking.
  import CurrentPrices from './CurrentPrices.svelte'
  import Leaderboard from './Leaderboard.svelte'
  import { readPref, writePref } from '../lib/format.js'

  export let fuelType = 'e5'

  let view = readPref('fuel_stations_view', 'now') === 'usual' ? 'usual' : 'now'
  $: writePref('fuel_stations_view', view)
</script>

<div class="card">
  <div class="head">
    <h2>{view === 'now' ? 'All stations' : 'Usually cheapest'}</h2>
    <div class="seg" role="group" aria-label="Station view">
      <button class:active={view === 'now'} aria-pressed={view === 'now'} on:click={() => (view = 'now')}>Price now</button>
      <button class:active={view === 'usual'} aria-pressed={view === 'usual'} on:click={() => (view = 'usual')}>Usually cheapest</button>
    </div>
  </div>
  {#if view === 'now'}
    <CurrentPrices {fuelType} />
  {:else}
    <Leaderboard {fuelType} />
  {/if}
</div>

<style>
  .card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 0.75rem;
    margin-bottom: 1rem;
  }

  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }

  h2 {
    margin: 0;
    font-size: 1.1rem;
    color: #e6edf3;
  }

  .seg {
    display: inline-flex;
    gap: 2px;
    padding: 3px;
    background: #0f1419;
    border: 1px solid #30363d;
    border-radius: 8px;
  }

  .seg button {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: #8b949e;
    font-size: 0.82rem;
    font-weight: 500;
    padding: 0.3rem 0.75rem;
    min-height: 2rem;
    cursor: pointer;
  }

  .seg button.active {
    background: rgba(59, 130, 246, 0.16);
    border-color: #3b82f6;
    color: #79b8ff;
  }

  @media (min-width: 640px) {
    .card {
      padding: 1.25rem;
    }
    h2 {
      font-size: 1.2rem;
    }
  }

  @media (min-width: 1024px) {
    .card {
      padding: 1.5rem;
    }
  }
</style>
