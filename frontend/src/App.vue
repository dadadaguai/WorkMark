<script setup lang="ts">
import ToastStack from '@/components/ToastStack.vue'
</script>

<template>
  <div class="app-layout">
    <router-view />
    <ToastStack />
  </div>
</template>
