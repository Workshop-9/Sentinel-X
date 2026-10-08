<script setup>
import { onMounted, ref } from 'vue'
import { state, activeAlerts, actions } from './stores/sentinel'
import { videoUrl } from './services/api'
import StatusPanel from './components/StatusPanel.vue'
import LiveChart from './components/LiveChart.vue'
import AlertList from './components/AlertList.vue'
import CommandPanel from './components/ControlPanel.vue'

onMounted(() => {
  actions.start().catch(console.error)
})

const videoError = ref(false)
</script>

<template>
  <main
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
      <div class="h-70">
        <LiveChart />
      </div>
    </section>

    <section class="rounded-lg border border-[#dcdcd6] bg-white p-4 dark:border-[#3a3a36] dark:bg-[#222220]">
      <h2 class="mb-2 text-sm font-semibold">Webcam</h2>
      <div class="flex aspect-4/3 w-full items-center justify-center overflow-hidden rounded-lg bg-black">
        <img
          v-if="!videoError"
          :src="videoUrl()"
          alt="Flux webcam"
          class="h-full w-full object-cover"
          @error="videoError = true"
        />
        <p v-else class="px-4 text-center text-sm text-white">
          Flux vidéo indisponible. Vérifiez que le backend fonctionne et qu’une webcam est accessible.
        </p>
      </div>
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