import request from './request'

export const graphApi = {
  getGraph: (userId, subject, noteId) => {
    const params = {}
    if (subject) params.subject = subject
    if (noteId) params.note_id = noteId
    return request.get(`/graph/${userId}`, { params })
  },
  getBooks: () => request.get('/graph/books'),
  getTree: (bookId) => request.get(`/graph/tree/${bookId}`),
  getSubjectStats: () => request.get('/graph/subject-stats'),
  getStudyProfile: () => request.get('/graph/study-profile'),
  createNode: (data) => request.post('/graph/nodes', data),
  createCategory: (data) => request.post('/graph/categories', data),
  createKnowledge: (data) => request.post('/graph/knowledge', data),
  updateNode: (nodeId, data) => request.put(`/graph/nodes/${nodeId}`, data),
  deleteNode: (nodeId) => request.delete(`/graph/nodes/${nodeId}`),
  createEdge: (data) => request.post('/graph/edges', data),
  getNodeSource: (nodeId) => request.get(`/graph/nodes/${nodeId}/source`),
  recordView: (nodeId) => request.post(`/graph/nodes/${nodeId}/view`),
  generateSummary: (nodeId) => request.post(`/graph/nodes/${nodeId}/ai-summary`),
}