<script setup>
import { ref, onMounted } from 'vue'
import { state, activeAlerts, actions } from './stores/sentinel'
import { videoUrl } from './services/api'
import StatusPanel from './components/StatusPanel.vue'
import LiveChart from './components/LiveChart.vue'
import AlertList from './components/AlertList.vue'
import CommandPanel from './components/ControlPanel.vue'
import { dashboardMock } from './mocks/dashboard.js'

const username = ref('')
const password = ref('')

const demoMode = import.meta.env.VITE_DEMO_MODE === 'true'

if(demoMode){
  Object.assign(state, dashboardMock)
}

onMounted(() => {
  if (!demoMode) actions.start().catch(() => {})
})
console.log(JSON.stringify(state))
// const submit = () => actions.login(username.value, password.value).catch(() => {})
</script>

<template>
  <main
    v-if="!state.authenticated"
    class="mx-auto my-[20vh] grid w-[calc(100%-2rem)] max-w-sm gap-3 rounded-lg border border-[#dcdcd6] bg-white p-5 text-[#1f1f1d] shadow-sm dark:border-[#3a3a36] dark:bg-[#222220] dark:text-[#eeeeea]"
  >
    <h1 class="text-xl font-bold">SENTINEL-X</h1>

    <input
      v-model="username"
      placeholder="Utilisateur"
      class="rounded border border-[#dcdcd6] bg-transparent px-3 py-2 text-inherit outline-none focus:ring-2 focus:ring-[#1d9e75]/30 dark:border-[#3a3a36]"
    />
    <input
      v-model="password"
      type="password"
      placeholder="Mot de passe"
      @keyup.enter="submit"
      class="rounded border border-[#dcdcd6] bg-transparent px-3 py-2 text-inherit outline-none focus:ring-2 focus:ring-[#1d9e75]/30 dark:border-[#3a3a36]"
    />
    <button
      class="cursor-pointer rounded bg-[#1f1f1d] px-3 py-2 font-medium text-white hover:opacity-90 dark:bg-[#eeeeea] dark:text-[#161615]"
      @click="submit"
    >
      Connexion
    </button>
    <p v-if="state.error" class="m-0 text-sm text-[#e24b4a]">{{ state.error }}</p>
  </main>

  <main
    v-else
    class="mx-auto grid max-w-6xl grid-cols-1 gap-4 p-4 text-[#1f1f1d] dark:text-[#eeeeea] md:grid-cols-2"
  >
    <header class="col-span-full flex flex-wrap items-center gap-3 border-b border-[#dcdcd6] pb-3 dark:border-[#3a3a36]">
      <h1 class="text-xl font-bold">SENTINEL-X</h1>
      <span
        :class="[
          'rounded-full px-2.5 py-1 text-xs font-medium text-white',
          state.live ? 'bg-[#1d9e75]' : 'bg-[#e24b4a]',
        ]"
      >
        {{ state.live ? 'Temps réel' : 'Reconnexion…' }}
      </span>
      <span v-if="state.user" class="text-sm text-[#6b6b66] dark:text-[#9a9a94]">
        {{ state.user.username }} ({{ state.user.role }})
      </span>
      <button
        class="ml-auto cursor-pointer rounded border border-[#dcdcd6] px-3 py-2 text-sm hover:bg-black/5 dark:border-[#3a3a36] dark:hover:bg-white/5"
        @click="actions.logout"
      >
        Déconnexion
      </button>
    </header>

    <div
      v-if="activeAlerts.length"
      class="col-span-full rounded-md bg-[#e24b4a] px-4 py-3 font-semibold text-white"
    >
      {{ activeAlerts.length }} alerte(s) active(s) :
      {{ activeAlerts[0].type }} ({{ activeAlerts[0].severity }})
    </div>

    <p
      v-if="state.error"
      class="col-span-full m-0 rounded-md border border-[#e24b4a]/30 bg-[#e24b4a]/10 p-3 text-sm text-[#e24b4a]"
    >
      {{ state.error }}
    </p>

    <StatusPanel
      class="col-span-full rounded-lg border border-[#dcdcd6] bg-white p-4 dark:border-[#3a3a36] dark:bg-[#222220]"
    />

    <section class="col-span-full rounded-lg border border-[#dcdcd6] bg-white p-4 dark:border-[#3a3a36] dark:bg-[#222220]">
      <h2 class="mb-2 text-sm font-semibold">Mesures</h2>
      <div class="h-[280px]">
        <LiveChart />
      </div>
    </section>

    <section class="rounded-lg border border-[#dcdcd6] bg-white p-4 dark:border-[#3a3a36] dark:bg-[#222220]">
      <h2 class="mb-2 text-sm font-semibold">Webcam</h2>
      <img
        :src="videoUrl()"
        alt="Flux webcam"
        class="aspect-[4/3] w-full rounded-lg bg-black object-cover"
      />
    </section>

    <CommandPanel
      class="rounded-lg border border-[#dcdcd6] bg-white p-4 dark:border-[#3a3a36] dark:bg-[#222220]"
    />
    <AlertList
      class="rounded-lg border border-[#dcdcd6] bg-white p-4 dark:border-[#3a3a36] dark:bg-[#222220]"
    />
  </main>
</template>

<style>
:root {
  --muted: #6b6b66;
  --ok: #1d9e75;
  --warn: #ef9f27;
  --bad: #e24b4a;
}

@media (prefers-color-scheme: dark) {
  :root {
    --muted: #9a9a94;
  }
}
</style>