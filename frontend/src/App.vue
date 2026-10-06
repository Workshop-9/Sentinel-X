<script setup>
import { ref, onMounted } from 'vue'
import { state, activeAlerts, actions } from './store'
import { videoUrl } from './api'
import StatusPanel from './components/StatusPanel.vue'
import LiveChart from './components/LiveChart.vue'
import AlertList from './components/AlertList.vue'
import CommandPanel from './components/ControlPanel.vue'

const username = ref('supervisor')
const password = ref('')

onMounted(() => actions.start().catch(() => {}))
const submit = () => actions.login(username.value, password.value).catch(() => {})
</script>

<template>
  <main v-if="!state.authenticated" class="login card">
    <h1>SENTINEL-X</h1>
    <input v-model="username" placeholder="Utilisateur" />
    <input v-model="password" type="password" placeholder="Mot de passe" @keyup.enter="submit" />
    <button class="primary" @click="submit">Connexion</button>
    <p v-if="state.error" class="err">{{ state.error }}</p>
  </main>

  <main v-else class="layout">
    <header>
      <h1>SENTINEL-X</h1>
      <span :class="['pill', state.live ? 'ok' : 'ko']">{{ state.live ? 'Temps réel' : 'Reconnexion…' }}</span>
      <button @click="actions.logout">Déconnexion</button>
    </header>

    <div v-if="activeAlerts.length" class="banner">
      {{ activeAlerts.length }} alerte(s) active(s) : {{ activeAlerts[0].type }} ({{ activeAlerts[0].severity }})
    </div>

    <StatusPanel />
    <section class="card chart"><h2>Mesures</h2><LiveChart /></section>
    <section class="card video"><h2>Webcam</h2><img :src="videoUrl()" alt="Flux webcam" /></section>
    <CommandPanel />
    <AlertList />
  </main>
</template>

<style>
:root { --bg:#f5f5f2; --card:#fff; --text:#1f1f1d; --muted:#6b6b66; --line:#dcdcd6; --ok:#1d9e75; --warn:#ef9f27; --bad:#e24b4a; }
@media (prefers-color-scheme: dark) { :root { --bg:#161615; --card:#222220; --text:#eeeeea; --muted:#9a9a94; --line:#3a3a36; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font-family: system-ui, sans-serif; }
h1 { font-size:20px; margin:0; } h2 { font-size:14px; margin:0 0 10px; color:var(--muted); font-weight:600; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }
.layout { max-width:1100px; margin:0 auto; padding:16px; display:grid; gap:16px; grid-template-columns: 1fr 1fr; }
.layout > header, .banner, .chart, .status { grid-column: 1 / -1; }
header { display:flex; align-items:center; gap:12px; } header button { margin-left:auto; }
.banner { background:var(--bad); color:#fff; padding:12px 16px; border-radius:12px; font-weight:600; }
.chart > div { height:280px; } .video img { width:100%; border-radius:8px; background:#000; aspect-ratio:4/3; }
.login { max-width:320px; margin:20vh auto; display:grid; gap:10px; }
input, button { padding:8px 12px; border-radius:8px; border:1px solid var(--line); background:var(--card); color:var(--text); font:inherit; }
button { cursor:pointer; } button:disabled { opacity:.4; cursor:not-allowed; }
button.primary { background:var(--text); color:var(--bg); }
.pill { padding:2px 10px; border-radius:99px; font-size:12px; color:#fff; } .pill.ok { background:var(--ok); } .pill.ko { background:var(--bad); }
.err { color:var(--bad); margin:0; }
@media (max-width: 760px) { .layout { grid-template-columns: 1fr; } }
</style>