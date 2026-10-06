<script setup>
import { computed } from 'vue'
import { state, actions, isSupervisor } from '../stores/sentinel'

const online = computed(() => !!state.status?.online)
const enabled = computed(() => online.value && isSupervisor.value)
const last = computed(() => Object.values(state.commands).at(-1))
const send = (target, action, ms = 0) => actions.sendCommand(target, action, ms).catch(() => {})
</script>

<template>
  <section
    class="rounded-md border border-neutral-200 bg-white p-4 text-neutral-900
           dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
  >
    <h2 class="mb-4 text-sm font-semibold text-neutral-600 dark:text-neutral-300">
      Commandes
    </h2>

    <div class="mb-3 grid grid-cols-[5rem_repeat(2,minmax(0,1fr))] items-center gap-2">
      <span class="text-sm font-medium">Buzzer</span>
      <button
        :disabled="!enabled"
        class="rounded px-2 py-2 text-xs font-medium text-white
               bg-rose-600 hover:bg-rose-700
               focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500
               disabled:cursor-not-allowed disabled:opacity-40"
        @click="send('buzzer', 'blink', 5000)"
      >
        Alarme 5 s
      </button>
      <button
        :disabled="!enabled"
        class="rounded border border-neutral-300 px-2 py-2 text-xs font-medium
               hover:bg-neutral-100 dark:border-neutral-600 dark:hover:bg-neutral-800
               focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500
               disabled:cursor-not-allowed disabled:opacity-40"
        @click="send('buzzer', 'off')"
      >
        Arrêt
      </button>
    </div>

    <div
      v-for="led in ['green', 'orange', 'red']"
      :key="led"
      class="mb-3 grid grid-cols-[5rem_repeat(3,minmax(0,1fr))] items-center gap-2 last:mb-0"
    >
      <span class="truncate text-sm font-medium">LED {{ led }}</span>

      <button
        :disabled="!enabled"
        :class="[
          'rounded px-2 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-40',
          led === 'green' ? 'bg-emerald-600 hover:bg-emerald-700' : '',
          led === 'orange' ? 'bg-amber-500 hover:bg-amber-600' : '',
          led === 'red' ? 'bg-rose-600 hover:bg-rose-700' : '',
        ]"
        @click="send('led_' + led, 'on')"
      >
        On
      </button>

      <button
        :disabled="!enabled"
        class="rounded border border-neutral-300 px-2 py-2 text-xs font-medium
               hover:bg-neutral-100 dark:border-neutral-600 dark:hover:bg-neutral-800
               disabled:cursor-not-allowed disabled:opacity-40"
        @click="send('led_' + led, 'blink')"
      >
        Clignote
      </button>

      <button
        :disabled="!enabled"
        class="rounded border border-neutral-300 px-2 py-2 text-xs font-medium
               hover:bg-neutral-100 dark:border-neutral-600 dark:hover:bg-neutral-800
               disabled:cursor-not-allowed disabled:opacity-40"
        @click="send('led_' + led, 'off')"
      >
        Off
      </button>
    </div>

    <p
      v-if="last"
      class="mt-4 border-t border-neutral-200 pt-3 text-xs text-neutral-500 dark:border-neutral-700 dark:text-neutral-400"
    >
      Dernière commande : {{ last.target }} / {{ last.action }} → {{ last.status }}
    </p>

    <p
      v-if="!isSupervisor"
      class="mt-3 rounded bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-200"
    >
      Compte en lecture seule : commandes désactivées.
    </p>
    <p
      v-else-if="!online"
      class="mt-3 rounded bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-200"
    >
      Boîtier hors ligne : commandes désactivées.
    </p>
  </section>
</template>