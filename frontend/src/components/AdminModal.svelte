<script>
  import { createEventDispatcher, onDestroy, onMount } from 'svelte';
  import L from 'leaflet';
  import 'leaflet/dist/leaflet.css';
  
  export let isOpen = false;
  
  let mapContainer;
  let map;
  
  const dispatch = createEventDispatcher();
  
  onMount(() => {
    if (isOpen && mapContainer && !map) {
      map = L.map(mapContainer).setView([51.505, -0.09], 13);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap'
      }).addTo(map);
    }
  });
  
  onDestroy(() => {
    if (map) {
      map.remove();
    }
  });
  
  function closeModal() {
    dispatch('close');
  }
</script>

{#if isOpen}
  <div class="modal-overlay" on:click={closeModal}>
    <div class="modal-content" on:click|stopPropagation>
      <button class="close-btn" on:click={closeModal}>×</button>
      <h2>Admin Panel</h2>
      <div bind:this={mapContainer} class="map-container"></div>
    </div>
  </div>
{/if}

<style>
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1000;
  }
  
  .modal-content {
    background-color: white;
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    width: 90%;
    max-width: 600px;
    max-height: 80vh;
    overflow-y: auto;
    position: relative;
  }
  
  .close-btn {
    position: absolute;
    top: 10px;
    right: 15px;
    background: none;
    border: none;
    font-size: 28px;
    cursor: pointer;
    color: #333;
  }
  
  .close-btn:hover {
    color: #000;
  }
  
  h2 {
    margin: 20px 20px 0 20px;
    color: #333;
  }
  
  .map-container {
    width: 100%;
    height: 300px;
    margin: 20px 0;
  }
</style>
