<script setup>
import { state, actions } from '../store'

const colors = { info: 'var(--muted)', warning: 'var(--warn)', critical: 'var(--bad)' }
const time = (iso) => new Date(iso).toLocaleTimeString()
</script>

<template>
  <section class="card">
    <h2>Alertes</h2>
    <p v-if="!state.alerts.length" class="empty">Aucune alerte.</p>
    <ul>
      <li v-for="a in state.alerts.slice(0, 15)" :key="a.id">
        <span class="dot" :style="{ background: colors[a.severity] }"></span>
        <span class="txt"><b>{{ a.type }}</b> · {{ a.event === 'cleared' ? 'résolue' : 'levée' }} · {{ a.source }}<br /><small>{{ time(a.received_at) }}</small></span>
        <button v-if="a.event === 'raised' && !a.acknowledged" @click="actions.ackAlert(a.id)">Acquitter</button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
ul { list-style:none; margin:0; padding:0; display:grid; gap:8px; max-height:300px; overflow:auto; }
li { display:flex; align-items:center; gap:10px; } .txt { flex:1; } .dot { width:10px; height:10px; border-radius:50%; }
small, .empty { color:var(--muted); }
</style>