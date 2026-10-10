<script setup lang="ts">
/** 通用确认对话框，支持显示影响范围详情。 */

defineProps<{
  title: string
  message?: string
  details?: { label: string; value: number | string }[]
  confirmText?: string
  cancelText?: string
  danger?: boolean
}>()

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()

function onConfirm() { emit('confirm') }
function onCancel() { emit('cancel') }
</script>

<template>
  <div class="dialog-overlay" @click.self="onCancel">
    <div class="dialog">
      <h3 class="dialog-title">{{ title }}</h3>
      <p v-if="message" class="dialog-message">{{ message }}</p>
      <ul v-if="details && details.length" class="dialog-details">
        <li v-for="d in details" :key="d.label">
          <span class="detail-label">{{ d.label }}</span>
          <span class="detail-value">{{ d.value }}</span>
        </li>
      </ul>
      <div class="dialog-slot"><slot /></div>
      <div class="dialog-actions">
        <button @click="onCancel">{{ cancelText || '取消' }}</button>
        <button :class="danger ? 'danger' : 'primary'" @click="onConfirm">{{ confirmText || '确认' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dialog-overlay {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.dialog {
  background: var(--bg);
  border-radius: var(--radius);
  padding: 24px;
  min-width: 360px;
  max-width: 480px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}
.dialog-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 8px; }
.dialog-message { color: var(--muted); margin-bottom: 12px; font-size: 0.9rem; }
.dialog-details { list-style: none; margin-bottom: 16px; }
.dialog-details li {
  display: flex; justify-content: space-between;
  padding: 6px 12px; background: var(--bg-alt);
  border-radius: var(--radius); margin-bottom: 4px; font-size: 0.88rem;
}
.detail-label { color: var(--muted); }
.detail-value { font-weight: 600; }
.dialog-slot { margin-bottom: 16px; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; }
</style>
