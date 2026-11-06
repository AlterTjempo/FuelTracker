<script>
  import { onMount } from 'svelte'
  import API_BASE, { safeFetch, getSavings, addRefuel, deleteRefuel } from '../lib/api.js'

  export let selectedFuelType = 'e5'

  let data = null
  let loading = true
  let loadError = ''
  let stations = []

  // form
  let fuelType = ['e5', 'e10', 'diesel'].includes(selectedFuelType) ? selectedFuelType : 'e5'
  let liters = ''
  let price = ''
  let when = localNowValue()
  let stationId = ''
  let saving = false
  let formError = ''

  function localNowValue() {
    const d = new Date()
    d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
    return d.toISOString().slice(0, 16)
  }

  function parseError(err) {
    try {
      const parsed = JSON.parse(err.message.replace(/^HTTP \d+: /, ''))
      if (Array.isArray(parsed.detail)) return parsed.detail.map((d) => d.msg).join('; ')
      return parsed.detail || err.message
    } catch {
      return err.message
    }
  }

  async function load() {
    try {
      data = await getSavings()
      loadError = ''
    } catch (e) {
      loadError = parseError(e)
    } finally {
      loading = false
    }
  }

  async function loadStations() {
    try {
      const rows = await safeFetch(`${API_BASE}/stations/?limit=1000`)
      stations = rows.sort((a, b) => (a.city || '').localeCompare(b.city || '') || a.name.localeCompare(b.name))
    } catch { /* station is optional */ }
  }

  async function submit() {
    formError = ''
    const l = parseFloat(String(liters).replace(',', '.'))
    const p = parseFloat(String(price).replace(',', '.'))
    if (!(l > 0 && l <= 200)) { formError = 'Enter litres between 0 and 200'; return }
    if (!(p >= 0.5 && p <= 5)) { formError = 'Enter the price per litre in € (e.g. 1.899)'; return }
    saving = true
    try {
      await addRefuel({
        fuel_type: fuelType,
        liters: l,
        price_per_liter: p,
        fueled_at: new Date(when).toISOString(),
        station_id: stationId || null,
      })
      liters = ''
      price = ''
      when = localNowValue()
      await load()
    } catch (e) {
      formError = parseError(e)
    } finally {
      saving = false
    }
  }

  async function remove(id) {
    if (!confirm('Delete this refuel?')) return
    try {
      await deleteRefuel(id)
      await load()
    } catch (e) {
      loadError = parseError(e)
    }
  }

  onMount(() => {
    load()
    loadStations()
  })

  const eur = (n) => `€${n.toFixed(2)}`
  const fmtWhen = (iso) =>
    new Date(iso).toLocaleString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
      timeZone: 'Europe/Berlin',
    })
</script>

<div class="savings">
  <h2>💰 Your Fuel Statistics</h2>

  {#if loading}
    <div class="state">Loading…</div>
  {:else if loadError}
    <div class="state error">{loadError}</div>
  {:else if data}
    <div class="tiles">
      <div class="tile"><span class="v">{data.summary.sessions}</span><span class="l">refuelling sessions</span></div>
      <div class="tile"><span class="v">{data.summary.liters.toLocaleString('en-GB')} L</span><span class="l">purchased</span></div>
      <div class="tile"><span class="v">{eur(data.summary.total_spent)}</span><span class="l">spent</span></div>
      <div class="tile highlight" class:neg={data.summary.saved < 0}>
        <span class="v">{data.summary.saved < 0 ? '−' : ''}{eur(Math.abs(data.summary.saved))}</span>
        <span class="l">{data.summary.saved < 0 ? 'above area average' : 'saved vs. area average'}</span>
      </div>
    </div>
    <p class="method">
      {data.method}
      {#if data.summary.sessions_without_reference > 0}
        <strong>{data.summary.sessions_without_reference}</strong> session(s) had no price data around that time and are not counted.
      {/if}
    </p>
  {/if}

  <form on:submit|preventDefault={submit}>
    <h3>Log a refuel</h3>
    <div class="row">
      <label>Fuel
        <select bind:value={fuelType}>
          <option value="e5">E5</option>
          <option value="e10">E10</option>
          <option value="diesel">Diesel</option>
        </select>
      </label>
      <label>Litres
        <input type="text" inputmode="decimal" placeholder="e.g. 38.5" bind:value={liters} />
      </label>
      <label>Price per litre (€)
        <input type="text" inputmode="decimal" placeholder="e.g. 1.899" bind:value={price} />
      </label>
      <label>When
        <input type="datetime-local" bind:value={when} max={localNowValue()} />
      </label>
      <label class="wide">Station (optional)
        <select bind:value={stationId}>
          <option value="">–</option>
          {#each stations as s}
            <option value={s.id}>{s.city ? s.city + ' – ' : ''}{s.name}</option>
          {/each}
        </select>
      </label>
    </div>
    {#if formError}<div class="form-error">{formError}</div>{/if}
    <button class="primary" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Add refuel'}</button>
  </form>

  {#if data && data.sessions.length > 0}
    <h3>Recent refuels</h3>
    <ul class="list">
      {#each data.sessions as s (s.id)}
        <li>
          <div class="main">
            <strong>{s.liters} L {s.fuel_type.toUpperCase()}</strong>
            <span>@ €{s.price_per_liter.toFixed(3)} = {eur(s.total_cost)}</span>
          </div>
          <div class="sub">
            {fmtWhen(s.fueled_at)}{s.station_name ? ' · ' + s.station_name : ''}
          </div>
          <div class="result" class:neg={s.saved !== null && s.saved < 0}>
            {#if s.saved === null}
              <span class="muted">no reference price for this time</span>
            {:else}
              {s.saved >= 0 ? 'Saved ' : 'Paid '}{eur(Math.abs(s.saved))}
              <span class="muted">(area avg €{s.reference_price.toFixed(3)})</span>
            {/if}
          </div>
          <button class="del" on:click={() => remove(s.id)} aria-label="Delete refuel">✕</button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  h2 { margin: 0 0 0.75rem; }
  h3 { margin: 1.25rem 0 0.5rem; font-size: 1rem; color: #c9d1d9; }
  .state { color: #8b949e; padding: 1rem; text-align: center; }
  .state.error { color: #f85149; }
  .tiles { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.625rem; }
  .tile { background: #1c2128; border: 1px solid #30363d; border-radius: 6px; padding: 0.75rem; display: flex; flex-direction: column; }
  .tile .v { font-size: 1.4rem; font-weight: 700; color: #e6edf3; }
  .tile .l { font-size: 0.8rem; color: #8b949e; }
  .tile.highlight { border-color: #10b981; }
  .tile.highlight .v { color: #10b981; }
  .tile.highlight.neg { border-color: #f59e0b; }
  .tile.highlight.neg .v { color: #f59e0b; }
  .method { color: #8b949e; font-size: 0.8rem; line-height: 1.5; margin: 0.75rem 0 0; }

  form { margin-top: 0.5rem; }
  .row { display: grid; grid-template-columns: 1fr; gap: 0.625rem; margin-bottom: 0.75rem; }
  label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.8rem; color: #8b949e; font-weight: 600; margin: 0; }
  input, select {
    background: #0f1419; border: 1px solid #30363d; color: #e6edf3; border-radius: 6px;
    padding: 0.5rem 0.625rem; font-size: 1rem; min-height: 2.5rem; font-family: inherit;
  }
  input:focus, select:focus { outline: 2px solid #3b82f6; outline-offset: 1px; }
  .form-error { color: #f85149; font-size: 0.85rem; margin-bottom: 0.5rem; }
  .primary { background: #3b82f6; border-color: #3b82f6; color: #fff; }
  .primary:hover { background: #2563eb; }
  .primary:disabled { opacity: 0.6; cursor: default; }

  .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.5rem; }
  .list li {
    position: relative; background: #1c2128; border: 1px solid #30363d; border-radius: 6px;
    padding: 0.625rem 2.5rem 0.625rem 0.75rem; display: flex; flex-direction: column; gap: 0.125rem;
  }
  .main { display: flex; flex-wrap: wrap; gap: 0.5rem; color: #e6edf3; }
  .main span { color: #8b949e; }
  .sub { font-size: 0.8rem; color: #8b949e; }
  .result { font-size: 0.9rem; color: #10b981; font-weight: 600; }
  .result.neg { color: #f59e0b; }
  .muted { color: #8b949e; font-weight: 400; font-size: 0.8rem; }
  .del {
    position: absolute; top: 0.375rem; right: 0.375rem; min-height: 2rem; width: 2rem; padding: 0;
    background: transparent; border-color: transparent; color: #8b949e;
  }
  .del:hover { color: #f85149; border-color: #30363d; }

  @media (min-width: 640px) {
    .tiles { grid-template-columns: repeat(4, 1fr); }
    .row { grid-template-columns: repeat(4, 1fr); }
    .wide { grid-column: 1 / -1; }
  }
</style>
