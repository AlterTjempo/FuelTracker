<script>
  import { onMount } from 'svelte'
  import { getForecast, getMarketContext, getTrend } from '../lib/api.js'
  import TrendChart from './TrendChart.svelte'

  export let fuelType = 'e5'

  let forecast = null
  let market = null
  let trend = null
  let loading = true
  let error = false
  let loadedFor = ''

  async function load() {
    const key = fuelType
    loading = true
    error = false
    try {
      const [f, m, t] = await Promise.all([getForecast(key), getMarketContext(key), getTrend(key)])
      if (key !== fuelType) return
      forecast = f
      market = m
      trend = t
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
    const iv = setInterval(() => { if (!document.hidden) load() }, 10 * 60 * 1000)
    return () => clearInterval(iv)
  })

  // ---------- formatting helpers ----------
  const todayIso = new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Berlin' })
  const dayLong = (iso) =>
    new Date(iso + 'T12:00:00').toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short' })
  const dayShort = (iso) =>
    new Date(iso + 'T12:00:00').toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })
  const eur3 = (n) => `€${n.toFixed(3)}`
  const hourLabel = (h) => (h === null || h === undefined ? '–' : `${String(h).padStart(2, '0')}:00`)
  const signed = (n, digits = 1) => `${n > 0 ? '+' : n < 0 ? '−' : '±'}${Math.abs(n).toFixed(digits)}`
  const cents = (n, digits = 1) => `${signed(n, digits)}¢/L`
  const pct = (n) => `${n > 0 ? '+' : ''}${n.toFixed(1)}%`
  const ago = (iso) => {
    const h = Math.round((Date.now() - new Date(iso).getTime()) / 3600000)
    return h < 1 ? 'just now' : h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`
  }

  const MODEL_NAMES = {
    persistence: 'No change (baseline)',
    weekday: 'Weekday pattern',
    momentum: 'Price momentum',
    price: 'Momentum + weekday',
    momentum_oil: 'Momentum + Brent',
    momentum_oil_news: 'Momentum + Brent + news',
  }

  // ---------- prediction summary ----------
  $: futureHorizons = trend && !trend.insufficient_data
    ? trend.horizons.filter((h) => h.date >= todayIso)
    : []
  $: headline = futureHorizons.length ? futureHorizons[futureHorizons.length - 1] : null
  $: anyModel = trend && !trend.insufficient_data && trend.any_model_beats_baseline
  $: baselineMae = trend?.horizons?.length ? trend.horizons[0].baseline_mae_cents : null

  // Reliability comes from the backend and is based on out-of-sample metrics
  // (skill vs. baseline, Diebold-Mariano test, band calibration).
  const TONES = { High: 'high', Medium: 'mid', Low: 'low' }
  // When no model beats "unchanged", that is a finding, not a fault: show it neutrally
  // ("No clear trend") instead of an amber "Reliability: Low" that reads like an error.
  $: reliability = headline?.reliability
    ? headline.beats_baseline
      ? { level: headline.reliability.level, label: 'Reliability: ' + headline.reliability.level, tone: TONES[headline.reliability.level] || 'low', note: headline.reliability.why }
      : { level: 'none', label: 'No clear trend', tone: 'flat', note: 'No model predicted prices better than "unchanged" on past data' }
    : null

  // One extra line only when the probability model passed validation (calibration + Brier skill).
  $: probLine = (() => {
    const hs = trend?.probability?.horizons?.filter((h) => h.validated && h.probability !== null) || []
    if (!hs.length) return ''
    const h = hs[0]
    return `${Math.round(h.probability * 100)}% chance of a rise of more than ${trend.probability.x_cents} cent in the next ${h.hours} h`
  })()

  const VERDICT = {
    flat: { icon: '→', text: 'No significant change expected', tone: 'flat' },
    rising: { icon: '↗', text: 'Prices are expected to rise', tone: 'up' },
    falling: { icon: '↘', text: 'Prices are expected to fall', tone: 'down' },
  }
  $: verdict = headline ? VERDICT[headline.direction] : null

  // ---------- best time to refuel ----------
  $: forecastOk = forecast && !forecast.insufficient_data
  // The hour pattern (pooled over all weekdays) is the headline; weekdays are secondary.
  $: bestHour = forecastOk ? forecast.hour_pattern?.best_hour ?? null : null
  $: worstHour = forecastOk ? forecast.hour_pattern?.worst_hour ?? null : null
  $: hourSpread = forecastOk ? forecast.hour_pattern?.spread_cents ?? forecast.hour_spread_cents : null

  // Brands differ in the size (not the timing) of the noon jump: show the range, one line.
  $: brandRange = (() => {
    const b = forecast?.brand_patterns
    if (!b?.brands_differ) return null
    const gs = b.groups.filter((g) => g.jump_cents !== null)
    if (gs.length < 2) return null
    const sorted = [...gs].sort((x, y) => x.jump_cents - y.jump_cents)
    return { min: sorted[0], max: sorted[sorted.length - 1] }
  })()

  function remainingBest(profile) {
    const nowH = Number(new Date().toLocaleString('en-GB', { hour: '2-digit', hour12: false, timeZone: 'Europe/Berlin' }))
    const entries = Object.entries(profile || {})
      .map(([h, v]) => [Number(h), v])
      .filter(([h]) => h >= nowH)
    if (!entries.length) return null
    entries.sort((a, b) => a[1] - b[1])
    return entries[0][0]
  }
  $: todayBest = forecastOk ? remainingBest(forecast.hour_pattern?.profile_cents) : null

  $: maxAbsOffset = forecastOk ? Math.max(0.5, ...forecast.forecast.map((d) => Math.abs(d.offset_cents))) : 1

  // ---------- market indicators ----------
  $: brentDays = trend?.oil_days ?? market?.oil_days ?? 0
  $: brentEnough = brentDays >= 20
  function outlookText(m) {
    if (!m) return ''
    if (m.outlook === 'upward_pressure')
      return 'Crude has risen recently and, in our data, pump prices have tended to follow: mild upward pressure.'
    if (m.outlook === 'downward_pressure')
      return 'Crude has fallen recently and, in our data, pump prices have tended to follow: mild downward pressure.'
    return 'No reliable signal from oil right now.'
  }
</script>

<div class="outlook">
  {#if loading && !trend}
    <div class="panel state">Loading outlook…</div>
  {:else if error && !trend}
    <div class="panel state">Couldn't load the outlook. Please try again in a moment.</div>
  {:else}
    <!-- 1. PREDICTION SUMMARY -->
    <section class="panel hero" aria-labelledby="hero-h">
      {#if !trend || trend.insufficient_data}
        <h2 id="hero-h">Price outlook</h2>
        <p class="muted">{trend?.reason || 'Not enough data for a price outlook yet.'}</p>
      {:else if !headline}
        <h2 id="hero-h">Price outlook</h2>
        <p class="muted">
          The latest complete day of data ({dayLong(trend.origin_date)}) is too far back to forecast
          the coming days. Forecasts resume once recent data has been collected.
        </p>
      {:else}
        <div class="hero-grid">
          <div class="hero-price">
            <span class="eyebrow" id="hero-h">Area-average {fuelType.toUpperCase()} price</span>
            <span class="big">{eur3(trend.latest_price)}<small>/L</small></span>
            <span class="sub">latest known · {dayLong(trend.origin_date)}</span>
          </div>

          <div class="hero-verdict" data-tone={verdict.tone}>
            <div class="verdict-line">
              <span class="verdict-icon" aria-hidden="true">{verdict.icon}</span>
              <span class="verdict-text">{verdict.text}</span>
            </div>
            <div class="verdict-numbers">
              <div>
                <span class="num">{eur3(headline.expected_price)}<small>/L</small></span>
                <span class="sub">expected {dayLong(headline.date)}</span>
              </div>
              <div>
                <span class="num">{cents(headline.expected_change_cents)}</span>
                <span class="sub">expected change · typical error ±{headline.interval_cents}¢/L</span>
              </div>
            </div>
          </div>
        </div>

        <div class="hero-foot">
          <span class="badge" data-tone={reliability.tone} title={reliability.note}>{reliability.label}</span>
          <span class="explain">
            {#if headline.beats_baseline}
              {reliability.note}.
              {#if headline.drivers?.length}Driven mainly by {headline.drivers.map((d) => d.feature).join(', ')}.{/if}
            {:else}
              Pump prices have been moving within normal day-to-day noise{#if baselineMae !== null}{' '}(about ±{baselineMae}¢/L per day){/if},
              and no model has predicted them better than "unchanged". The page therefore does not
              invent a trend. The reliable pattern is the time of day (see below).
            {/if}
            {#if probLine}<strong class="prob">{probLine}.</strong>{/if}
          </span>
        </div>
      {/if}
    </section>

    <!-- 2. PRICE DEVELOPMENT CHART -->
    {#if trend && !trend.insufficient_data && trend.history?.length > 1}
      <section class="panel" aria-labelledby="chart-h">
        <h3 id="chart-h">Price development</h3>
        <TrendChart
          history={trend.history}
          horizons={futureHorizons.length ? trend.horizons : []}
          originDate={trend.origin_date}
          originPrice={trend.latest_price}
        />
        <p class="caption">
          Solid: real daily average of all tracked stations (gaps are missing data, not flat prices).
          {#if futureHorizons.length}
            {#if anyModel}
              Dashed: model forecast with its 80% range.
            {:else}
              Dashed: the "no change" baseline. The band is the typical error of that baseline, not a predicted move.
            {/if}
          {/if}
        </p>
      </section>
    {/if}

    <!-- 3. BEST TIME TO REFUEL -->
    <section class="panel" aria-labelledby="best-h">
      <h3 id="best-h">Best time to refuel</h3>
      {#if !forecastOk}
        <p class="muted">
          Not enough history yet for a weekday/hour pattern. We need at least
          {forecast?.min_samples_per_weekday ?? 3} well-covered days for every weekday
          (currently {forecast?.days_used ?? 0} usable days).
        </p>
      {:else}
        <div class="tiles three">
          <div class="tile good">
            <span class="tile-label">Cheapest hour</span>
            <span class="tile-value">{hourLabel(bestHour)}</span>
            {#if todayBest !== null && todayBest !== bestHour}
              <span class="tile-sub">today, from now: {hourLabel(todayBest)}</span>
            {/if}
          </div>
          <div class="tile warn">
            <span class="tile-label">Priciest hour</span>
            <span class="tile-value">{hourLabel(worstHour)}</span>
          </div>
          <div class="tile">
            <span class="tile-label">Typical difference</span>
            <span class="tile-value">~{hourSpread}<small>¢/L</small></span>
            {#if brandRange}
              <span class="tile-sub">{brandRange.min.jump_cents}¢ at {brandRange.min.group} to {brandRange.max.jump_cents}¢ at {brandRange.max.group}</span>
            {/if}
          </div>
        </div>
        <p class="caption">
          Hour pattern from {forecast.days_used} days of data (confidence: <strong>{forecast.confidence}</strong>; recent weeks weigh more).
          Weekdays are only shown when they clear their standard error and 0.3¢.
        </p>

        {#if forecast.significant_weekdays > 0}
          <details class="fold inner">
            <summary>Weekday differences</summary>
            <ul class="week">
              {#each forecast.forecast as day, i}
                <li class:today={i === 0}>
                  <span class="w-day">{i === 0 ? 'Today' : day.weekday.slice(0, 3)} <em>{dayShort(day.date)}</em></span>
                  <span class="w-bar" aria-hidden="true">
                    <span class="w-axis"></span>
                    <span
                      class="w-fill"
                      class:neg={day.offset_cents < 0}
                      class:muted={day.label === 'average'}
                      style="width: {(Math.abs(day.offset_cents) / maxAbsOffset) * 50}%; {day.offset_cents < 0 ? 'right: 50%' : 'left: 50%'}"
                    ></span>
                  </span>
                  <span class="w-val" class:good={day.label === 'cheaper'} class:warnc={day.label === 'pricier'}>{cents(day.offset_cents)}</span>
                  <span class="w-hour">{day.label === 'cheaper' ? 'cheaper than usual' : day.label === 'pricier' ? 'pricier than usual' : 'about average'}</span>
                </li>
              {/each}
            </ul>
            <p class="caption">±{forecast.forecast[0].uncertainty_cents}¢/L typical uncertainty per weekday. {forecast.disclaimer}</p>
          </details>
        {/if}
      {/if}
    </section>

    <!-- 4. WHY THIS PREDICTION -->
    <details class="fold panel">
      <summary><span>Why this prediction?</span></summary>
      <p class="lead">
        The model compares recent price momentum, distance from the 28-day average and the weekday
        with Brent crude and keyword-scored news. It only uses an input if that input improves
        predictions on data it has not seen.
      </p>

      <h4>Data it uses</h4>
      <ul class="sources">
        <li>
          <span>Pump price history</span>
          <span class="chip" data-tone={trend && trend.days_used >= 60 ? 'ok' : 'warn'}>
            {trend ? `${trend.days_used} days` : '–'}
          </span>
        </li>
        <li>
          <span>Brent crude oil</span>
          <span class="chip" data-tone={brentEnough ? 'ok' : 'warn'}>
            {brentEnough ? `${brentDays} days` : `only ${brentDays} days: not enough yet`}
          </span>
        </li>
        <li>
          <span>Energy news</span>
          <span class="chip" data-tone={trend?.news_days > 0 ? 'ok' : 'na'}>
            {trend?.news_days > 0 ? `${trend.news_days} days with articles` : 'no data'}
          </span>
        </li>
      </ul>

      {#if market}
        <h4>Market indicators</h4>
        <div class="tiles three">
          <div class="tile" class:na={!market.oil_7d}>
            <span class="tile-label">Brent, 7 days</span>
            {#if market.oil_7d}
              <span class="tile-value">{pct(market.oil_7d.change_pct)}</span>
            {:else}
              <span class="tile-na">Not enough data</span>
              <span class="tile-sub">{brentDays} days of Brent history</span>
            {/if}
          </div>
          <div class="tile" class:na={!market.fuel_7d}>
            <span class="tile-label">Pump price, 7 days</span>
            {#if market.fuel_7d}
              <span class="tile-value">{pct(market.fuel_7d.change_pct)}</span>
            {:else}
              <span class="tile-na">No recent data</span>
            {/if}
          </div>
          <div class="tile" class:na={!market.lag_relationship.best}>
            <span class="tile-label">Oil → pump link</span>
            {#if market.lag_relationship.best}
              <span class="tile-value">r = {market.lag_relationship.best.correlation}</span>
              <span class="tile-sub">
                best lag {market.lag_relationship.best.lag_days} d · {market.lag_relationship.best.pairs} days ·
                {market.lag_relationship.reliable ? 'meaningful' : 'weak'}
              </span>
            {:else}
              <span class="tile-na">Not enough data</span>
              <span class="tile-sub">needs ≥ 20 days of both series</span>
            {/if}
          </div>
        </div>
        <p class="lead">{outlookText(market)}</p>
      {/if}
    </details>

    <!-- 5. MODEL RELIABILITY -->
    {#if trend && !trend.insufficient_data}
      <details class="fold panel">
        <summary><span>Model reliability &amp; validation</span></summary>
        <p class="lead">
          Each model is tested the way it would have been used: for every past day it is trained only
          on what was known then and asked to predict ahead. The "no change" baseline is the bar to beat.
        </p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Ahead</th><th>Model used</th><th>Typical error</th><th>Baseline error</th><th>Improvement</th><th>Significance (p)</th><th>80% band hit</th><th>Tested days</th></tr>
            </thead>
            <tbody>
              {#each trend.horizons as h}
                <tr>
                  <td>+{h.h} d</td>
                  <td>{MODEL_NAMES[h.model] || h.model}</td>
                  <td>{h.mae_cents !== null ? `${h.mae_cents}¢/L` : '–'}</td>
                  <td>{h.baseline_mae_cents !== null ? `${h.baseline_mae_cents}¢/L` : '–'}</td>
                  <td>
                    {#if h.skill_vs_persistence === null}–
                    {:else}{h.skill_vs_persistence > 0 ? '+' : '−'}{Math.abs(Math.round(h.skill_vs_persistence * 100))}%{h.beats_baseline ? '' : ' (not used)'}{/if}
                  </td>
                  <td>{h.dm_p_eval ?? '–'}</td>
                  <td>{h.coverage80 !== undefined ? Math.round(h.coverage80 * 100) + '%' : '–'}</td>
                  <td>{h.n_test}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        <p class="caption">
          Improvement = how much smaller the model's error is than the baseline's, on the second half of
          the backtest (the half not used to choose the model). Negative means the model was worse, so the
          baseline is shown instead. Trained on {trend.days_used} days of prices
          ({trend.oil_days} with Brent, {trend.news_days} with news).
        </p>
        <p class="caption">{trend.method} {trend.disclaimer}</p>
      </details>
    {/if}

    <!-- 6. NEWS -->
    {#if market}
      <details class="fold panel">
        <summary><span>Relevant market news <em>({market.news.length})</em></span></summary>
        {#if market.news.length === 0}
          <p class="muted">No articles in the last 72 hours matched supply-related topics.</p>
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
        <p class="caption">{market.disclaimer}</p>
      </details>
    {/if}
  {/if}
</div>

<style>
  .panel {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
  }
  .state { color: #8b949e; text-align: center; padding: 2rem 1rem; }
  h2, h3 { margin: 0 0 0.75rem; color: #e6edf3; }
  h3 { font-size: 1.05rem; }
  h4 { margin: 1.1rem 0 0.5rem; font-size: 0.8rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.05em; }
  .muted { color: #8b949e; }
  p.muted { font-size: 0.9rem; line-height: 1.5; margin: 0; }
  .lead { color: #c9d1d9; font-size: 0.9rem; line-height: 1.55; margin: 0 0 0.75rem; }
  .caption { color: #8b949e; font-size: 0.78rem; line-height: 1.5; margin: 0.75rem 0 0; }
  small { font-size: 0.55em; font-weight: 500; color: #8b949e; margin-left: 0.1em; }

  /* hero */
  .hero { padding: 1.25rem; }
  .hero-grid { display: grid; grid-template-columns: 1fr; gap: 1.25rem; }
  .hero-price, .hero-verdict > .verdict-numbers > div { display: flex; flex-direction: column; gap: 0.125rem; }
  .eyebrow { color: #8b949e; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
  .big { font-size: 2.6rem; font-weight: 700; color: #e6edf3; line-height: 1.1; }
  .sub { color: #8b949e; font-size: 0.78rem; }
  .verdict-line { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.75rem; }
  .verdict-icon {
    display: inline-flex; align-items: center; justify-content: center;
    width: 2.25rem; height: 2.25rem; border-radius: 50%; font-size: 1.3rem; font-weight: 700;
    background: #21262d; color: #8b949e;
  }
  .verdict-text { font-size: 1.2rem; font-weight: 600; color: #e6edf3; }
  [data-tone='up'] .verdict-icon { background: rgba(245,158,11,0.15); color: #f59e0b; }
  [data-tone='down'] .verdict-icon { background: rgba(16,185,129,0.15); color: #10b981; }
  .verdict-numbers { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
  .num { font-size: 1.25rem; font-weight: 700; color: #e6edf3; }
  .hero-foot {
    display: flex; flex-direction: column; gap: 0.5rem; margin-top: 1.1rem; padding-top: 1rem;
    border-top: 1px solid #30363d;
  }
  .badge {
    align-self: flex-start; font-size: 0.78rem; font-weight: 600; padding: 0.2rem 0.6rem;
    border-radius: 999px; border: 1px solid #30363d; color: #8b949e; background: #1c2128;
  }
  .badge[data-tone='high'] { color: #10b981; border-color: rgba(16,185,129,0.5); }
  .badge[data-tone='mid'] { color: #58a6ff; border-color: rgba(88,166,255,0.5); }
  .badge[data-tone='flat'] { color: #8b949e; border-color: #30363d; }
  .badge[data-tone='low'] { color: #f59e0b; border-color: rgba(245,158,11,0.45); }
  .prob { display: block; margin-top: 0.25rem; color: #e6edf3; }
  .explain { color: #c9d1d9; font-size: 0.88rem; line-height: 1.5; }

  /* tiles */
  .tiles { display: grid; grid-template-columns: 1fr; gap: 0.625rem; }
  .tile {
    background: #1c2128; border: 1px solid #30363d; border-radius: 6px; padding: 0.7rem 0.8rem;
    display: flex; flex-direction: column; gap: 0.125rem;
  }
  .tile.good { border-left: 3px solid #10b981; }
  .tile.warn { border-left: 3px solid #f59e0b; }
  .tile-label { color: #8b949e; font-size: 0.78rem; }
  .tile-value { font-size: 1.35rem; font-weight: 700; color: #e6edf3; }
  .tile-sub { color: #8b949e; font-size: 0.75rem; }
  .tile-na { color: #6e7681; font-size: 0.95rem; font-style: italic; padding: 0.25rem 0; }
  .tile.na { background: transparent; border-style: dashed; }

  /* 7-day list */
  .week { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
  .week li {
    display: grid; grid-template-columns: 5.5rem 1fr 4.2rem; grid-template-areas: 'day bar val' 'day hour hour';
    align-items: center; gap: 0.1rem 0.6rem; padding: 0.5rem 0.25rem; border-bottom: 1px solid #21262d; font-size: 0.88rem;
  }
  .week li:last-child { border-bottom: none; }
  .week li.today { background: rgba(59,130,246,0.07); border-radius: 6px; }
  .w-day { grid-area: day; color: #e6edf3; font-weight: 600; }
  .w-day em { display: block; font-style: normal; color: #8b949e; font-weight: 400; font-size: 0.75rem; }
  .w-bar { grid-area: bar; position: relative; height: 10px; }
  .w-axis { position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px; background: #30363d; }
  .w-fill { position: absolute; top: 1px; bottom: 1px; background: #f59e0b; border-radius: 2px; }
  .w-fill.neg { background: #10b981; }
  .w-fill.muted { background: #6b7280; }
  .w-val { grid-area: val; text-align: right; font-weight: 600; color: #c9d1d9; font-variant-numeric: tabular-nums; }
  .w-val.good { color: #10b981; }
  .w-val.warnc { color: #f59e0b; }
  .w-hour { grid-area: hour; color: #8b949e; font-size: 0.75rem; }

  /* collapsible sections */
  .fold > summary {
    cursor: pointer; list-style: none; font-weight: 600; color: #e6edf3; font-size: 1.02rem;
    display: flex; align-items: center; gap: 0.5rem; min-height: 1.75rem;
  }
  .fold > summary::-webkit-details-marker { display: none; }
  .fold > summary::before {
    content: '▸'; color: #8b949e; transition: transform 0.15s; display: inline-block; width: 1rem;
  }
  .fold[open] > summary::before { transform: rotate(90deg); }
  .fold > summary em { color: #8b949e; font-style: normal; font-weight: 400; }
  .fold[open] > summary { margin-bottom: 0.75rem; }
  .fold.inner { margin-top: 1rem; }
  .fold.inner > summary { font-size: 0.88rem; color: #58a6ff; font-weight: 500; }

  /* sources + chips */
  .sources { list-style: none; margin: 0 0 0.5rem; padding: 0; display: flex; flex-direction: column; gap: 0.4rem; }
  .sources li { display: flex; justify-content: space-between; gap: 0.75rem; align-items: center; font-size: 0.88rem; color: #c9d1d9; }
  .chip { font-size: 0.75rem; padding: 0.15rem 0.55rem; border-radius: 999px; border: 1px solid #30363d; color: #8b949e; text-align: right; }
  .chip[data-tone='ok'] { color: #10b981; border-color: rgba(16,185,129,0.4); }
  .chip[data-tone='warn'] { color: #f59e0b; border-color: rgba(245,158,11,0.4); }

  /* tables */
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  th { text-align: left; color: #8b949e; font-weight: 500; padding: 0.4rem 0.6rem; border-bottom: 1px solid #30363d; white-space: nowrap; }
  td { padding: 0.45rem 0.6rem; border-bottom: 1px solid #21262d; color: #c9d1d9; white-space: nowrap; }

  /* news */
  .news { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.7rem; }
  .news li { display: flex; flex-direction: column; gap: 0.125rem; }
  .news a { color: #58a6ff; text-decoration: none; line-height: 1.35; }
  .news a:hover { text-decoration: underline; }
  .meta { color: #8b949e; font-size: 0.75rem; }
  .kw { color: #6e7681; font-size: 0.7rem; }

  @media (min-width: 640px) {
    .panel { padding: 1.25rem; }
    .hero-grid { grid-template-columns: 1fr 1.6fr; align-items: center; }
    .hero-foot { flex-direction: row; align-items: center; gap: 0.9rem; }
    .tiles.three { grid-template-columns: repeat(3, 1fr); }
    .week li { grid-template-columns: 7rem 1fr 4.5rem 7.5rem; grid-template-areas: 'day bar val hour'; }
    .w-hour { text-align: right; }
    .w-day em { display: inline; margin-left: 0.35rem; }
  }
</style>
