import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import ChatPage from './pages/ChatPage'
import RegistryPage from './pages/RegistryPage'
import DashboardPage from './pages/DashboardPage'
import SystemLogsPage from './pages/SystemLogsPage'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/registry" element={<RegistryPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/logs" element={<SystemLogsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}

