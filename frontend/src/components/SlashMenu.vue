<script setup lang="ts">
/** 斜杠命令浮动菜单：定位到触发行 textarea 下方（底部溢出时翻转）。
 * 交互对齐飞书：双色两行条目、SVG 图标、底部快捷键提示。
 */
import { computed } from 'vue'
import type { SlashItem } from '@/types'

const props = defineProps<{ anchor: DOMRect; items: SlashItem[]; hi: number }>()
const emit = defineEmits<{ select: [item: SlashItem]; hover: [index: number] }>()

/** 各类型图标（24 线性 SVG，飞书风格） */
const ICONS: Record<string, string> = {
  text: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h10M4 18h13"/></svg>',
  code: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6l-5 6 5 6M16 6l5 6-5 6M13 4l-2 16"/></svg>',
  shell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v14H4zM7 10l2.5 2L7 14M12.5 14.5h4"/></svg>',
  output: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v14H4zM7 9h10M7 12.5h10M7 16h6"/></svg>',
  todo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v14H4z"/><path d="M7.5 12l3 3 6-6.5"/></svg>',
  table: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v14H4zM4 10h16M4 15h16M10 5v14M15 5v14"/></svg>',
  image: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v14H4z"/><circle cx="9" cy="10" r="1.6"/><path d="M4 17l5-4 3 2.5 4-4 4 3.5"/></svg>',
  tpl: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4h14v16H5z"/><path d="M8 8.5h8M8 12h8M8 15.5h4"/></svg>',
}

/** 图标底色（飞书式彩色图标位） */
const TINT: Record<string, string> = {
  text: '#8a8f98',
  code: '#4a5d8f',
  shell: '#b07916',
  output: '#2e7d51',
  todo: '#3a6fd8',
  table: '#8f6db4',
  image: '#2e8b77',
  tpl: '#b5442c',
}

function iconOf(key: string): string {
  return ICONS[key.startsWith('tpl-') ? 'tpl' : key] || ICONS.text
}
function tintOf(key: string): string {
  return TINT[key.startsWith('tpl-') ? 'tpl' : key] || TINT.text
}

const style = computed(() => {
  const a = props.anchor
  const estH = Math.min(props.items.length * 52 + 34, 380)
  const flip = a.bottom + estH + 8 > window.innerHeight
  return {
    left: Math.max(8, Math.min(a.left, window.innerWidth - 316)) + 'px',
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
      <span class="slash-icon" :style="{ color: tintOf(it.key) }" v-html="iconOf(it.key)"></span>
      <span class="slash-text">
        <span class="slash-label">{{ it.label }}</span>
        <span class="slash-desc">{{ it.desc }}</span>
      </span>
    </div>
    <div class="slash-foot">↑↓ 选择 · Enter 插入 · Esc 关闭</div>
  </div>
</template>

<style scoped>
.slash-menu {
  position: fixed;
  width: 304px;
  max-height: 380px;
  overflow: auto;
  z-index: 1000;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  padding: 5px;
  animation: wm-pop 0.14s ease-out;
}
.slash-item {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 6px 8px;
  border-radius: var(--radius);
  cursor: pointer;
  color: var(--fg);
  transition: background 0.1s;
}
.slash-item.hi { background: var(--bg-alt); }
.slash-icon {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  background: rgba(38, 40, 44, 0.045);
  flex-shrink: 0;
}
.slash-icon :deep(svg) { width: 19px; height: 19px; }
.slash-text { display: flex; flex-direction: column; min-width: 0; }
.slash-label { font-size: 13px; font-weight: 600; line-height: 1.4; white-space: nowrap; }
.slash-desc { color: var(--muted); font-size: 11px; line-height: 1.4; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.slash-foot {
  display: flex;
  justify-content: center;
  gap: 6px;
  margin-top: 4px;
  padding: 5px 0 2px;
  border-top: 1px solid var(--border);
  color: var(--faint);
  font-size: 11px;
  user-select: none;
}
</style>
