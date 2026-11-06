<script>
  import { onMount } from 'svelte'
  import { getForecast, getMarketContext } from '../lib/api.js'

  export let fuelType = 'e5'

  let forecast = null
  let market = null
  let loading = true
  let error = false
  let loadedFor = ''

  async function load() {
    const key = fuelType
    loading = true
    error = false
    try {
      const [f, m] = await Promise.all([getForecast(key), getMarketContext(key)])
      if (key !== fuelType) return
      forecast = f
      market = m
    } catch (e) {
      console.error('Error loading outlook:', e)
      error = true
    } finally {
      loading = false
    }
  }

  $: if (fuelType !== loadedFor) {
    loadedFor = fuelType
    load()
  }

  onMount(() => {
    const iv = setInterval(load, 10 * 60 * 1000)
    return () => clearInterval(iv)
  })

  const LABELS = {
    cheaper: { text: 'Cheaper than usual', color: '#10b981' },
    average: { text: 'About average', color: '#6b7280' },
    pricier: { text: 'Pricier than usual', color: '#f59e0b' },
  }

  // Today: only hours that are still ahead are useful, so pick from those.
  function remainingBest(day) {
    const nowH = Number(new Date().toLocaleString('en-GB', { hour: '2-digit', hour12: false, timeZone: 'Europe/Berlin' }))
    const entries = Object.entries(day.hour_offsets_cents || {})
      .map(([h, v]) => [Number(h), v])
      .filter(([h]) => h >= nowH)
    if (entries.length === 0) return { best: null, worst: null }
    entries.sort((a, b) => a[1] - b[1])
    return { best: entries[0][0], worst: entries[entries.length - 1][0] }
  }

  const hourLabel = (h) => (h === null || h === undefined ? '–' : `${String(h).padStart(2, '0')}:00`)
  const sign = (n) => (n > 0 ? '+' : n < 0 ? '−' : '±')
  const fmtDate = (iso) =>
    new Date(iso + 'T12:00:00').toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })

  $: cheapestDay = forecast && !forecast.insufficient_data
    ? forecast.forecast.find((f) => f.rank === 1)
    : null

  function outlookText(m) {
    if (!m) return ''
    if (m.outlook === 'upward_pressure')
      return 'Crude has risen recently, and in our data pump prices have tended to follow. Mild upward pressure.'
    if (m.outlook === 'downward_pressure')
      return 'Crude has fallen recently, and in our data pump prices have tended to follow. Mild downward pressure.'
    return 'No reliable signal from oil right now.'
  }

  const pct = (n) => (n === null || n === undefined ? '–' : `${n > 0 ? '+' : ''}${n.toFixed(1)}%`)
  const ago = (iso) => {
    const h = Math.round((Date.now() - new Date(iso).getTime()) / 3600000)
    return h < 1 ? 'just now' : h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`
  }
</script>

<div class="outlook">
  {#if loading && !forecast}
    <div class="state">Loading outlook…</div>
  {:else if error && !forecast}
    <div class="state">Couldn't load the outlook. Please try again in a moment.</div>
  {:else if forecast}
    <section>
      <h2>📅 Next 7 days</h2>
      {#if forecast.insufficient_data}
        <div class="notice">
          Not enough history yet for a weekday pattern. We need at least
          {forecast.min_samples_per_weekday} well-covered days for every weekday
          (currently {forecast.days_used} usable days in total).
        </div>
      {:else}
        {#if cheapestDay}
          <p class="lead">
            Historically the cheapest day is <strong>{cheapestDay.weekday}</strong>
            and the cheapest hour is around <strong>{hourLabel(cheapestDay.best_hour)}</strong>.
          </p>
        {/if}
        <div class="calendar">
          {#each forecast.forecast as day, i}
            <div class="day" class:today={i === 0} style="--accent: {LABELS[day.label].color}">
              <div class="day-head">
                <span class="weekday">{i === 0 ? 'Today' : day.weekday.slice(0, 3)}</span>
                <span class="date">{fmtDate(day.date)}</span>
              </div>
              <div class="badge">{LABELS[day.label].text}</div>
              <div class="offset" title="Typical difference to the weekly average (± uncertainty)">
                {sign(day.offset_cents)}{Math.abs(day.offset_cents).toFixed(1)}¢
                <small>±{day.uncertainty_cents.toFixed(1)}</small>
              </div>
              <div class="hours">
                {#if i === 0}
                  {@const rest = remainingBest(day)}
                  <span>Cheapest hour left <strong>{hourLabel(rest.best)}</strong></span>
                  <span>Priciest hour left <strong>{hourLabel(rest.worst)}</strong></span>
                {:else}
                  <span>Cheapest hour <strong>{hourLabel(day.best_hour)}</strong></span>
                  <span>Priciest hour <strong>{hourLabel(day.worst_hour)}</strong></span>
                {/if}
              </div>
            </div>
          {/each}
        </div>
        <p class="footnote">
          Pattern confidence: <strong>{forecast.confidence}</strong>
          ({forecast.days_used} usable days, {forecast.first_day} → {forecast.last_day}).
          {#if forecast.recent_trend_cents_per_day !== null}
            Recent direction: {sign(forecast.recent_trend_cents_per_day)}{Math.abs(forecast.recent_trend_cents_per_day)}¢/day.
          {/if}
          {forecast.disclaimer}
        </p>
      {/if}
    </section>

    {#if market}
      <section>
        <h2>🛢️ Market context</h2>
        <div class="tiles">
          <div class="tile">
            <span class="tile-label">Brent, 7 days</span>
            <span class="tile-value">
              {#if market.oil_7d}{pct(market.oil_7d.change_pct)}{:else}–{/if}
            </span>
            {#if !market.oil_7d}<span class="tile-sub">not enough oil history</span>{/if}
          </div>
          <div class="tile">
            <span class="tile-label">Pump price, 7 days</span>
            <span class="tile-value">
              {#if market.fuel_7d}{pct(market.fuel_7d.change_pct)}{:else}–{/if}
            </span>
            {#if !market.fuel_7d}<span class="tile-sub">no recent data</span>{/if}
          </div>
          <div class="tile">
            <span class="tile-label">Oil → pump link</span>
            <span class="tile-value">
              {#if market.lag_relationship.best}
                r = {market.lag_relationship.best.correlation}
              {:else}–{/if}
            </span>
            <span class="tile-sub">
              {#if market.lag_relationship.best}
                best lag {market.lag_relationship.best.lag_days} d · {market.lag_relationship.best.pairs} days
                · {market.lag_relationship.reliable ? 'meaningful' : 'weak'}
              {:else}
                needs ≥ 20 days of both series
              {/if}
            </span>
          </div>
        </div>
        <p class="lead">{outlookText(market)}</p>

        <h3>Relevant news (last 72 h)</h3>
        {#if market.news.length === 0}
          <p class="muted">No articles matched supply-related topics.</p>
        {:else}
          <ul class="news">
            {#each market.news as n}
              <li>
                <a href={n.link} target="_blank" rel="noopener noreferrer">{n.title}</a>
                <span class="meta">{n.source} · {ago(n.published_at)}</span>
                <span class="kw">{n.keywords.slice(0, 4).join(' · ')}</span>
              </li>
            {/each}
          </ul>
        {/if}
        <p class="footnote">{market.disclaimer}</p>
      </section>
    {/if}
  {/if}
</div>

<style>
  section + section { margin-top: 1.5rem; padding-top: 1.25rem; border-top: 1px solid #30363d; }
  h2 { margin: 0 0 0.75rem; }
  h3 { margin: 1rem 0 0.5rem; font-size: 0.95rem; color: #c9d1d9; }
  .lead { color: #c9d1d9; margin: 0 0 1rem; line-height: 1.5; }
  .muted, .footnote { color: #8b949e; font-size: 0.8rem; line-height: 1.5; margin: 0.75rem 0 0; }
  .state, .notice {
    color: #8b949e; padding: 1.25rem; text-align: center;
    background: #1c2128; border: 1px solid #30363d; border-radius: 6px;
  }
  .notice { text-align: left; }

  .calendar { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.625rem; }
  .day {
    background: #1c2128; border: 1px solid #30363d; border-top: 3px solid var(--accent);
    border-radius: 6px; padding: 0.75rem; display: flex; flex-direction: column; gap: 0.375rem;
  }
  .day.today { box-shadow: 0 0 0 1px #3b82f6 inset; }
  .day-head { display: flex; justify-content: space-between; align-items: baseline; }
  .weekday { font-weight: 600; color: #e6edf3; }
  .date { color: #8b949e; font-size: 0.8rem; }
  .badge { color: var(--accent); font-size: 0.8rem; font-weight: 600; }
  .offset { font-size: 1.25rem; font-weight: 700; color: #e6edf3; }
  .offset small { font-size: 0.7rem; color: #8b949e; font-weight: 400; margin-left: 0.25rem; }
  .hours { display: flex; flex-direction: column; gap: 0.125rem; font-size: 0.75rem; color: #8b949e; }
  .hours strong { color: #c9d1d9; }

  .tiles { display: grid; grid-template-columns: 1fr; gap: 0.625rem; margin-bottom: 1rem; }
  .tile {
    background: #1c2128; border: 1px solid #30363d; border-radius: 6px; padding: 0.75rem;
    display: flex; flex-direction: column; gap: 0.125rem;
  }
  .tile-label { color: #8b949e; font-size: 0.8rem; }
  .tile-value { font-size: 1.35rem; font-weight: 700; color: #e6edf3; }
  .tile-sub { color: #8b949e; font-size: 0.75rem; }

  .news { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.625rem; }
  .news li { display: flex; flex-direction: column; gap: 0.125rem; }
  .news a { color: #58a6ff; text-decoration: none; line-height: 1.35; }
  .news a:hover { text-decoration: underline; }
  .meta { color: #8b949e; font-size: 0.75rem; }
  .kw { color: #6e7681; font-size: 0.7rem; }

  @media (min-width: 640px) {
    .calendar { grid-template-columns: repeat(4, 1fr); }
    .tiles { grid-template-columns: repeat(3, 1fr); }
  }
  @media (min-width: 1024px) {
    .calendar { grid-template-columns: repeat(7, 1fr); }
  }
</style>
