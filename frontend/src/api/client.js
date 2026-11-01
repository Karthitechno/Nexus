import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const client = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 120000,
})

client.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.detail || err.message || 'Unknown error'
    return Promise.reject(new Error(msg))
  }
)

// Health
export const getHealth = () => client.get('/api/health').then(r => r.data)

// Registry
export const getTools = (params = {}) => client.get('/api/tools', { params }).then(r => r.data)
export const getTool = (id) => client.get(`/api/tools/${id}`).then(r => r.data)
export const getRegistryStats = () => client.get('/api/tools/stats').then(r => r.data)
export const registerTool = (data) => client.post('/api/tools/register', data).then(r => r.data)
export const deleteTool = (id) => client.delete(`/api/tools/${id}`).then(r => r.data)
export const enableTool = (id) => client.post(`/api/tools/${id}/enable`).then(r => r.data)
export const disableTool = (id) => client.post(`/api/tools/${id}/disable`).then(r => r.data)
export const importCollection = (file) => {
  const form = new FormData()
  form.append('file', file)
  return client.post('/api/tools/import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data)
}

// Search
export const searchTools = (query, topK = 5) =>
  client.post('/api/tools/search', { query, top_k: topK }).then(r => r.data)

// Chat
export const sendChat = (query, threadId = null, stickyTools = []) =>
  client.post('/api/chat', { query, thread_id: threadId, session_sticky_tools: stickyTools }).then(r => r.data)
export const approveChat = (threadId, approved) =>
  client.post('/api/chat/approve', { thread_id: threadId, approved }).then(r => r.data)

// RAG
export const uploadDocument = (file) => {
  const form = new FormData()
  form.append('file', file)
  return client.post('/api/rag/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data)
}
export const queryRAG = (question, topK = 5) =>
  client.post('/api/rag/query', { question, top_k: topK }).then(r => r.data)
export const listDocuments = () => client.get('/api/rag/documents').then(r => r.data)

// System
export const systemSearch = (query) =>
  client.post('/api/system/search', { query }).then(r => r.data)
export const getLogs = (limit = 50) =>
  client.get('/api/system/logs', { params: { limit } }).then(r => r.data)
export const getLogById = (id) => client.get(`/api/system/logs/${id}`).then(r => r.data)
export const getPayPalStatus = () => client.get('/api/paypal/status').then(r => r.data)

// Benchmark
export const runBenchmark = (scales = [10, 50, 100]) =>
  client.post('/api/benchmark/run', { scales }).then(r => r.data)
export const getBenchmarkResults = () => client.get('/api/benchmark/results').then(r => r.data)

export default client

