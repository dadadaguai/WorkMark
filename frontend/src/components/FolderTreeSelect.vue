<script setup lang="ts">
/** 树形文件夹选择器（移动文档/文件夹共用）：缩进层级 + 展开/折叠 + 单选。
 * modelValue 为选中的 folder_id；允许多次展开。allowRoot 时顶部提供「根级」选项。
 */
import { ref, computed } from 'vue'
import type { Folder } from '@/types'

const props = defineProps<{
  folders: Folder[]
  modelValue: number | null
  allowRoot?: boolean
  /** 不可选中的文件夹 id（如移动文件夹时的自身及其子孙） */
  disabled?: number[]
}>()
const emit = defineEmits<{ 'update:modelValue': [number | null] }>()

const expanded = ref(new Set<number>())
const disabledSet = computed(() => new Set(props.disabled ?? []))

const childrenMap = computed(() => {
  const map = new Map<number | null, Folder[]>()
  for (const f of props.folders) {
    const k = f.parent_id
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(f)
  }
  for (const arr of map.values()) arr.sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
  return map
})

function childrenOf(pid: number | null): Folder[] {
  return childrenMap.value.get(pid) ?? []
}

const visible = computed(() => {
  const out: { f: Folder; depth: number }[] = []
  const walk = (pid: number | null, depth: number) => {
    for (const f of childrenOf(pid)) {
      out.push({ f, depth })
      if (expanded.value.has(f.id)) walk(f.id, depth + 1)
    }
  }
  walk(null, 0)
  return out
})

function toggle(id: number) {
  const s = new Set(expanded.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  expanded.value = s
}

function pick(id: number | null) {
  if (id !== null && disabledSet.value.has(id)) return
  emit('update:modelValue', id)
}
</script>

<template>
  <div class="folder-tree">
    <button v-if="allowRoot" class="tree-row" :class="{ selected: modelValue === null }" @click="pick(null)">
      <span class="tree-dot"></span>
      <span class="tree-name">（根级）</span>
    </button>
    <div v-for="n in visible" :key="n.f.id" class="tree-row" :class="{ selected: modelValue === n.f.id, disabled: disabledSet.has(n.f.id) }" :style="{ paddingLeft: (8 + n.depth * 16) + 'px' }" @click="pick(n.f.id)">
      <span class="tree-toggle" :class="{ has: childrenOf(n.f.id).length > 0 }" @click.stop="toggle(n.f.id)">
        {{ childrenOf(n.f.id).length ? (expanded.has(n.f.id) ? '▾' : '▸') : '' }}
      </span>
      <span class="tree-dot"></span>
      <span class="tree-name">{{ n.f.name }}</span>
      <span v-if="n.f.is_default" class="tree-star">★</span>
    </div>
  </div>
</template>

<style scoped>
.folder-tree {
  max-height: 260px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px;
  margin-bottom: 12px;
  background: var(--bg);
}
.tree-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9rem;
  color: var(--fg);
  border: none;
  background: transparent;
  width: 100%;
  text-align: left;
  transition: background 0.12s;
}
.tree-row:hover { background: var(--bg-alt); }
.tree-row.selected { background: var(--accent-light); color: var(--accent); font-weight: 600; }
.tree-row.disabled { opacity: 0.45; cursor: not-allowed; }
.tree-toggle {
  width: 16px;
  flex-shrink: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--muted);
  font-size: 0.72rem;
  padding: 0;
}
.tree-toggle.has { cursor: pointer; }
.tree-dot {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  border-radius: 50%;
  border: 1.5px solid var(--border-strong);
  background: transparent;
}
.tree-row.selected .tree-dot { border-color: var(--accent); background: var(--accent); }
.tree-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tree-star { color: var(--warn); font-size: 0.8rem; }
</style>