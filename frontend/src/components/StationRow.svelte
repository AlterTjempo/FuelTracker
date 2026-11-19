<script>
  // One station row, used by every station list so they look and behave the same:
  // the name opens the station details, "Route" opens directions.
  import { createEventDispatcher } from 'svelte'
  import { eur3, routeUrl } from '../lib/format.js'

  export let rank = null
  export let name = ''
  export let brand = ''
  export let city = ''
  export let meta = ''
  export let price = null
  export let closed = false
  export let highlight = false
  export let lat = null
  export let lon = null
  export let route = true

  const dispatch = createEventDispatcher()
  $: sub = [brand, city].filter(Boolean).join(' · ')
</script>

<div class="row" class:highlight>
  {#if rank !== null}<span class="rank">{rank}</span>{/if}
  <div class="info">
    <button class="name" on:click={() => dispatch('open')} title="Show station details">
      {name}
    </button>
    {#if closed}<span class="closed">Closed</span>{/if}
    {#if sub || meta}
      <div class="sub">
        {sub}{#if sub && meta}<span class="sep">·</span>{/if}{#if meta}<span class="meta">{meta}</span>{/if}
      </div>
    {/if}
  </div>
  <span class="price">{eur3(price)}</span>
  {#if route}
    <a class="route" href={routeUrl({ lat, lon, name, city })} target="_blank" rel="noopener noreferrer"
      title="Directions to {name}">Route</a>
  {/if}
  <slot />
</div>

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.6rem 0.25rem;
    border-bottom: 1px solid #21262d;
    min-height: 3.25rem;
  }

  .row.highlight {
    background: rgba(59, 130, 246, 0.08);
    border-radius: 6px;
    border-bottom-color: transparent;
    padding-left: 0.5rem;
    padding-right: 0.5rem;
  }

  .rank {
    width: 1.5rem;
    flex-shrink: 0;
    text-align: center;
    color: #6e7681;
    font-size: 0.8rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .highlight .rank {
    color: #58a6ff;
  }

  .info {
    flex: 1;
    min-width: 0;
  }

  .name {
    background: none;
    border: none;
    padding: 0;
    min-height: 0;
    color: #e6edf3;
    font-weight: 600;
    font-size: 0.9rem;
    text-align: left;
    cursor: pointer;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    display: inline-block;
    vertical-align: middle;
  }

  .name:hover {
    color: #58a6ff;
    text-decoration: underline;
    background: none;
  }

  .closed {
    font-size: 0.62rem;
    font-weight: 700;
    text-transform: uppercase;
    color: #f87171;
    border: 1px solid rgba(248, 113, 113, 0.5);
    border-radius: 3px;
    padding: 0 0.3rem;
    margin-left: 0.35rem;
    vertical-align: middle;
  }

  .sub {
    color: #8b949e;
    font-size: 0.75rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .sep {
    margin: 0 0.3rem;
  }

  .meta {
    color: #6e7681;
  }

  .price {
    font-size: 1.05rem;
    font-weight: 700;
    color: #e6edf3;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .highlight .price {
    color: #58a6ff;
  }

  .route {
    flex-shrink: 0;
    font-size: 0.78rem;
    font-weight: 600;
    color: #58a6ff;
    text-decoration: none;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 0.45rem 0.6rem;
    touch-action: manipulation;
  }

  .route:hover {
    border-color: #58a6ff;
    background: rgba(88, 166, 255, 0.08);
  }

  @media (min-width: 640px) {
    .row {
      gap: 0.85rem;
      padding: 0.65rem 0.5rem;
    }
    .name {
      font-size: 0.95rem;
    }
    .price {
      font-size: 1.15rem;
    }
  }
</style>
