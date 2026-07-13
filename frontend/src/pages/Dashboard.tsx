/**
 * 工作台页面 — 任务概览与统计
 *
 * 展示任务统计卡片、磁盘用量、最近任务列表，
 * 支持清理旧任务和快速新建任务。
 */

import React, { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Card, Row, Col, Statistic, Table, Tag, Button, Space, Spin, Modal, InputNumber, message, Tooltip } from 'antd'
import {
  FileTextOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  HddOutlined,
  DeleteOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { getTaskStats, getDiskUsage, cleanupOldTasks } from '../services/api'

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

interface DiskUsage {
  output_mb: number
  uploads_mb: number
  total_mb: number
  output_task_count: number
  orphaned_count: number
}

const Dashboard: React.FC = () => {
  const navigate = useNavigate()
  const [data, setData] = useState<StatsData | null>(null)
  const [diskUsage, setDiskUsage] = useState<DiskUsage | null>(null)
  const [loading, setLoading] = useState(true)
  const [cleanupModalOpen, setCleanupModalOpen] = useState(false)
  const [cleanupDays, setCleanupDays] = useState(30)
  const [cleanupLoading, setCleanupLoading] = useState(false)

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

    // 后台获取磁盘用量（不阻塞 loading 状态）
    try {
      const diskRes = await getDiskUsage()
      setDiskUsage(diskRes.data.data)
    } catch {
      // 静默失败
    }
  }, [])

  useEffect(() => {
    fetchData(true) // 首次加载显示 loading
    const interval = setInterval(() => fetchData(false), 10000) // 轮询不显示 loading
    return () => clearInterval(interval)
  }, [fetchData])

  const handleCleanup = async () => {
    setCleanupLoading(true)
    try {
      const res = await cleanupOldTasks({ older_than_days: cleanupDays })
      const result = res.data.data
      const orphanInfo = result.orphaned_count > 0 ? `，含 ${result.orphaned_count} 个孤儿目录` : ''
      message.success(
        `已清理 ${result.deleted_count} 个目录，释放 ${result.freed_mb} MB（扫描 ${result.scanned_count} 个${orphanInfo}）`
      )
      setCleanupModalOpen(false)
      // 刷新数据
      fetchData(false)
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : '清理失败'
      message.error(errMsg)
    } finally {
      setCleanupLoading(false)
    }
  }

  const stats = data?.stats || { total: 0, pending: 0, processing: 0, completed: 0, failed: 0, cancelled: 0 }

  const formatDiskSize = (mb: number) => {
    if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`
    return `${mb.toFixed(0)} MB`
  }

  const diskUsageColor = diskUsage ? (diskUsage.total_mb > 500 ? '#ff4d4f' : diskUsage.total_mb > 200 ? '#faad14' : '#52c41a') : '#1890ff'

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
          <Tooltip title={diskUsage ? `磁盘占用: ${formatDiskSize(diskUsage.total_mb)}（${diskUsage.output_task_count} 个目录，含 ${diskUsage.orphaned_count} 个孤儿目录）` : '加载中...'}>
            <Button icon={<HddOutlined />}>
              磁盘 {diskUsage ? formatDiskSize(diskUsage.total_mb) : '...'}
            </Button>
          </Tooltip>
          <Button
            icon={<DeleteOutlined />}
            danger
            onClick={() => setCleanupModalOpen(true)}
            disabled={!diskUsage || diskUsage.output_task_count === 0}
          >
            清理旧文件
          </Button>
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
            <Col span={6}>
              <Card hoverable>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <HddOutlined style={{ color: diskUsageColor, fontSize: 40 }} />
                  <Statistic
                    title="磁盘占用"
                    value={diskUsage ? formatDiskSize(diskUsage.total_mb) : '...'}
                    valueStyle={{ color: diskUsageColor }}
                  />
                </div>
              </Card>
            </Col>
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

      <Modal
        title="清理旧任务输出"
        open={cleanupModalOpen}
        onOk={handleCleanup}
        onCancel={() => setCleanupModalOpen(false)}
        confirmLoading={cleanupLoading}
        okText="立即清理"
        cancelText="取消"
        okButtonProps={{ danger: true }}
      >
        <p style={{ marginBottom: 16 }}>
          此操作将清理指定天数前的已完成/失败/取消任务的输出目录，
          <strong>但会保留任务历史记录</strong>（仅删除磁盘文件）。
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>清理</span>
          <InputNumber
            min={1}
            max={365}
            value={cleanupDays}
            onChange={(v) => setCleanupDays(v || 30)}
            style={{ width: 100 }}
          />
          <span>天前的任务输出</span>
        </div>
        <p style={{ marginTop: 12, color: '#888', fontSize: 12 }}>
          当前磁盘占用: {diskUsage ? formatDiskSize(diskUsage.total_mb) : '...'}，
          {diskUsage ? `${diskUsage.output_task_count} 个目录` : ''}
          {diskUsage && diskUsage.orphaned_count > 0
            ? `（含 ${diskUsage.orphaned_count} 个孤儿目录，无 DB 记录）`
            : ''}
        </p>
      </Modal>
    </div>
  )
}

export default Dashboard
