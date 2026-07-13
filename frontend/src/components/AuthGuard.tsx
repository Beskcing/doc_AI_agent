/**
 * 路由守卫组件 — JWT 鉴权
 *
 * 进入受保护路由前验证 Token 有效性：
 * - 无 Token 或 Token 失效 → 跳转登录页
 * - Token 有效 → 渲染子组件
 */

import React, { useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Spin } from 'antd'
import { getMe } from '../services/api'

const getAccessToken = (): string | null => localStorage.getItem('access_token')

interface AuthGuardProps {
  children: React.ReactNode
}

const AuthGuard: React.FC<AuthGuardProps> = ({ children }) => {
  const location = useLocation()
  const [status, setStatus] = useState<'loading' | 'authenticated' | 'unauthenticated'>('loading')

  useEffect(() => {
    const token = getAccessToken()
    if (!token) {
      setStatus('unauthenticated')
      return
    }

    // 验证 token 是否有效（向 /api/auth/me 发请求）
    getMe()
      .then((res) => {
        // 更新 localStorage 中的用户信息
        if (res.data) {
          localStorage.setItem('user_info', JSON.stringify(res.data))
        }
        setStatus('authenticated')
      })
      .catch(() => {
        // Token 无效，清除并跳转登录
        localStorage.clear()
        setStatus('unauthenticated')
      })
  }, [])

  if (status === 'loading') {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" tip="验证登录状态..." />
      </div>
    )
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <>{children}</>
}

export default AuthGuard
