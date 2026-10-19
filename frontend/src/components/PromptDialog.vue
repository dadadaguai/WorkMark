<script setup lang="ts">
/** 统一输入对话框（替代原生 prompt）：单行/多行输入，Esc 取消、Enter 确认、焦点恢复。 */
import { ref, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps<{
  title: string
  message?: string
  placeholder?: string
  initialValue?: string
  confirmText?: string
  cancelText?: string
  multiline?: boolean
}>()

const emit = defineEmits<{ confirm: [string]; cancel: [] }>()

const value = ref(props.initialValue ?? '')
const inputEl = ref<HTMLInputElement | HTMLTextAreaElement | null>(null)
let previouslyFocused: HTMLElement | null = null

function onConfirm() { emit('confirm', value.value) }
function onCancel() { emit('cancel') }

function onGlobalKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') { e.preventDefault(); onCancel() }
}
function onInputKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !props.multiline) { e.preventDefault(); onConfirm() }
}

onMounted(() => {
  previouslyFocused = document.activeElement as HTMLElement | null
  nextTick(() => inputEl.value?.focus())
  document.addEventListener('keydown', onGlobalKeydown)
})
onUnmounted(() => {
  document.removeEventListener('keydown', onGlobalKeydown)
  previouslyFocused?.focus?.()
})
</script>

<template>
  <div class="dialog-overlay" role="dialog" aria-modal="true" aria-labelledby="prompt-dialog-title" @click.self="onCancel">
    <div class="dialog">
      <h3 id="prompt-dialog-title" class="dialog-title">{{ title }}</h3>
      <p v-if="message" class="dialog-message">{{ message }}</p>
      <textarea
        v-if="multiline"
        ref="inputEl"
        v-model="value"
        class="dialog-input prompt-textarea"
        :placeholder="placeholder"
        rows="3"
      ></textarea>
      <input
        v-else
        ref="inputEl"
        v-model="value"
        class="dialog-input"
        :placeholder="placeholder"
        @keydown="onInputKeydown"
      />
      <div class="dialog-actions">
        <button @click="onCancel">{{ cancelText || '取消' }}</button>
        <button class="primary" @click="onConfirm">{{ confirmText || '确认' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dialog-overlay {
  position: fixed; inset: 0;
  background: rgba(35, 39, 43, 0.38);
  backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.dialog {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 26px;
  width: min(480px, calc(100vw - 32px));
  box-shadow: var(--shadow-lg);
  animation: wm-pop 0.18s ease-out;
}
.dialog-title { font-family: var(--font-serif); font-size: 1.15rem; font-weight: 700; margin-bottom: 8px; }
.dialog-message { color: var(--muted); margin-bottom: 12px; font-size: 0.9rem; }
.dialog-input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  margin-bottom: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 0.9rem;
  background: var(--bg);
  font-family: inherit;
}
.prompt-textarea { resize: vertical; line-height: 1.6; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; }
</style>