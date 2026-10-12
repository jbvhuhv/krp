import { createRouter, createWebHistory } from 'vue-router'


import MainLayout from '@/layouts/MainLayout.vue'


const routes = [
  {
    path: '/chat/:avatarId',
    name: 'VisitorChat',
    component: () => import('@/views/avatar/VisitorChat.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: MainLayout,
    redirect: '/community',
    children: [
      {
        path: 'community',
        name: 'Community',
        component: () => import('@/views/community/Community.vue'),
        meta: { title: '知识广场', public: true },
      },
      {
        path: 'community/search',
        name: 'SearchResults',
        component: () => import('@/views/community/SearchResults.vue'),
        meta: { title: '搜索结果', public: true },
      },
      {
        path: 'community/:id',
        name: 'CommunityDetail',
        component: () => import('@/views/community/CommunityDetail.vue'),
        meta: { title: '图谱详情', public: true },
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/Dashboard.vue'),
        meta: { title: '知识花园' },
      },
      {
        path: 'notes',
        name: 'Notes',
        component: () => import('@/views/notes/Notes.vue'),
        meta: { title: '笔记' },
      },
      {
        path: 'notes/category',
        name: 'NoteCategory',
        component: () => import('@/views/notes/NoteCategory.vue'),
        meta: { title: '笔记分类' },
      },
      {
        path: 'graph',
        name: 'GraphViewer',
        component: () => import('@/views/graph/GraphViewer.vue'),
        meta: { title: '知识图谱' },
      },
      {
        path: 'knowledge/book/:bookId',
        name: 'BookDetail',
        component: () => import('@/views/graph/BookDetail.vue'),
        meta: { title: '知识书详情' },
      },
      {
        path: 'reflection',
        name: 'Reflection',
        component: () => import('@/views/reflection/Reflection.vue'),
        meta: { title: '反思' },
      },
      {
        path: 'avatar',
        name: 'Avatar',
        component: () => import('@/views/avatar/Avatar.vue'),
        meta: { title: '数字分身' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/community',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})


export default router