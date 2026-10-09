<script setup>
import { state } from '../stores/sentinel'

const colors = { info: 'var(--muted)', warning: 'var(--warn)', critical: 'var(--bad)' }
const time = (iso) => new Date(iso).toLocaleTimeString()
const alertLabel = (alert) => {
  if (alert.details?.source === 'vision') return 'Intrusion caméra'
  if (alert.type === 'anomaly') return 'Anomalie IA'
  return alert.type
}
</script>

<template>
  <section class="card">
    <h2>Alertes</h2>
    <p v-if="!state.alerts.length" class="empty">Aucune alerte.</p>
    <ul class="list-style-none m-0 p-0 grid gap-2 max-h-75 overflow-auto">
      <li class="flex items-center gap-2" v-for="a in state.alerts.slice(0, 15)" :key="a.id">
        <span class="dot w-2.5 h-2.5 border-rounded" :style="{ background: colors[a.severity] }"></span>
        <span class="txt">
          <b>{{ alertLabel(a) }}</b>
          · {{ a.event === 'cleared' ? 'résolue' : 'levée' }} · {{ a.source }}<br />
          <small>{{ time(a.received_at) }}</small>
          <small v-if="a.details?.causes?.length"> · {{ a.details.causes.join(', ') }}</small>
          <small v-if="a.details?.score != null"> · score {{ a.details.score }}</small>
          <small v-if="a.details?.source === 'vision'">
            · {{ a.details.persons }} personne(s), confiance {{ Math.round(a.details.confidence * 100) }}%
            <span v-if="a.details.snapshot"> · {{ a.details.snapshot }}</span>
          </small>
        </span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
small, .empty { color:var(--muted); }
</style>