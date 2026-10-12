import request from './request'

export const brainstormApi = {
  verify: (data) => request.post('/brainstorm/verify', data),
  suggest: (data) => request.post('/brainstorm/suggest', data),
}