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
  // 导出思维导图：后端回 .docx 字节流；bookIds 为空时导整个书架
  // 数组参数手动拼串：axios 默认会序列化成 book_ids[]=a，FastAPI 不认这个键名
  exportMindmap: (bookIds) => {
    const query = (bookIds || [])
      .filter(Boolean)
      .map((id) => `book_ids=${encodeURIComponent(id)}`)
      .join('&')
    return request.get(`/graph/export/mindmap${query ? `?${query}` : ''}`, {
      responseType: 'blob',
      timeout: 60000,
    })
  },
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