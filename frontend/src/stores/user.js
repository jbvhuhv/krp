import { defineStore } from 'pinia'


const TOKEN_KEY = 'krp_token'
const USER_KEY = 'krp_user'

function readUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch (error) {
    return null
  }
}

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    user: readUser(),
    isLoginModalVisible: false,
    refreshTick: 0,
  }),
  getters: {
    isLoggedIn: (state) => Boolean(state.token),
    userId: (state) => state.user?.id || '',
    nickname: (state) => state.user?.nickname || '',
    maskedPhone: (state) => {
      const phone = state.user?.phone
      if (!phone || phone.length < 7) return '未登录'
      return phone.slice(0, 3) + '****' + phone.slice(-4)
    },
    displayName() {
      return this.nickname || this.maskedPhone
    },
  },
  actions: {
    setToken(token) {
      this.token = token || ''
      if (token) {
        localStorage.setItem(TOKEN_KEY, token)
      } else {
        localStorage.removeItem(TOKEN_KEY)
      }
    },
    setUser(user) {
      this.user = user || null
      if (user) {
        localStorage.setItem(USER_KEY, JSON.stringify(user))
      } else {
        localStorage.removeItem(USER_KEY)
      }
    },
    openLoginModal() {
      this.isLoginModalVisible = true
    },
    requestRefresh() {
      this.refreshTick++
    },
    closeLoginModal() {
      this.isLoginModalVisible = false
    },
    async sendCode(phone) {
      const { authApi } = await import('@/api')
      return authApi.sendCode(phone)
    },
    async login(payload) {
      const { authApi } = await import('@/api')
      const data = await authApi.login(payload)
      this.setToken(data.access_token)
      return data
    },
    async fetchMe() {
      const { authApi } = await import('@/api')
      const user = await authApi.me()
      this.setUser(user)
      return user
    },
    async updateNickname(nickname) {
      const { authApi } = await import('@/api')
      const user = await authApi.updateMe({ nickname })
      this.setUser(user)
      return user
    },

    logout() {
      this.setToken('')
      this.setUser(null)
    },
  },
})