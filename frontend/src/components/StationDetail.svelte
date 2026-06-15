<script>
  import { onMount, createEventDispatcher } from 'svelte';
  import API_BASE, { safeFetch } from '../lib/api.js';

  export let stationId = '';

  const dispatch = createEventDispatcher();

  let station = null;
  let loading = true;
  let error = null;

  async function loadStation() {
    loading = true;
    error = null;
    try {
      station = await safeFetch(`${API_BASE}/stations/${stationId}/detail?hours=168`);
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }

  function close() {
    dispatch('close');
  }

  function formatPrice(price) {
    if (price === null || price === undefined) return '—';
    return `€${price.toFixed(3)}`;
  }

  onMount(loadStation);
</script>

<div class="detail-overlay" on:click={close} on:keydown={e => e.key === 'Escape' && close()}>
  <div class="detail-panel" on:click|stopPropagation>
    <button class="back-btn" on:click={close}>← Back to list</button>

    {#if loading}
      <div class="loading">Loading station details...</div>
    {:else if error}
      <div class="error">{error}</div>
    {:else if station}
      <div class="station-header">
        <h2>{station.name}</h2>
        <span class="brand-tag">{station.city || station.post_code || ''}</span>
        <span class="status" class:open={station.is_open} class:closed={!station.is_open}>
          {station.is_open ? '🟢 Open' : '🔴 Closed'}
        </span>
      </div>

      <div class="address">
        📍 {station.street} {station.house_number}, {station.post_code} {station.city}
      </div>

      <div class="map-container">
        <iframe
          title="Station location"
          width="100%"
          height="250"
          frameborder="0"
          style="border-radius: 8px; border: 1px solid #30363d;"
          src="https://www.openstreetmap.org/export/embed.html?bbox={station.longitude - 0.005}%2C{station.latitude - 0.003}%2C{station.longitude + 0.005}%2C{station.latitude + 0.003}&layer=mapnik&marker={station.latitude}%2C{station.longitude}"
        ></iframe>
        <a
          class="route-btn"
          href="https://www.google.com/maps/dir/?api=1&destination={station.latitude},{station.longitude}"
          target="_blank"
          rel="noopener noreferrer"
        >
          🧭 Route
        </a>
      </div>

      <div class="prices-section">
        <h3>Current Prices</h3>
        <div class="price-grid">
          <div class="price-card">
            <span class="fuel-label">E5</span>
            <span class="fuel-price">{formatPrice(station.current_e5)}</span>
          </div>
          <div class="price-card">
            <span class="fuel-label">E10</span>
            <span class="fuel-price">{formatPrice(station.current_e10)}</span>
          </div>
          <div class="price-card">
            <span class="fuel-label">Diesel</span>
            <span class="fuel-price">{formatPrice(station.current_diesel)}</span>
          </div>
        </div>
      </div>

      <div class="prices-section">
        <h3>7-Day Statistics ({station.price_count} data points)</h3>
        <table class="stats-table">
          <thead>
            <tr>
              <th>Fuel</th>
              <th>Avg</th>
              <th>Min</th>
              <th>Max</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>E5</td>
              <td>{formatPrice(station.avg_e5)}</td>
              <td class="min">{formatPrice(station.min_e5)}</td>
              <td class="max">{formatPrice(station.max_e5)}</td>
            </tr>
            <tr>
              <td>E10</td>
              <td>{formatPrice(station.avg_e10)}</td>
              <td class="min">{formatPrice(station.min_e10)}</td>
              <td class="max">{formatPrice(station.max_e10)}</td>
            </tr>
            <tr>
              <td>Diesel</td>
              <td>{formatPrice(station.avg_diesel)}</td>
              <td class="min">{formatPrice(station.min_diesel)}</td>
              <td class="max">{formatPrice(station.max_diesel)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    {/if}
  </div>
</div>

<style>
  .detail-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.6);
    z-index: 900;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 2rem 1rem;
    overflow-y: auto;
  }

  .detail-panel {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 1.5rem;
    width: 100%;
    max-width: 600px;
    margin-top: 1rem;
  }

  .back-btn {
    background: none;
    border: none;
    color: #3b82f6;
    cursor: pointer;
    font-size: 0.9rem;
    padding: 0.25rem 0;
    margin-bottom: 1rem;
    min-height: auto;
  }

  .back-btn:hover {
    text-decoration: underline;
  }

  .station-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
    margin-bottom: 0.5rem;
  }

  .station-header h2 {
    margin: 0;
    font-size: 1.3rem;
    color: #e6edf3;
  }

  .brand-tag {
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 0.2rem 0.5rem;
    font-size: 0.75rem;
    color: #3fb950;
    font-weight: 600;
  }

  .status {
    font-size: 0.8rem;
  }

  .address {
    color: #8b949e;
    font-size: 0.9rem;
    margin-bottom: 1rem;
  }

  .map-container {
    margin-bottom: 1.5rem;
  }

  .route-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    margin-top: 0.625rem;
    padding: 0.5rem 1rem;
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #e6edf3;
    font-size: 0.85rem;
    font-weight: 500;
    text-decoration: none;
    transition: border-color 0.2s, background 0.2s;
  }

  .route-btn:hover {
    border-color: #3b82f6;
    background: #30363d;
  }

  .prices-section {
    margin-bottom: 1.5rem;
  }

  .prices-section h3 {
    color: #c9d1d9;
    font-size: 1rem;
    margin: 0 0 0.75rem 0;
  }

  .price-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
  }

  .price-card {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 0.75rem;
    text-align: center;
  }

  .fuel-label {
    display: block;
    color: #8b949e;
    font-size: 0.75rem;
    font-weight: 600;
    margin-bottom: 0.25rem;
    text-transform: uppercase;
  }

  .fuel-price {
    display: block;
    color: #3b82f6;
    font-size: 1.2rem;
    font-weight: 700;
  }

  .stats-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
  }

  .stats-table th,
  .stats-table td {
    padding: 0.5rem 0.75rem;
    text-align: left;
    border-bottom: 1px solid #21262d;
  }

  .stats-table th {
    color: #8b949e;
    font-weight: 600;
    font-size: 0.8rem;
    text-transform: uppercase;
  }

  .stats-table td {
    color: #c9d1d9;
  }

  .stats-table .min {
    color: #3fb950;
  }

  .stats-table .max {
    color: #f85149;
  }

  .loading {
    text-align: center;
    padding: 3rem;
    color: #8b949e;
  }

  .error {
    background: #3f1f1f;
    color: #ff7b72;
    padding: 1rem;
    border-radius: 6px;
    border: 1px solid #5a2828;
  }

  @media (min-width: 640px) {
    .detail-panel {
      padding: 2rem;
    }

    .station-header h2 {
      font-size: 1.5rem;
    }
  }
</style>
