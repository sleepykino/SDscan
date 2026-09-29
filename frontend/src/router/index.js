import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('../layout/MainLayout.vue'),
    redirect: '/tasks',
    children: [
      {
        path: 'tasks',
        name: 'task-list',
        component: () => import('../views/TaskList.vue'),
        meta: { title: '任务列表', icon: 'List' },
      },
      {
        path: 'tasks/create',
        name: 'task-create',
        component: () => import('../views/TaskCreate.vue'),
        meta: { title: '新建任务', icon: 'Plus' },
      },
      {
        path: 'tasks/:id',
        name: 'task-detail',
        component: () => import('../views/TaskDetail.vue'),
        meta: { title: '任务详情', hidden: true },
      },
      {
        path: 'results',
        name: 'results',
        component: () => import('../views/Results.vue'),
        meta: { title: '结果列表', icon: 'Search' },
      },
      {
        path: 'hits',
        name: 'hits',
        component: () => import('../views/Hits.vue'),
        meta: { title: '敏感命中', icon: 'Warning' },
      },
      {
        path: 'platforms',
        name: 'platforms',
        component: () => import('../views/Platforms.vue'),
        meta: { title: '平台配置', icon: 'Monitor' },
      },
      {
        path: 'rules',
        name: 'rules',
        component: () => import('../views/Rules.vue'),
        meta: { title: '规则配置', icon: 'SetUp' },
      },
      {
        path: 'domains',
        name: 'domains',
        component: () => import('../views/Domains.vue'),
        meta: { title: '域名清单', icon: 'Connection' },
      },
      {
        path: 'attachments',
        name: 'attachments',
        component: () => import('../views/Attachments.vue'),
        meta: { title: '附件中心', icon: 'Paperclip' },
      },
      {
        path: 'data-sources',
        name: 'data-sources',
        component: () => import('../views/DataSources.vue'),
        meta: { title: 'T2 数据源', icon: 'Coin' },
      },
    ],
  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
