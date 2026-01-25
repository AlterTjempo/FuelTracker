<script>
  import { onMount, onDestroy } from 'svelte'
  import { Chart, registerables } from 'chart.js'
  import { format } from 'date-fns'
  
  Chart.register(...registerables)
  
  export let fuelType = 'e5'
  export let hours = 24
  
  let chartCanvas
  let chart
  let data = []
  let loading = true
  
  async function fetchData() {
    try {
      const response = await fetch(`http://localhost:8000/api/prices/history/all?fuel_type=${fuelType}&hours=${hours}`)
      const result = await response.json()
      data = result
      updateChart()
      loading = false
    } catch (error) {
      console.error('Error fetching data:', error)
      loading = false
    }
  }
  
  function updateChart() {
    if (!chartCanvas || data.length === 0) return
    
    const ctx = chartCanvas.getContext('2d')
    
    if (chart) {
      chart.destroy()
    }
    
    const labels = data.map(d => format(new Date(d.timestamp), 'MMM dd HH:mm'))
    const avgPrices = data.map(d => d.avg_price)
    const minPrices = data.map(d => d.min_price)
    const maxPrices = data.map(d => d.max_price)
    
    chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Average Price',
            data: avgPrices,
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            borderWidth: 2,
            tension: 0.4,
            fill: true,
            pointRadius: 0,
            pointHoverRadius: 6,
          },
          {
            label: 'Min Price',
            data: minPrices,
            borderColor: '#10b981',
            borderWidth: 1,
            borderDash: [5, 5],
            tension: 0.4,
            fill: false,
            pointRadius: 0,
          },
          {
            label: 'Max Price',
            data: maxPrices,
            borderColor: '#ef4444',
            borderWidth: 1,
            borderDash: [5, 5],
            tension: 0.4,
            fill: false,
            pointRadius: 0,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false,
        },
        plugins: {
          legend: {
            display: true,
            position: 'top',
            labels: {
              color: '#8b949e',
              font: {
                size: 12
              }
            }
          },
          tooltip: {
            backgroundColor: '#161b22',
            borderColor: '#30363d',
            borderWidth: 1,
            titleColor: '#e6edf3',
            bodyColor: '#8b949e',
            callbacks: {
              label: function(context) {
                return context.dataset.label + ': €' + context.parsed.y.toFixed(3)
              }
            }
          }
        },
        scales: {
          x: {
            grid: {
              color: '#30363d',
              drawBorder: false,
            },
            ticks: {
              color: '#8b949e',
              maxRotation: 45,
              minRotation: 45
            }
          },
          y: {
            grid: {
              color: '#30363d',
              drawBorder: false,
            },
            ticks: {
              color: '#8b949e',
              callback: function(value) {
                return '€' + value.toFixed(3)
              }
            }
          }
        }
      }
    })
  }
  
  onMount(() => {
    fetchData()
    const interval = setInterval(fetchData, 60000) // Update every minute
    return () => clearInterval(interval)
  })
  
  onDestroy(() => {
    if (chart) {
      chart.destroy()
    }
  })
  
  $: if (fuelType || hours) {
    fetchData()
  }
</script>

<div class="chart-container">
  {#if loading}
    <div class="loading">Loading price data...</div>
  {:else if data.length === 0}
    <div class="no-data">No data available yet. Data collection in progress...</div>
  {:else}
    <canvas bind:this={chartCanvas}></canvas>
  {/if}
</div>

<style>
  .chart-container {
    height: 400px;
    position: relative;
  }
  
  canvas {
    max-height: 400px;
  }
  
  .loading, .no-data {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #8b949e;
    font-size: 1.1rem;
  }
</style>
