import request from './request'

export const reflectionApi = {
  getTodayQuestions: () => request.get('/reflection/today'),
  generateTodayQuestions: () => request.post('/reflection/today/generate'),
  submitAnswer: (data) => request.post('/reflection/answer', data),
  getHistory: (params) => request.get('/reflection/history', { params }),
  getMastery: () => request.get('/reflection/mastery'),
  getNodeMastery: (nodeId) => request.get(`/reflection/nodes/${nodeId}/mastery`),
  getSchedule: () => request.get('/reflection/schedule'),
  updateSchedule: (data) => request.put('/reflection/schedule', data),
}