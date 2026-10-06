<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { Chart, LineController, LineElement, PointElement, LinearScale, CategoryScale, Legend, Tooltip } from 'chart.js'
import { chart } from '../store'

Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Legend, Tooltip)

const canvas = ref(null)
let c = null

const line = (label, color, yAxisID) => ({ label, borderColor: color, yAxisID, data: [] })

function refresh() {
  if (!c) return
  c.data.labels = chart.value.labels.map((l) => new Date(l).toLocaleTimeString())
  c.data.datasets[0].data = chart.value.temperature
  c.data.datasets[1].data = chart.value.humidity
  c.data.datasets[2].data = chart.value.gas
  c.update('none')
}

onMounted(() => {
  c = new Chart(canvas.value, {
    type: 'line',
    data: { labels: [], datasets: [line('Température (°C)', '#e24b4a', 'y'), line('Humidité (%)', '#378add', 'y'), line('Gaz (ppm)', '#ef9f27', 'y1')] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false, pointRadius: 0, borderWidth: 2,
      scales: { x: { ticks: { maxTicksLimit: 6 } }, y: { position: 'left' }, y1: { position: 'right', grid: { drawOnChartArea: false } } },
    },
  })
  refresh()
})
onBeforeUnmount(() => c?.destroy())
watch(chart, refresh)
</script>

<template><div><canvas ref="canvas"></canvas></div></template>