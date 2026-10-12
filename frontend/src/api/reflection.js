import request from './request'

export const reflectionApi = {
  getTodayQuestions: () => request.get('/reflection/today'),
  submitAnswer: (data) => request.post('/reflection/answer', data),
  getHistory: (params) => request.get('/reflection/history', { params }),
  getMastery: () => request.get('/reflection/mastery'),
}