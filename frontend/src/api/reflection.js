import request from './request'

export const reflectionApi = {
  getTodayQuestions: () => request.get('/reflection/today'),
  generateTodayQuestions: () => request.post('/reflection/today/generate'),
  // 针对单个知识点「再来一题」加练（每日加练有上限，超额时后端返回 404）
  generateMore: (nodeId) => request.post('/reflection/questions/more', { node_id: nodeId }),
  submitAnswer: (data) => request.post('/reflection/answer', data),
  getHistory: (params) => request.get('/reflection/history', { params }),
  getMastery: () => request.get('/reflection/mastery'),
  getNodeMastery: (nodeId) => request.get(`/reflection/nodes/${nodeId}/mastery`),
  getSchedule: () => request.get('/reflection/schedule'),
  updateSchedule: (data) => request.put('/reflection/schedule', data),
}