/**
 * 应用根组件 — 路由配置
 *
 * 公开路由：/login（登录/注册）
 * 受保护路由：由 AuthGuard 鉴权，AppLayout 提供侧边栏布局
 */

import { Routes, Route } from 'react-router-dom'
import AuthGuard from './components/AuthGuard'
import AppLayout from './components/AppLayout'
import Dashboard from './pages/Dashboard'
import UploadPage from './pages/UploadPage'
import TasksPage from './pages/TasksPage'
import TaskDetailPage from './pages/TaskDetailPage'
import ChatPage from './pages/ChatPage'
import KbPage from './pages/KbPage'
import ConfigPage from './pages/ConfigPage'
import TemplatesPage from './pages/TemplatesPage'
import LoginPage from './pages/LoginPage'
import AdminUsersPage from './pages/AdminUsersPage'

function App() {
  return (
    <Routes>
      {/* 公开路由：登录/注册 */}
      <Route path="/login" element={<LoginPage />} />
      {/* 受保护路由 */}
      <Route
        path="/"
        element={
          <AuthGuard>
            <AppLayout />
          </AuthGuard>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="upload" element={<UploadPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="tasks/:taskId" element={<TaskDetailPage />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="templates" element={<TemplatesPage />} />
        <Route path="kb" element={<KbPage />} />
        <Route path="config" element={<ConfigPage />} />
        <Route path="admin/users" element={<AdminUsersPage />} />
      </Route>
    </Routes>
  )
}

export default App
