<script setup>
import { computed } from 'vue'
import { state, actions } from '../store'

const online = computed(() => !!state.status?.online)
const last = computed(() => Object.values(state.commands).at(-1))
const send = (target, action, ms = 0) => actions.sendCommand(target, action, ms).catch(() => {})
</script>

<template>
  <section class="card">
    <h2>Commandes</h2>
    <div class="row">
      <span>Buzzer</span>
      <button :disabled="!online" @click="send('buzzer', 'blink', 5000)">Alarme 5 s</button>
      <button :disabled="!online" @click="send('buzzer', 'off')">Arrêt</button>
    </div>
    <div v-for="led in ['green', 'orange', 'red']" :key="led" class="row">
      <span>LED {{ led }}</span>
      <button :disabled="!online" @click="send('led_' + led, 'on')">On</button>
      <button :disabled="!online" @click="send('led_' + led, 'blink')">Clignote</button>
      <button :disabled="!online" @click="send('led_' + led, 'off')">Off</button>
    </div>
    <p v-if="last" class="last">Dernière commande : {{ last.target }} / {{ last.action }} → {{ last.status }}</p>
    <p v-if="!online" class="last">Boîtier hors ligne : commandes désactivées.</p>
  </section>
</template>

<style scoped>
.row { display:flex; align-items:center; gap:8px; margin-bottom:8px; } .row span { width:90px; }
.last { color:var(--muted); font-size:13px; margin:8px 0 0; }
</style>