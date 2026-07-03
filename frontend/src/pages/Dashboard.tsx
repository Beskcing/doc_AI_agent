import React, { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Card, Row, Col, Statistic, Table, Tag, Button, Space, Spin } from 'antd'
import {
  FileTextOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { getTaskStats } from '../services/api'

interface StatsData {
  stats: {
    total: number
    pending: number
    processing: number
    completed: number
    failed: number
    cancelled: number
  }
  recent_tasks: Array<{
    id: string
    filename: string
    standard: string
    status: string
    progress: number
    created_at: string
  }>
}

const Dashboard: React.FC = () => {
  const navigate = useNavigate()
  const [data, setData] = useState<StatsData | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true)
    try {
      const res = await getTaskStats()
      setData(res.data.data)
    } catch {
      // 静默失败
    } finally {
      if (showLoading) setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData(true) // 首次加载显示 loading
    const interval = setInterval(() => fetchData(false), 10000) // 轮询不显示 loading
    return () => clearInterval(interval)
  }, [fetchData])

  const stats = data?.stats || { total: 0, pending: 0, processing: 0, completed: 0, failed: 0, cancelled: 0 }

  const statCards = [
    { title: '总任务数', value: stats.total, icon: <FileTextOutlined style={{ color: '#1890ff', fontSize: 40 }} /> },
    { title: '已完成', value: stats.completed, icon: <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 40 }} /> },
    { title: '处理中', value: stats.processing, icon: <ClockCircleOutlined style={{ color: '#faad14', fontSize: 40 }} /> },
    { title: '失败', value: stats.failed, icon: <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 40 }} /> },
  ]

  const statusMap: Record<string, { text: string; color: string }> = {
    completed: { text: '已完成', color: 'success' },
    processing: { text: '处理中', color: 'processing' },
    failed: { text: '失败', color: 'error' },
    pending: { text: '待处理', color: 'default' },
    cancelled: { text: '已取消', color: 'warning' },
  }

  const columns = [
    { title: '文件名', dataIndex: 'filename', key: 'filename', ellipsis: true },
    { title: '排版规范', dataIndex: 'standard', key: 'standard', width: 150 },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={statusMap[status]?.color || 'default'}>
          {statusMap[status]?.text || status}
        </Tag>
      ),
    },
    { title: '进度', dataIndex: 'progress', key: 'progress', width: 80, render: (v: number) => `${v}%` },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180, render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-' },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>工作台</h2>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => fetchData(true)} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/upload')}>
            新建任务
          </Button>
        </Space>
      </div>

      {loading && !data ? (
        <div style={{ textAlign: 'center', padding: 100 }}>
          <Spin size="large" />
        </div>
      ) : (
        <>
          <Row gutter={16} style={{ marginBottom: 24 }}>
            {statCards.map((stat, index) => (
              <Col span={6} key={index}>
                <Card hoverable>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                    {stat.icon}
                    <Statistic title={stat.title} value={stat.value} />
                  </div>
                </Card>
              </Col>
            ))}
          </Row>

          <Card
            title="最近任务"
            extra={<Link to="/tasks">查看全部</Link>}
          >
            <Table
              dataSource={data?.recent_tasks || []}
              columns={columns}
              pagination={false}
              rowKey="id"
              onRow={(record) => ({
                onClick: () => navigate(`/tasks/${record.id}`),
                style: { cursor: 'pointer' },
              })}
            />
          </Card>
        </>
      )}
    </div>
  )
}

export default Dashboard
