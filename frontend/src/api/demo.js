import request from './request'

export const demoApi = {
  /** 为空书架账号一键灌入静态示例（1 本书 + 1 条笔记），不调用任何模型 */
  bootstrap: () => request.post('/demo/bootstrap'),
}
