<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="logo">
        <span class="logo-mark">▚</span>
        <div>
          <div class="logo-en">SENTINEL</div>
          <div class="logo-cn">敏感信息检索</div>
        </div>
      </div>
      <nav class="nav">
        <router-link
          v-for="item in menus"
          :key="item.path"
          :to="item.path"
          class="nav-item"
        >
          <el-icon class="nav-icon"><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </router-link>
      </nav>
      <div class="sidebar-foot mono">localhost:8000</div>
    </aside>

    <div class="main">
      <header class="topbar">
        <div class="crumb">{{ route.meta.title || '' }}</div>
        <div class="top-actions">
          <el-tooltip content="全局设置">
            <el-button circle size="small" @click="settingsVisible = true">
              <el-icon><Setting /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </header>
      <main class="content">
        <router-view />
      </main>
    </div>

    <SettingsDialog v-model:visible="settingsVisible" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import SettingsDialog from '../components/SettingsDialog.vue'

const route = useRoute()
const settingsVisible = ref(false)

const menus = [
  { path: '/tasks', title: '任务列表', icon: 'List' },
  { path: '/tasks/create', title: '新建任务', icon: 'Plus' },
  { path: '/results', title: '结果列表', icon: 'Search' },
  { path: '/hits', title: '敏感命中', icon: 'Warning' },
  { path: '/domains', title: '域名清单', icon: 'Connection' },
  { path: '/attachments', title: '附件中心', icon: 'Paperclip' },
  { path: '/platforms', title: '平台配置', icon: 'Monitor' },
  { path: '/rules', title: '规则配置', icon: 'SetUp' },
]
</script>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.sidebar {
  width: 210px;
  flex-shrink: 0;
  background: #0a0e14;
  border-right: 1px solid var(--sd-border);
  display: flex;
  flex-direction: column;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px;
  border-bottom: 1px solid var(--sd-border);
}
.logo-mark {
  color: var(--sd-green-bright);
  font-size: 22px;
  text-shadow: 0 0 8px rgba(0, 230, 118, 0.8);
}
.logo-en {
  font-family: 'JetBrains Mono', Consolas, monospace;
  letter-spacing: 3px;
  font-weight: 700;
  font-size: 15px;
  color: var(--sd-green-bright);
}
.logo-cn {
  font-size: 11px;
  color: var(--sd-text-sub);
}

.nav {
  flex: 1;
  padding: 10px 0;
}
.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 18px;
  color: var(--sd-text-sub);
  font-size: 14px;
  border-left: 2px solid transparent;
  transition: background 0.12s, color 0.12s;
}
.nav-item:hover {
  background: var(--sd-bg-hover);
  color: var(--sd-green-text);
}
.nav-item.router-link-exact-active {
  color: var(--sd-green-text);
  background: rgba(63, 185, 80, 0.08);
  border-left-color: var(--sd-green);
}
.nav-icon {
  font-size: 16px;
}

.sidebar-foot {
  padding: 12px 18px;
  font-size: 11px;
  color: #4a5460;
  border-top: 1px solid var(--sd-border);
}

.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.topbar {
  height: 52px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 22px;
  background: var(--sd-bg-panel);
  border-bottom: 1px solid var(--sd-border);
}
.crumb {
  color: var(--sd-text-sub);
  font-size: 13px;
}
.content {
  flex: 1;
  overflow-y: auto;
  padding: 22px;
}
</style>
