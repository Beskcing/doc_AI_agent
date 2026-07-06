import { Routes, Route } from 'react-router-dom'
import AppLayout from './components/AppLayout'
import Dashboard from './pages/Dashboard'
import UploadPage from './pages/UploadPage'
import TasksPage from './pages/TasksPage'
import TaskDetailPage from './pages/TaskDetailPage'
import ChatPage from './pages/ChatPage'
import KbPage from './pages/KbPage'
import ConfigPage from './pages/ConfigPage'
import TemplatesPage from './pages/TemplatesPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<AppLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="upload" element={<UploadPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="tasks/:taskId" element={<TaskDetailPage />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="templates" element={<TemplatesPage />} />
        <Route path="kb" element={<KbPage />} />
        <Route path="config" element={<ConfigPage />} />
      </Route>
    </Routes>
  )
}

export default App
