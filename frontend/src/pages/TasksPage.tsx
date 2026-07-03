import React, { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Table,
  Tag,
  Button,
  Space,
  message,
  Popconfirm,
  Progress,
  Select,
} from 'antd'
import {
  PlusOutlined,
  ReloadOutlined,
  RetweetOutlined,
  EyeOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { listTasks, cancelTask, retryTask } from '../services/api'

interface TaskItem {
  id: string
  filename: string
  standard: string
  status: string
  progress: number
  created_at: string
  error_message?: string
}

const statusMap: Record<string, { text: string; color: string }> = {
  completed: { text: '已完成', color: 'success' },
  processing: { text: '处理中', color: 'processing' },
  failed: { text: '失败', color: 'error' },
  pending: { text: '待处理', color: 'default' },
  cancelled: { text: '已取消', color: 'warning' },
}

const TasksPage: React.FC = () => {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [loading, setLoading] = useState(false)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10, total: 0 })
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)

  const fetchTasks = useCallback(async (page = 1, pageSize = 10, status?: string) => {
    setLoading(true)
    try {
      const res = await listTasks({ page, page_size: pageSize, status })
      const data = res.data.data
      setTasks(data.items || [])
      setPagination({
        current: data.page,
        pageSize: data.page_size,
        total: data.total,
      })
    } catch (error: any) {
      message.error(error.message || '获取任务列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchTasks(pagination.current, pagination.pageSize, statusFilter)
    const hasActive = tasks.some((t) => t.status === 'processing' || t.status === 'pending')
    const interval = setInterval(() => {
      fetchTasks(pagination.current, pagination.pageSize, statusFilter)
    }, hasActive ? 3000 : 10000)
    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pagination.current, pagination.pageSize, statusFilter])

  const handleCancel = async (taskId: string) => {
    try {
      await cancelTask(taskId)
      message.success('任务已取消')
      fetchTasks(pagination.current, pagination.pageSize, statusFilter)
    } catch (error: any) {
      message.error(error.message || '取消失败')
    }
  }

  const handleRetry = async (taskId: string) => {
    try {
      await retryTask(taskId)
      message.success('任务已重新提交')
      fetchTasks(pagination.current, pagination.pageSize, statusFilter)
    } catch (error: any) {
      message.error(error.message || '重试失败')
    }
  }

  const columns: ColumnsType<TaskItem> = [
    {
      title: '文件名',
      dataIndex: 'filename',
      key: 'filename',
      ellipsis: true,
      render: (text: string, record: TaskItem) => (
        <Link to={`/tasks/${record.id}`}>{text}</Link>
      ),
    },
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
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      width: 150,
      render: (progress: number, record: TaskItem) =>
        record.status === 'processing' ? (
          <Progress percent={progress} size="small" status="active" />
        ) : record.status === 'failed' ? (
          <Progress percent={progress} size="small" status="exception" />
        ) : (
          <Progress percent={progress} size="small" />
        ),
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
    {
      title: '操作',
      key: 'action',
      width: 220,
      render: (_, record: TaskItem) => (
        <Space size="small">
          <Link to={`/tasks/${record.id}`}>
            <Button type="link" size="small" icon={<EyeOutlined />}>
              详情
            </Button>
          </Link>
          {(record.status === 'processing' || record.status === 'pending') && (
            <Popconfirm title="确认取消?" onConfirm={() => handleCancel(record.id)}>
              <Button type="link" danger size="small">
                取消
              </Button>
            </Popconfirm>
          )}
          {(record.status === 'failed' || record.status === 'cancelled') && (
            <Button
              type="link"
              size="small"
              icon={<RetweetOutlined />}
              onClick={() => handleRetry(record.id)}
            >
              重试
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>任务管理</h2>
        <Space>
          <Select
            placeholder="状态筛选"
            allowClear
            style={{ width: 150 }}
            value={statusFilter}
            onChange={(val) => {
              setStatusFilter(val)
              fetchTasks(1, pagination.pageSize, val)
            }}
            options={[
              { value: 'pending', label: '待处理' },
              { value: 'processing', label: '处理中' },
              { value: 'completed', label: '已完成' },
              { value: 'failed', label: '失败' },
              { value: 'cancelled', label: '已取消' },
            ]}
          />
          <Button
            icon={<ReloadOutlined />}
            onClick={() => fetchTasks(pagination.current, pagination.pageSize, statusFilter)}
            loading={loading}
          >
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/upload')}>
            新建任务
          </Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={tasks}
        rowKey="id"
        loading={loading}
        pagination={{
          current: pagination.current,
          pageSize: pagination.pageSize,
          total: pagination.total,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (page, pageSize) => {
            fetchTasks(page, pageSize || 10, statusFilter)
          },
        }}
      />
    </div>
  )
}

export default TasksPage
