/**
 * 应用入口 — 挂载 React 根节点
 *
 * 引入 BrowserRouter（SPA 路由）、antd ConfigProvider（中文国际化）。
 */

import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
// React 19 兼容补丁，必须在 antd 之前引入
import '@ant-design/v5-patch-for-react-19'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>
)
