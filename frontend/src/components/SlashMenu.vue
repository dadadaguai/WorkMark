<script setup lang="ts">
/** 斜杠命令浮动菜单：定位到触发行的 textarea 下方（底部溢出时翻转），供文档流编辑器插入富内容。 */
import { computed } from 'vue'
import type { SlashItem } from '@/types'

const props = defineProps<{ anchor: DOMRect; items: SlashItem[]; hi: number }>()
const emit = defineEmits<{ select: [item: SlashItem]; hover: [index: number] }>()

const style = computed(() => {
  const a = props.anchor
  const estH = Math.min(props.items.length * 34 + 10, 320)
  const flip = a.bottom + estH + 8 > window.innerHeight
  return {
    left: Math.max(8, Math.min(a.left, window.innerWidth - 276)) + 'px',
    top: (flip ? a.top - estH - 6 : a.bottom + 6) + 'px',
  }
})
</script>

<template>
  <div class="slash-menu" :style="style">
    <div
      v-for="(it, i) in items"
      :key="it.key"
      class="slash-item"
      :class="{ hi: i === hi }"
      @mousedown.prevent
      @click="emit('select', it)"
      @mousemove="emit('hover', i)"
    >
      <span class="slash-icon">{{ it.icon }}</span>
      <span class="slash-label">{{ it.label }}</span>
      <span class="slash-desc">{{ it.desc }}</span>
    </div>
  </div>
</template>

<style scoped>
.slash-menu {
  position: fixed;
  width: 264px;
  max-height: 320px;
  overflow: auto;
  z-index: 1000;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  padding: 4px;
}
.slash-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  color: var(--fg);
}
.slash-item.hi { background: var(--bg-alt); }
.slash-icon { width: 22px; text-align: center; color: var(--muted); font-size: 12px; flex-shrink: 0; }
.slash-label { font-weight: 600; white-space: nowrap; }
.slash-desc { color: var(--muted); font-size: 11px; margin-left: auto; padding-left: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
