import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Form, Input, Button, Typography, message, Space, Divider } from 'antd'
import { UserOutlined, LockOutlined, FileTextOutlined } from '@ant-design/icons'
import { login as loginApi, register as registerApi } from '../services/api'

const { Title, Text, Link } = Typography

const LoginPage: React.FC = () => {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()

  const handleSubmit = async (values: { username: string; password: string; confirmPassword?: string }) => {
    setLoading(true)
    try {
      if (mode === 'register') {
        if (values.password !== values.confirmPassword) {
          message.error('两次密码不一致')
          setLoading(false)
          return
        }
        const res = await registerApi({ username: values.username, password: values.password })
        const { access_token, refresh_token, user } = res.data
        localStorage.setItem('access_token', access_token)
        localStorage.setItem('refresh_token', refresh_token)
        if (user) localStorage.setItem('user_info', JSON.stringify(user))
        message.success('注册成功！')
        navigate('/', { replace: true })
      } else {
        const res = await loginApi({ username: values.username, password: values.password })
        const { access_token, refresh_token, user } = res.data
        localStorage.setItem('access_token', access_token)
        localStorage.setItem('refresh_token', refresh_token)
        if (user) localStorage.setItem('user_info', JSON.stringify(user))
        message.success(`欢迎回来，${user?.username || values.username}！`)
        navigate('/', { replace: true })
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '操作失败，请重试'
      message.error(msg)
    } finally {
      setLoading(false)
    }
  }

  const switchMode = () => {
    setMode(mode === 'login' ? 'register' : 'login')
    form.resetFields()
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      }}
    >
      <Card
        style={{
          width: 420,
          boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
          borderRadius: 12,
        }}
        bodyStyle={{ padding: '32px 40px' }}
      >
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <FileTextOutlined style={{ fontSize: 48, color: '#667eea' }} />
          <Title level={3} style={{ marginTop: 12, marginBottom: 4 }}>
            文档排版智能体
          </Title>
          <Text type="secondary">企业级国标文档结构化与排版平台</Text>
        </div>

        <Form form={form} onFinish={handleSubmit} size="large" autoComplete="off">
          <Form.Item
            name="username"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 3, max: 20, message: '用户名 3-20 位' },
              { pattern: /^[a-zA-Z0-9_]+$/, message: '仅支持字母、数字、下划线' },
            ]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 8, message: '密码至少 8 位' },
              ...(mode === 'register'
                ? [{ pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$/, message: '需含大小写字母和数字' }]
                : []),
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>

          {mode === 'register' && (
            <Form.Item
              name="confirmPassword"
              dependencies={['password']}
              rules={[
                { required: true, message: '请确认密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) return Promise.resolve()
                    return Promise.reject(new Error('两次密码不一致'))
                  },
                }),
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="确认密码" />
            </Form.Item>
          )}

          <Form.Item style={{ marginBottom: 12 }}>
            <Button type="primary" htmlType="submit" loading={loading} block>
              {mode === 'login' ? '登录' : '注册'}
            </Button>
          </Form.Item>
        </Form>

        <Divider style={{ margin: '12px 0' }} />

        <div style={{ textAlign: 'center' }}>
          <Space>
            <Text type="secondary">
              {mode === 'login' ? '还没有账号？' : '已有账号？'}
            </Text>
            <Link onClick={switchMode} style={{ cursor: 'pointer' }}>
              {mode === 'login' ? '立即注册' : '去登录'}
            </Link>
          </Space>
        </div>
      </Card>
    </div>
  )
}

export default LoginPage
