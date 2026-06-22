<script>
  import { createEventDispatcher, onDestroy, onMount, tick } from 'svelte';
  import L from 'leaflet';
  import 'leaflet/dist/leaflet.css';
  import { getAdminTrafficSummary } from '../lib/api.js';

  const dispatch = createEventDispatcher();

  const dayOptions = [7, 30, 90];
  const worldView = [18, 8];

  let days = 30;
  let loading = true;
  let error = '';
  let summary = null;
  let selectedPoint = null;
  let mapElement;
  let map;
  let markerLayer;

  function formatLocation(point) {
    return [point.city, point.country].filter(Boolean).join(', ') || 'Unknown';
  }

  function parseError(err) {
    try {
      const parsed = JSON.parse(err.message.replace(/^HTTP \d+: /, ''));
      return parsed.detail || err.message;
    } catch {
      return err.message;
    }
  }

  function ensureMap() {
    if (map || !mapElement) {
      return;
    }

    map = L.map(mapElement, {
      center: worldView,
      zoom: 2,
      minZoom: 2,
      maxZoom: 6,
      zoomControl: true,
      attributionControl: true,
      worldCopyJump: true,
    });

    L.tileLayer('/api/admin/map-tiles/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      tileSize: 256,
      maxZoom: 6,
      minZoom: 2,
      noWrap: false,
      crossOrigin: true,
    }).addTo(map);

    markerLayer = L.layerGroup().addTo(map);
    setTimeout(() => map.invalidateSize(), 50);
  }

  function renderMarkers() {
    if (!markerLayer) {
      return;
    }

    markerLayer.clearLayers();

    for (const point of summary?.map_points || []) {
      const marker = L.circleMarker([point.latitude, point.longitude], {
        radius: Math.min(18, 6 + point.count),
        color: '#d7f8ff',
        weight: 2,
        fillColor: '#38bdf8',
        fillOpacity: 0.55,
      });

      marker.on('click', () => {
        selectedPoint = point;
      });

      marker.bindTooltip(`${formatLocation(point)}: ${point.count} visit${point.count === 1 ? '' : 's'}`, {
        direction: 'top',
        opacity: 0.95,
      });

      marker.addTo(markerLayer);
    }

    map.setView(worldView, 2);
    setTimeout(() => map.invalidateSize(), 20);
  }

  async function loadSummary() {
    loading = true;
    error = '';
    selectedPoint = null;
    try {
      summary = await getAdminTrafficSummary(days);
    } catch (err) {
      error = parseError(err);
    } finally {
      loading = false;
    }
  }

  $: if (!loading && !error && summary && mapElement) {
    tick().then(() => {
      ensureMap();
      renderMarkers();
    });
  }

  function close() {
    dispatch('close');
  }

  onMount(() => {
    loadSummary();
  });

  onDestroy(() => {
    if (map) {
      map.remove();
      map = null;
    }
  });
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<div class="modal-overlay" on:click={close}>
  <div class="modal" on:click|stopPropagation>
    <button class="close-btn" on:click={close}>&times;</button>

    <div class="header-row">
      <div>
        <h2>Admin Traffic</h2>
        <p class="subtitle">Estimated visitor locations and requested app pages.</p>
      </div>

      <div class="range-picker">
        {#each dayOptions as option}
          <button class:active={days === option} on:click={() => { days = option; loadSummary(); }}>
            {option}d
          </button>
        {/each}
      </div>
    </div>

    {#if loading}
      <div class="state-card">Loading admin traffic...</div>
    {:else if error}
      <div class="state-card error">{error}</div>
    {:else}
      <div class="stats-grid">
        <div class="stat-card">
          <span class="stat-label">Tracked Visits</span>
          <strong>{summary.total_visits}</strong>
        </div>
        <div class="stat-card">
          <span class="stat-label">Mapped Locations</span>
          <strong>{summary.map_points.length}</strong>
        </div>
        <div class="stat-card">
          <span class="stat-label">Top Source</span>
          <strong>{summary.top_sources[0]?.source || 'direct'}</strong>
        </div>
      </div>

      <div class="map-card">
        <div class="card-head">
          <h3>Traffic Map</h3>
        </div>

        <div class="world-map" bind:this={mapElement} aria-label="Traffic world map"></div>

        {#if selectedPoint}
          <div class="map-detail">
            <strong>{formatLocation(selectedPoint)}</strong>
            <span>{selectedPoint.count} visit{selectedPoint.count === 1 ? '' : 's'}</span>
            <span>Top pages: {selectedPoint.pages.join(', ') || 'unknown'}</span>
          </div>
        {:else if !summary.map_points.length}
          <div class="map-detail muted">No public coordinates to plot yet. Local or private-network traffic is still listed below.</div>
        {:else}
          <div class="map-detail muted">Click a marker to inspect that traffic cluster.</div>
        {/if}
      </div>

      <div class="grid two-col">
        <div class="panel">
          <h3>Top Pages</h3>
          {#if summary.top_pages.length}
            {#each summary.top_pages as item}
              <div class="list-row">
                <span>{item.page}</span>
                <strong>{item.count}</strong>
              </div>
            {/each}
          {:else}
            <div class="empty">No page views yet.</div>
          {/if}
        </div>

        <div class="panel">
          <h3>Traffic Sources</h3>
          {#if summary.top_sources.length}
            {#each summary.top_sources as item}
              <div class="list-row">
                <span>{item.source}</span>
                <strong>{item.count}</strong>
              </div>
            {/each}
          {:else}
            <div class="empty">No sources tracked yet.</div>
          {/if}
        </div>
      </div>

      <div class="panel recent-panel">
        <h3>Recent Visits</h3>
        {#if summary.recent_visits.length}
          <div class="recent-list">
            {#each summary.recent_visits as visit}
              <div class="recent-row">
                <div>
                  <strong>{visit.page}</strong>
                  <span>{visit.path}</span>
                </div>
                <div>
                  <span>{[visit.city, visit.country].filter(Boolean).join(', ') || 'Unknown'}</span>
                  <span>{visit.source}</span>
                </div>
                <time>{new Date(visit.visited_at).toLocaleString()}</time>
              </div>
            {/each}
          </div>
        {:else}
          <div class="empty">No visits recorded for this range.</div>
        {/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.74);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1100;
    padding: 1rem;
  }

  .modal {
    width: min(1100px, 100%);
    max-height: calc(100vh - 2rem);
    overflow-y: auto;
    background: #10161d;
    border: 1px solid #2b3642;
    border-radius: 18px;
    padding: 1.5rem;
    position: relative;
    box-shadow: 0 22px 70px rgba(0, 0, 0, 0.45);
  }

  .close-btn {
    position: absolute;
    top: 1rem;
    right: 1rem;
    background: none;
    border: none;
    color: #8aa0b6;
    font-size: 1.5rem;
    cursor: pointer;
    min-height: auto;
  }

  .header-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.25rem;
    padding-right: 2rem;
  }

  h2 {
    margin: 0;
    color: #edf5ff;
    font-size: 1.6rem;
  }

  .subtitle {
    margin: 0.35rem 0 0;
    color: #8aa0b6;
    font-size: 0.9rem;
  }

  .range-picker {
    display: flex;
    gap: 0.5rem;
  }

  .range-picker button {
    min-height: auto;
    padding: 0.55rem 0.8rem;
    border-radius: 999px;
    border: 1px solid #334557;
    background: #18222c;
    color: #9db5ca;
    cursor: pointer;
  }

  .range-picker button.active {
    background: #24517a;
    color: #f1f7ff;
    border-color: #4d8ed0;
  }

  .state-card,
  .panel,
  .map-card,
  .stat-card {
    background: #141d26;
    border: 1px solid #273341;
    border-radius: 14px;
  }

  .state-card {
    padding: 1rem;
    color: #d7e5f3;
  }

  .state-card.error {
    color: #ff8b83;
    border-color: #5b2b2f;
    background: #27181a;
  }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.9rem;
    margin-bottom: 1rem;
  }

  .stat-card {
    padding: 1rem;
  }

  .stat-label {
    display: block;
    color: #8aa0b6;
    font-size: 0.8rem;
    margin-bottom: 0.45rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .stat-card strong {
    color: #edf5ff;
    font-size: 1.45rem;
  }

  .map-card {
    padding: 1rem;
    margin-bottom: 1rem;
  }

  .card-head {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: baseline;
    margin-bottom: 0.85rem;
  }

  .card-head h3,
  .panel h3 {
    margin: 0;
    color: #edf5ff;
    font-size: 1rem;
  }

  .card-head span {
    color: #7f94a8;
    font-size: 0.8rem;
  }

  .world-map {
    width: 100%;
    height: 430px;
    border-radius: 16px;
    overflow: hidden;
    border: 1px solid #24313d;
  }

  :global(.leaflet-container) {
    background: #102032;
    font: inherit;
  }

  :global(.leaflet-control-zoom a),
  :global(.leaflet-control-attribution) {
    background: #141d26;
    color: #dceaf7;
    border-color: #2d3d4d;
  }

  :global(.leaflet-tooltip) {
    background: rgba(12, 22, 34, 0.94);
    color: #edf5ff;
    border: 1px solid #2e4254;
    border-radius: 8px;
    box-shadow: none;
  }

  .map-detail {
    margin-top: 0.8rem;
    padding: 0.8rem 0.95rem;
    border-radius: 12px;
    background: #0f1720;
    border: 1px solid #253240;
    color: #dceaf7;
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
  }

  .map-detail.muted {
    color: #89a0b5;
  }

  .two-col {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .panel {
    padding: 1rem;
  }

  .list-row {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.65rem 0;
    border-bottom: 1px solid #22303c;
    color: #dceaf7;
  }

  .list-row:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }

  .recent-list {
    display: flex;
    flex-direction: column;
    gap: 0.65rem;
  }

  .recent-row {
    display: grid;
    grid-template-columns: 1.2fr 1fr auto;
    gap: 1rem;
    align-items: center;
    padding: 0.8rem 0.95rem;
    background: #0f1720;
    border: 1px solid #22303c;
    border-radius: 12px;
  }

  .recent-row div {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .recent-row strong {
    color: #edf5ff;
  }

  .recent-row span,
  .recent-row time,
  .empty {
    color: #8aa0b6;
    font-size: 0.85rem;
  }

  .recent-panel {
    margin-bottom: 0;
  }

  @media (max-width: 820px) {
    .stats-grid,
    .two-col,
    .recent-row {
      grid-template-columns: 1fr;
    }

    .header-row,
    .card-head {
      flex-direction: column;
      align-items: stretch;
    }
  }
</style>