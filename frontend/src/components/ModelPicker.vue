<template>
  <label class="mp">
    <span class="sr-only">Modèle d'IA</span>
    <select
      v-model="chat.currentModel"
      :disabled="chat.availableModels.length === 0"
      aria-label="Choisir le modèle d'IA"
    >
      <optgroup
        v-if="installed.length"
        label="Installés"
      >
        <option
          v-for="m in installed"
          :key="m.name"
          :value="m.name"
        >
          {{ m.name }} ({{ m.size_gb }} Go){{ m.recommended ? ' ✓ adapté' : '' }}
        </option>
      </optgroup>
      <optgroup
        v-if="toInstall.length"
        :label="`Recommandés pour ${deviceLabel} (à installer)`"
      >
        <option
          v-for="name in toInstall"
          :key="name"
          :value="name"
          disabled
        >
          {{ name }} — ollama pull {{ name }}
        </option>
      </optgroup>
    </select>
  </label>
</template>

<script setup>
import { computed, watch } from 'vue'
import { useChatStore } from '../stores/chat.js'
import { useSettingsStore } from '../stores/settings.js'

const chat = useChatStore()
const settings = useSettingsStore()

const device = computed(() => settings.data.compute_device || 'gpu')
const deviceLabel = computed(() => (device.value === 'cpu' ? 'CPU' : 'GPU'))
const recommended = computed(() => settings.data.device_models?.[device.value] || [])

// Modèles installés, ceux adaptés au périphérique remontés en tête
const installed = computed(() => {
  const list = (chat.availableModels || []).map(m => ({
    ...m, recommended: recommended.value.includes(m.name),
  }))
  return list.sort((a, b) => (b.recommended - a.recommended) || a.name.localeCompare(b.name))
})

// Recommandés pour le périphérique mais pas encore installés
const toInstall = computed(() => {
  const have = new Set((chat.availableModels || []).map(m => m.name))
  return recommended.value.filter(n => !have.has(n))
})

// Au changement de périphérique, si le modèle courant n'est pas adapté, on bascule
// automatiquement vers le premier modèle installé recommandé pour ce périphérique.
watch(device, () => {
  const cur = chat.currentModel
  const curRec = recommended.value.includes(cur)
  if (!curRec) {
    const best = installed.value.find(m => m.recommended) || installed.value[0]
    if (best) chat.currentModel = best.name
  }
})
</script>

<style scoped>
.mp { display: inline-flex; }
select { min-width: 240px; width: auto; }
</style>
