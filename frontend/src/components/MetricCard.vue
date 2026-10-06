<template>
  <div class="bg-dark-800 border border-gray-800 p-4 rounded-lg flex items-center justify-between">
    <div>
      <p class="text-xs text-gray-400 font-mono">{{ title }}</p>
      <p class="text-2xl font-bold mt-1" :style="{ color: accentColor }">
        {{ value }} <span class="text-sm font-normal text-gray-400">{{ unit }}</span>
      </p>
    </div>
    <div class="w-10 h-10 rounded-full flex items-center justify-center bg-gray-900 border border-gray-700">
      <i :class="[icon, 'text-lg']" :style="{ color: accentColor }"></i>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: String,
  value: [Number, String, Boolean],
  unit: String,
  icon: String,
  accentColor: { type: String, default: '#13c2c2' }
});
</script>