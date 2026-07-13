/**
 * 应用主布局 — 侧边栏 + 顶栏 + 内容区
 *
 * 功能：
 * - 可折叠侧边栏菜单（根据用户角色过滤管理员菜单）
 * - 顶栏任务徽标 + 用户下拉菜单
 * - 通过 <Outlet /> 渲染子路由
 */

import React, { useState, useEffect, useMemo } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  Layout,
  Menu,
  theme,
  Button,
  Badge,
  Space,
  Typography,
  Avatar,
  Dropdown,
  message,
} from 'antd'
import {
  DashboardOutlined,
  UploadOutlined,
  FileTextOutlined,
  DatabaseOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined,
  DownOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BellOutlined,
  MessageOutlined,
  FileExcelOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import { getTaskStats } from '../services/api'

const { Header, Sider, Content } = Layout
const { Text } = Typography

type MenuItem = Required<MenuProps>['items'][number]

const AppLayout: React.FC = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)
  const [activeCount, setActiveCount] = useState(0)
  const [username, setUsername] = useState<string>('用户')
  const [userRole, setUserRole] = useState<string>('user')
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken()

  // 从 localStorage 读取用户信息
  useEffect(() => {
    try {
      const raw = localStorage.getItem('user_info')
      if (raw) {
        const info = JSON.parse(raw)
        setUsername(info.username || '用户')
        setUserRole(info.role || 'user')
      }
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    const fetchActiveCount = async () => {
      try {
        const res = await getTaskStats()
        const stats = res.data.data.stats
        setActiveCount((stats.processing || 0) + (stats.pending || 0))
      } catch {
        // 静默
      }
    }
    fetchActiveCount()
    const interval = setInterval(fetchActiveCount, 10000)
    return () => clearInterval(interval)
  }, [])

  const selectedKeys = [location.pathname]

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    navigate(key)
  }

  const handleUserMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key === 'profile') {
      message.info('个人中心功能待开发')
    } else if (key === 'settings') {
      navigate('/config')
    } else if (key === 'logout') {
      localStorage.clear()
      message.success('已退出登录')
      navigate('/login', { replace: true })
    }
  }

  const userMenuItems: MenuItem[] = [
    { key: 'profile', icon: <UserOutlined />, label: username },
    { key: 'settings', icon: <SettingOutlined />, label: '系统配置' },
    { type: 'divider' },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
  ]

  // 根据角色过滤菜单项
  const filteredMenuItems = useMemo(() => {
    const allItems: MenuItem[] = [
      { key: '/', icon: <DashboardOutlined />, label: '工作台' },
      { key: '/upload', icon: <UploadOutlined />, label: '文档上传' },
      { key: '/tasks', icon: <FileTextOutlined />, label: '任务管理' },
      { key: '/chat', icon: <MessageOutlined />, label: '对话排版' },
      { key: '/templates', icon: <FileExcelOutlined />, label: '模板管理' },
      ...(userRole === 'admin'
        ? [
            { key: '/kb', icon: <DatabaseOutlined />, label: '知识库' },
            { key: '/config', icon: <SettingOutlined />, label: '系统配置' },
            { key: '/admin/users', icon: <TeamOutlined />, label: '用户管理' },
          ]
        : []),
    ]
    return allItems
  }, [userRole])

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        theme="dark"
        width={220}
        style={{
          position: 'fixed',
          height: '100vh',
          left: 0,
          top: 0,
          bottom: 0,
          zIndex: 100,
        }}
      >
        <div style={{ height: 64, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Text
            style={{
              color: '#fff',
              fontSize: collapsed ? 14 : 18,
              fontWeight: 'bold',
              whiteSpace: 'nowrap',
            }}
          >
            {collapsed ? '排版' : '文档排版智能体'}
          </Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={selectedKeys}
          items={filteredMenuItems}
          onClick={handleMenuClick}
          style={{ borderRight: 0 }}
        />
      </Sider>

      <Layout style={{ marginLeft: collapsed ? 80 : 220, transition: 'all 0.2s' }}>
        <Header
          style={{
            padding: '0 24px',
            background: colorBgContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            position: 'sticky',
            top: 0,
            zIndex: 99,
            boxShadow: '0 1px 4px rgba(0,0,0,0.05)',
          }}
        >
          <Space>
            <Button
              type="text"
              onClick={() => setCollapsed(!collapsed)}
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            />
            <Text strong style={{ fontSize: 16 }}>
              企业级国标文档结构化与排版智能体
            </Text>
          </Space>

          <Space size={16}>
            <Badge count={activeCount} size="small">
              <Button
                type="text"
                icon={<BellOutlined />}
                onClick={() => navigate('/tasks')}
              />
            </Badge>
            <Dropdown
              menu={{ items: userMenuItems, onClick: handleUserMenuClick }}
              placement="bottomRight"
            >
              <Space style={{ cursor: 'pointer' }}>
                <Avatar icon={<UserOutlined />} size="small" />
                <Text>{username}</Text>
                <DownOutlined style={{ fontSize: 12 }} />
              </Space>
            </Dropdown>
          </Space>
        </Header>

        <Content
          style={{
            margin: '16px',
            padding: 24,
            background: colorBgContainer,
            borderRadius: borderRadiusLG,
            minHeight: 'calc(100vh - 112px)',
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}

export default AppLayout
