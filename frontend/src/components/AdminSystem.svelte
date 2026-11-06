<script>
  import { onMount } from 'svelte'
  import { getAdminSystem } from '../lib/api.js'

  let data = null
  let loading = true
  let error = ''

  async function load() {
    loading = true
    error = ''
    try {
      data = await getAdminSystem()
    } catch (e) {
      try { error = JSON.parse(e.message.replace(/^HTTP \d+: /, '')).detail || e.message } catch { error = e.message }
    } finally {
      loading = false
    }
  }

  onMount(() => {
    load()
    const iv = setInterval(() => { if (!document.hidden) load() }, 60000)
    return () => clearInterval(iv)
  })

  const fmtAge = (s) => {
    if (s === null || s === undefined) return 'never'
    if (s < 90) return 'just now'
    if (s < 5400) return `${Math.round(s / 60)} min ago`
    if (s < 172800) return `${Math.round(s / 3600)} h ago`
    return `${Math.round(s / 86400)} days ago`
  }
  const fmtBytes = (b) =>
    b >= 1e9 ? `${(b / 1e9).toFixed(2)} GB` : b >= 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.round(b / 1e3)} kB`
  const fmtNum = (n) => (n ?? 0).toLocaleString('en-GB')
  const fmtDateTime = (iso) =>
    iso ? new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : '–'
  const STATUS_TEXT = { ok: 'Healthy', warn: 'Getting stale', error: 'Stale / no data' }
  const cellColor = (c) =>
    c === 0 ? '#2a1f22' : c < 0.5 ? '#6b4b1f' : c < 0.9 ? '#2f6b4a' : '#1f9d63'

  $: fuel = data?.collectors.fuel
  $: warnings = data ? data.security_checks.filter((c) => !c.ok).length : 0
</script>

{#if loading && !data}
  <div class="card">Loading system overview…</div>
{:else if error}
  <div class="card err">{error}</div>
{:else if data}
  <div class="grid">
    {#each Object.values(data.collectors) as c}
      <div class="card collector" data-status={c.status}>
        <div class="row">
          <span class="dot" aria-hidden="true"></span>
          <span class="name">{c.label}</span>
        </div>
        <strong class="big">{STATUS_TEXT[c.status]}</strong>
        <span class="muted">Last data {fmtAge(c.age_seconds)}</span>
        <span class="muted">{fmtNum(c.rows_total)} rows total{#if c.rows_24h !== undefined} · {fmtNum(c.rows_24h)} in 24 h{/if}</span>
        {#if c.last_usd_per_barrel}<span class="muted">Brent ${c.last_usd_per_barrel.toFixed(2)}/bbl</span>{/if}
      </div>
    {/each}
  </div>

  <div class="card">
    <h3>Fuel price collection</h3>
    <div class="facts">
      <div><span class="muted">Cycles in last 24 h</span><strong>{fuel.cycles_24h} / {fuel.expected_cycles_24h}</strong></div>
      <div><span class="muted">Stations in latest cycle</span><strong>{fuel.stations_in_latest_cycle} of {fuel.stations_known}</strong></div>
      <div><span class="muted">First observation</span><strong>{fmtDateTime(fuel.first_observation)}</strong></div>
      <div><span class="muted">Days with data (last 60)</span><strong>{data.collection_summary.days_with_data} / 60</strong></div>
      <div><span class="muted">Avg. coverage on those days</span><strong>{Math.round(data.collection_summary.avg_coverage_on_days_with_data * 100)}%</strong></div>
    </div>
    <h4>Last 60 days (completed 15-minute cycles per day)</h4>
    <div class="strip" role="img" aria-label="Collection coverage per day for the last 60 days">
      {#each data.collection_history as d}
        <span class="cell" style="background: {cellColor(d.coverage)}" title="{d.date}: {d.cycles} of 96 cycles"></span>
      {/each}
    </div>
    <div class="legend">
      <span><i style="background:#2a1f22"></i>no data</span>
      <span><i style="background:#6b4b1f"></i>&lt; 50%</span>
      <span><i style="background:#2f6b4a"></i>50–90%</span>
      <span><i style="background:#1f9d63"></i>≥ 90%</span>
    </div>
    <p class="muted small">Missing days are real gaps (the app was not running or the API failed); they are never filled in.</p>
  </div>

  <div class="two">
    <div class="card">
      <h3>Scheduled jobs</h3>
      <ul class="list">
        {#each data.scheduler_jobs as j}
          <li>
            <span><strong>{j.id}</strong><br /><span class="muted small">{j.trigger}</span></span>
            <span class="muted">next {fmtDateTime(j.next_run)}</span>
          </li>
        {/each}
        {#if !data.scheduler_jobs.length}<li class="muted">No jobs reported.</li>{/if}
      </ul>

      {#if data.collectors.news.sources_7d?.length}
        <h4>News articles by source (7 days)</h4>
        <ul class="list">
          {#each data.collectors.news.sources_7d as s}
            <li><span>{s.source}</span><strong>{s.count}</strong></li>
          {/each}
        </ul>
      {/if}
    </div>

    <div class="card">
      <h3>Database · {fmtBytes(data.database.size_bytes)}</h3>
      <ul class="list">
        {#each data.database.tables as t}
          <li>
            <span>{t.table}</span>
            <span class="barwrap">
              <span class="bar" style="width: {Math.max(2, (t.bytes / data.database.tables[0].bytes) * 100)}%"></span>
            </span>
            <span class="muted num">{fmtBytes(t.bytes)}</span>
          </li>
        {/each}
      </ul>
    </div>
  </div>

  <div class="card">
    <h3>Security &amp; configuration {#if warnings}<span class="pill warn">{warnings} to review</span>{:else}<span class="pill ok">all good</span>{/if}</h3>
    <ul class="checks">
      {#each data.security_checks as c}
        <li class:bad={!c.ok}>
          <span class="mark" aria-hidden="true">{c.ok ? '✓' : '!'}</span>
          <span>
            {c.label}
            {#if !c.ok}<span class="muted small"><br />{c.detail}</span>{/if}
          </span>
        </li>
      {/each}
    </ul>
    <p class="muted small">Only on/off status is shown, never the secret values.</p>
  </div>
  <p class="muted small">Generated {fmtDateTime(data.generated_at)} · {data.cache_note}</p>
{/if}

<style>
  .card { background: #141d26; border: 1px solid #273341; border-radius: 14px; padding: 1rem; margin-bottom: 1rem; color: #d7e5f3; }
  .card.err { color: #ff8b83; border-color: #5b2b2f; background: #27181a; }
  h3 { margin: 0 0 0.75rem; font-size: 1.02rem; display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
  h4 { margin: 1rem 0 0.5rem; font-size: 0.78rem; color: #8aa0b6; text-transform: uppercase; letter-spacing: 0.05em; }
  .muted { color: #8aa0b6; }
  .small { font-size: 0.78rem; line-height: 1.45; }
  .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.9rem; margin-bottom: 1rem; }
  .collector { margin: 0; display: flex; flex-direction: column; gap: 0.2rem; border-left: 4px solid #6e7681; }
  .collector[data-status='ok'] { border-left-color: #1f9d63; }
  .collector[data-status='warn'] { border-left-color: #f59e0b; }
  .collector[data-status='error'] { border-left-color: #ff8b83; }
  .row { display: flex; align-items: center; gap: 0.5rem; }
  .dot { width: 0.6rem; height: 0.6rem; border-radius: 50%; background: #6e7681; }
  [data-status='ok'] .dot { background: #1f9d63; }
  [data-status='warn'] .dot { background: #f59e0b; }
  [data-status='error'] .dot { background: #ff8b83; }
  .name { color: #8aa0b6; font-size: 0.82rem; }
  .big { font-size: 1.15rem; }
  .facts { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.75rem; }
  .facts div { display: flex; flex-direction: column; gap: 0.1rem; }
  .strip { display: grid; grid-template-columns: repeat(30, 1fr); gap: 3px; }
  .cell { aspect-ratio: 1; border-radius: 3px; }
  .legend { display: flex; flex-wrap: wrap; gap: 0.9rem; margin-top: 0.5rem; font-size: 0.75rem; color: #8aa0b6; }
  .legend i { display: inline-block; width: 0.7rem; height: 0.7rem; border-radius: 2px; margin-right: 0.3rem; vertical-align: -1px; }
  .two { display: grid; grid-template-columns: 1fr; gap: 0 1rem; }
  .list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.45rem; }
  .list li { display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; font-size: 0.88rem; }
  .barwrap { flex: 1; height: 6px; background: #1c2833; border-radius: 3px; overflow: hidden; }
  .bar { display: block; height: 100%; background: #38bdf8; }
  .num { min-width: 4.5rem; text-align: right; font-variant-numeric: tabular-nums; }
  .checks { list-style: none; padding: 0; margin: 0 0 0.5rem; display: flex; flex-direction: column; gap: 0.5rem; }
  .checks li { display: flex; gap: 0.6rem; font-size: 0.9rem; }
  .mark { width: 1.3rem; height: 1.3rem; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 0.8rem; font-weight: 700; background: rgba(31,157,99,0.18); color: #1f9d63; flex-shrink: 0; }
  .checks li.bad .mark { background: rgba(245,158,11,0.18); color: #f59e0b; }
  .pill { font-size: 0.72rem; padding: 0.15rem 0.55rem; border-radius: 999px; border: 1px solid; font-weight: 600; }
  .pill.ok { color: #1f9d63; border-color: rgba(31,157,99,0.5); }
  .pill.warn { color: #f59e0b; border-color: rgba(245,158,11,0.5); }
  @media (min-width: 720px) {
    .grid { grid-template-columns: repeat(4, 1fr); }
    .facts { grid-template-columns: repeat(5, 1fr); }
    .two { grid-template-columns: 1fr 1fr; }
    .strip { grid-template-columns: repeat(60, 1fr); }
  }
</style>
