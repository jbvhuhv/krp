import axios from 'axios'
import { ElMessage } from 'element-plus'


import logger from '@/utils/logger'

let hasAuthError = false

let lastErrorMsg = ''
let lastErrorAt = 0

const ERROR_DEDUPE_WINDOW = 2000
const ERROR_COLLAPSE_WINDOW = 400

export function notifyError(message) {
  const text = typeof message === 'string' ? message : message?.message || '操作失败'
  const now = Date.now()
  if (text === lastErrorMsg && now - lastErrorAt < ERROR_DEDUPE_WINDOW) return
  if (now - lastErrorAt < ERROR_COLLAPSE_WINDOW) return
  lastErrorMsg = text
  lastErrorAt = now
  ElMessage.error(text)
}


const request = axios.create({
  baseURL: '/api/v1',
  timeout: 90000,
})

request.interceptors.request.use(
  async (config) => {
    const token = localStorage.getItem('krp_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error.response?.status
    const body = error.response?.data
    const isTimeout = error.code === 'ECONNABORTED' || /timeout/i.test(error.message || '')
    const isNetwork = !error.response
    const detail =
      body?.detail ||
      (isTimeout ? '请求超时，请稍后重试' : isNetwork ? '网络异常，请检查网络后重试' : '请求失败')
    const traceId = body?.trace_id || error.response?.headers?.['x-trace-id']
    if (status === 500) {
      logger.error(
        `[后端500] trace_id=${traceId || '未知'} | ${error.config?.method?.toUpperCase()} ${error.config?.url}`,
      )
    }
    const silentAuth = error.config?.silentAuth
    const silent = error.config?.silent
    if (status === 401 && !silentAuth) {
      localStorage.removeItem('krp_token')
      localStorage.removeItem('krp_user')
      if (!hasAuthError) {
        hasAuthError = true
        import('@/stores/user').then(({ useUserStore }) => {
          const userStore = useUserStore()
          userStore.logout()
          userStore.openLoginModal()
        })
      }
    } else if (status !== 401 && !silent) {
      notifyError(detail)
    }
    return Promise.reject(error)
  },
)


export function resetAuthError() {
  hasAuthError = false
}

export default request