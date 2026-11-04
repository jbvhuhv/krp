import request from './request'

// 复用统一实例的 baseURL，避免在流式接口里再硬编码一份 '/api/v1'：
// 一旦部署前缀或环境变量调整，普通接口与流式接口会走岔。
const BASE_URL = request.defaults.baseURL || '/api/v1'

/** 401 处理与 request.js 的拦截器保持一致：清凭据 + 弹登录框。 */
function handleUnauthorized() {
  localStorage.removeItem('krp_token')
  localStorage.removeItem('krp_user')
  import('@/stores/user').then(({ useUserStore }) => {
    const userStore = useUserStore()
    userStore.logout()
    userStore.openLoginModal()
  })
}

export const brainstormApi = {
  verify: (data) => request.post('/brainstorm/verify', data),
  suggest: (data) => request.post('/brainstorm/suggest', data),

  /**
   * 流式构思（SSE）。
   *
   * @param {object} data 请求体
   * @param {(msg: object) => void} onMessage 每解析出一帧就回调
   * @param {{ signal?: AbortSignal }} [options] 关闭面板/切换节点时传入，及时断流
   */
  async suggestStream(data, onMessage, options = {}) {
    const { signal } = options
    if (signal?.aborted) throw new DOMException('已取消', 'AbortError')

    const token = localStorage.getItem('krp_token')
    const resp = await fetch(`${BASE_URL}/brainstorm/suggest/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(data),
      signal,
    })

    if (resp.status === 401) {
      handleUnauthorized()
      throw new Error('登录已过期，请重新登录')
    }
    if (!resp.ok || !resp.body) {
      // fetch 不走 axios 拦截器，错误文案要自己兜：优先用后端返回的 detail
      let detail = ''
      try {
        detail = (await resp.json())?.detail || ''
      } catch {
        /* 响应体不是 JSON（网关错误页等），忽略 */
      }
      throw new Error(detail || `请求失败（HTTP ${resp.status}）`)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            onMessage(JSON.parse(line.slice(6)))
          } catch {
            /* 半包/畸形帧：跳过，等下一块数据补齐 */
          }
        }
      }
    } finally {
      // 主动取消时释放连接，避免后端继续生成、前端连接悬挂
      reader.releaseLock?.()
    }
  },
}
