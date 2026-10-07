<script setup>
import { computed } from 'vue'
import { state, latest } from '../stores/sentinel'

const color = computed(() => ({ NORMAL: 'var(--ok)', WARNING: 'var(--warn)', ALERT: 'var(--bad)' }[state.status?.state] || 'var(--muted)'))
const val = (v, unit) => (v === undefined || v === null ? '–' : `${v} ${unit}`)
</script>

<template>
  <section class="card status">
    <h2>Boîtier {{ state.status?.device_id ?? '' }}</h2>
    <div class="grid grid-cols-2 gap-4 sm:grid-cols-3">
      <div><small>État</small><b :style="{ color }">{{ state.status?.state ?? '–' }}</b></div>
      <div><small>Liaison</small><b>{{ state.status?.online ? 'En ligne' : 'Hors ligne' }}</b></div>
      <div><small>Température</small><b>{{ val(latest?.sensors.temperature_c, '°C') }}</b></div>
      <div><small>Humidité</small><b>{{ val(latest?.sensors.humidity_pct, '%') }}</b></div>
      <div><small>Gaz</small><b>{{ val(latest?.sensors.gas_ppm, 'ppm') }}</b></div>
      <div><small>Mouvement</small><b>{{ latest?.sensors.motion == null ? '–' : latest.sensors.motion ? 'Détecté' : 'Aucun' }}</b></div>
      <div><small>Classification</small><b>{{ latest?.label ?? '–' }}</b></div>
      <div><small>Signal WiFi</small><b>{{ val(state.status?.rssi_dbm, 'dBm') }}</b></div>
    </div>
  </section>
</template>

<style scoped>
small { display:block; color:var(--muted); font-size:12px; } b { font-size:20px; }
</style>