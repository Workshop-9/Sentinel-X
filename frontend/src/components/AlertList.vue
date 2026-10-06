<script setup>
import { state, actions, isSupervisor } from '../stores/sentinel'

const colors = { info: 'var(--muted)', warning: 'var(--warn)', critical: 'var(--bad)' }
const time = (iso) => new Date(iso).toLocaleTimeString()
</script>

<template>
  <section class="card">
    <h2>Alertes</h2>
    <p v-if="!state.alerts.length" class="empty">Aucune alerte.</p>
    <ul class="list-style-none m-0 p-0 grid gap-2 max-h-75 overflow-auto">
      <li class="flex items-center gap-2" v-for="a in state.alerts.slice(0, 15)" :key="a.id">
        <span class="dot w-2.5 h-2.5 border-rounded" :style="{ background: colors[a.severity] }"></span>
        <span class="txt"><b>{{ a.type }}</b> · {{ a.event === 'cleared' ? 'résolue' : 'levée' }} · {{ a.source }}<br /><small>{{ time(a.received_at) }}</small></span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
small, .empty { color:var(--muted); }
</style>