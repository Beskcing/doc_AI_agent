import React, { useState, useEffect } from 'react'
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
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import { getTaskStats } from '../services/api'

const { Header, Sider, Content } = Layout
const { Text } = Typography

type MenuItem = Required<MenuProps>['items'][number]

const menuItems: MenuItem[] = [
  { key: '/', icon: <DashboardOutlined />, label: '工作台' },
  { key: '/upload', icon: <UploadOutlined />, label: '文档上传' },
  { key: '/tasks', icon: <FileTextOutlined />, label: '任务管理' },
  { key: '/chat', icon: <MessageOutlined />, label: '对话排版' },
  { key: '/templates', icon: <FileExcelOutlined />, label: '模板管理' },
  { key: '/kb', icon: <DatabaseOutlined />, label: '知识库' },
  { key: '/config', icon: <SettingOutlined />, label: '系统配置' },
]

const AppLayout: React.FC = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)
  const [activeCount, setActiveCount] = useState(0)
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken()

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
      message.info('退出登录功能待开发')
    }
  }

  const userMenuItems: MenuItem[] = [
    { key: 'profile', icon: <UserOutlined />, label: '个人中心' },
    { key: 'settings', icon: <SettingOutlined />, label: '系统配置' },
    { type: 'divider' },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录' },
  ]

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
          items={menuItems}
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
                <Text>管理员</Text>
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
