<script setup>
import { computed, reactive } from 'vue'
import { state, actions } from '../stores/sentinel'

const online = computed(() => !!state.status?.online)
const last = computed(() => Object.values(state.commands).at(-1))
const send = (target, action, ms = 0) => actions.sendCommand(target, action, ms).catch(() => {})
const selected = reactive({ buzzer: null, led_green: null, led_red: null })

const selectCommand = (target, action, ms = 0) => {
  selected[target] = action
  if (online.value) send(target, action, ms)
}
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
        class="rounded border border-neutral-300 px-2 py-2 text-xs font-medium
               hover:bg-neutral-100 dark:border-neutral-600 dark:hover:bg-neutral-800
               transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
        :class="selected.buzzer === 'blink' ? 'border-rose-600 bg-rose-600 text-white hover:bg-rose-700 dark:border-rose-500' : ''"
        :aria-pressed="selected.buzzer === 'blink'"
        @click="selectCommand('buzzer', 'blink', 5000)"
      >
        Alarme 5 s
      </button>
      <button
        class="rounded border border-neutral-300 px-2 py-2 text-xs font-medium
               hover:bg-neutral-100 dark:border-neutral-600 dark:hover:bg-neutral-800
               transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400"
        :class="selected.buzzer === 'off' ? 'border-rose-600 bg-rose-600 text-white hover:bg-rose-700 dark:border-rose-500' : ''"
        :aria-pressed="selected.buzzer === 'off'"
        @click="selectCommand('buzzer', 'off')"
      >
        Arrêt
      </button>
    </div>

    <div
      v-for="led in ['green', 'red']"
      :key="led"
      class="mb-3 grid grid-cols-[5rem_repeat(3,minmax(0,1fr))] items-center gap-2 last:mb-0"
    >
      <span class="truncate text-sm font-medium">LED {{ led }}</span>

      <button
        :class="[
          'rounded border px-2 py-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2',
          selected['led_' + led] === 'on'
            ? 'border-emerald-700 bg-emerald-600 text-white hover:bg-emerald-700 focus-visible:ring-emerald-500'
            : 'border-neutral-300 bg-transparent hover:bg-neutral-100 focus-visible:ring-emerald-500 dark:border-neutral-600 dark:hover:bg-neutral-800',
        ]"
        :aria-pressed="selected['led_' + led] === 'on'"
        @click="selectCommand('led_' + led, 'on')"
      >
        On
      </button>

      <button
        class="rounded border border-neutral-300 px-2 py-2 text-xs font-medium
               hover:bg-neutral-100 dark:border-neutral-600 dark:hover:bg-neutral-800
               transition-colors focus-visible:outline-none focus-visible:ring-2"
        :class="selected['led_' + led] === 'blink'
          ? (led === 'green'
              ? 'border-emerald-500 bg-emerald-100 text-emerald-900 hover:bg-emerald-200 focus-visible:ring-emerald-500 dark:border-emerald-700 dark:bg-emerald-900 dark:text-emerald-100'
              : 'border-rose-500 bg-rose-100 text-rose-900 hover:bg-rose-200 focus-visible:ring-rose-500 dark:border-rose-700 dark:bg-rose-900 dark:text-rose-100')
          : 'focus-visible:ring-neutral-400'"
        :aria-pressed="selected['led_' + led] === 'blink'"
        @click="selectCommand('led_' + led, 'blink')"
      >
        Clignote
      </button>

      <button
        class="rounded border border-neutral-300 px-2 py-2 text-xs font-medium
               hover:bg-neutral-100 dark:border-neutral-600 dark:hover:bg-neutral-800
               transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400"
        :class="selected['led_' + led] === 'off' ? 'border-rose-600 bg-rose-600 text-white hover:bg-rose-700 dark:border-rose-500' : ''"
        :aria-pressed="selected['led_' + led] === 'off'"
        @click="selectCommand('led_' + led, 'off')"
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
      v-if="!online"
      class="mt-3 rounded bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-200"
    >
      Boîtier hors ligne : aperçu local uniquement, commandes non transmises.
    </p>
  </section>
</template>