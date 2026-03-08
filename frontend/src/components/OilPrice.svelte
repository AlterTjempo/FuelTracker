<script>
  import { onMount, onDestroy } from 'svelte'
  import { Chart, registerables } from 'chart.js'
  import { format } from 'date-fns'
  import API_BASE from '../lib/api.js'

  Chart.register(...registerables)

  export let hours = 24

  let data = null
  let loading = true
  let error = false

  let historyData = []
  let historyLoading = true
  let chartCanvas
  let chart

  const formatter = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Berlin',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })

  async function fetchOilPrice() {
    try {
      const res = await fetch(`${API_BASE}/oil-prices/latest`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      data = await res.json()
      error = false
    } catch (e) {
      console.error('Error fetching oil price:', e)
      error = true
    } finally {
      loading = false
    }
  }

  async function fetchHistory() {
    try {
      historyLoading = true
      const res = await fetch(`${API_BASE}/oil-prices/history?hours=${hours}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      historyData = await res.json()
    } catch (e) {
      console.error('Error fetching oil history:', e)
      historyData = []
    } finally {
      historyLoading = false
    }
  }

  function updateChart() {
    if (!chartCanvas || historyData.length === 0) return
    if (chart) chart.destroy()

    const ctx = chartCanvas.getContext('2d')
    const labels = historyData.map(d => format(new Date(d.timestamp), 'MMM dd HH:mm'))

    chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'USD / barrel',
            data: historyData.map(d => d.price_usd_per_barrel),
            borderColor: '#f59e0b',
            backgroundColor: 'rgba(245, 158, 11, 0.1)',
            borderWidth: 2,
            tension: 0,
            fill: true,
            pointRadius: 0,
            pointHoverRadius: 6,
            yAxisID: 'yUsd',
          },
          {
            label: 'EUR / liter',
            data: historyData.map(d => d.price_eur_per_liter),
            borderColor: '#58a6ff',
            borderWidth: 2,
            tension: 0,
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 6,
            yAxisID: 'yEur',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            display: true,
            position: 'top',
            labels: { color: '#8b949e', font: { size: 12 } },
          },
          tooltip: {
            backgroundColor: '#161b22',
            borderColor: '#30363d',
            borderWidth: 1,
            titleColor: '#e6edf3',
            bodyColor: '#8b949e',
            callbacks: {
              label: (ctx) => {
                if (ctx.dataset.yAxisID === 'yUsd')
                  return `${ctx.dataset.label}: $${ctx.parsed.y.toFixed(2)}`
                return `${ctx.dataset.label}: €${ctx.parsed.y.toFixed(4)}`
              },
            },
          },
        },
        scales: {
          x: {
            grid: { color: '#30363d', drawBorder: false },
            ticks: { color: '#8b949e', maxRotation: 45, minRotation: 45 },
          },
          yUsd: {
            position: 'left',
            grid: { color: '#30363d', drawBorder: false },
            ticks: {
              color: '#f59e0b',
              callback: (v) => `$${v.toFixed(0)}`,
            },
          },
          yEur: {
            position: 'right',
            grid: { drawOnChartArea: false },
            ticks: {
              color: '#58a6ff',
              callback: (v) => `€${v.toFixed(3)}`,
            },
          },
        },
      },
    })
  }

  onMount(() => {
    fetchOilPrice()
    fetchHistory()
    const interval = setInterval(() => { fetchOilPrice(); fetchHistory() }, 15 * 60 * 1000)
    return () => clearInterval(interval)
  })

  onDestroy(() => { if (chart) chart.destroy() })

  $: if (hours) fetchHistory()

  $: if (chartCanvas && historyData.length > 0) {
    updateChart()
  } else if (chart && historyData.length === 0) {
    chart.destroy()
    chart = null
  }
</script>

<div class="oil-price">
  <div class="oil-header">
    <span class="oil-icon">🛢️</span>
    <span class="oil-title">Brent Crude Oil Index</span>
  </div>

  {#if loading}
    <div class="loading">Loading…</div>
  {:else if error || !data}
    <div class="no-data">No data</div>
  {:else}
    <div class="metrics">
      <div class="metric primary">
        <div class="value">${data.price_usd_per_barrel.toFixed(2)}</div>
        <div class="label">per barrel</div>
      </div>
      <div class="divider"></div>
      <div class="metric">
        <div class="value">€{data.price_eur_per_barrel.toFixed(2)}</div>
        <div class="label">per barrel</div>
      </div>
      <div class="divider"></div>
      <div class="metric">
        <div class="value">€{data.price_eur_per_liter.toFixed(4)}</div>
        <div class="label">per liter</div>
      </div>
    </div>
    <div class="updated">Updated {formatter.format(new Date(data.timestamp))}</div>
  {/if}
</div>

<div class="main-chart">
  {#if historyLoading}
    <div class="chart-placeholder">Loading chart…</div>
  {:else if historyData.length === 0}
    <div class="chart-placeholder">No history data yet.</div>
  {:else}
    <canvas bind:this={chartCanvas}></canvas>
  {/if}
</div>

<style>
  .oil-price {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 1rem 1.25rem;
    margin-bottom: 1rem;
  }

  .oil-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }

  .oil-icon {
    font-size: 1.2rem;
  }

  .oil-title {
    font-size: 1rem;
    font-weight: 600;
    color: #e6edf3;
  }

  .metrics {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .metric {
    display: flex;
    flex-direction: column;
    align-items: center;
    flex: 1;
    min-width: 80px;
  }

  .metric.primary .value {
    color: #f59e0b;
    font-size: 1.25rem;
  }

  .value {
    font-size: 1.1rem;
    font-weight: 700;
    color: #58a6ff;
    font-variant-numeric: tabular-nums;
  }

  .label {
    font-size: 0.7rem;
    color: #8b949e;
    margin-top: 0.2rem;
    text-align: center;
  }

  .divider {
    width: 1px;
    height: 2rem;
    background: #30363d;
    flex-shrink: 0;
  }

  .updated {
    margin-top: 0.6rem;
    font-size: 0.7rem;
    color: #8b949e;
    text-align: right;
  }

  .loading,
  .no-data {
    color: #8b949e;
    font-size: 0.875rem;
  }

  .main-chart {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 0.75rem;
    margin-bottom: 1rem;
    height: 250px;
    position: relative;
  }

  .main-chart canvas {
    max-height: 250px;
  }

  .chart-placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #8b949e;
    font-size: 0.95rem;
  }

  @media (min-width: 640px) {
    .main-chart { height: 350px; }
    .main-chart canvas { max-height: 350px; }
  }

  @media (min-width: 1024px) {
    .main-chart { height: 400px; }
    .main-chart canvas { max-height: 400px; }
  }
</style>