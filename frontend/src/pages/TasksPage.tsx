import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  Table,
  Tag,
  Button,
  Space,
  message,
  Popconfirm,
  Progress,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { listTasks, cancelTask } from '../services/api'

interface TaskItem {
  key: string
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
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [loading, setLoading] = useState(false)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10, total: 0 })

  const fetchTasks = async (page = 1, pageSize = 10) => {
    setLoading(true)
    try {
      const res = await listTasks({ page, page_size: pageSize })
      const data = res.data.data
      setTasks(
        data.items.map((item: TaskItem) => ({
          ...item,
          key: item.id,
        }))
      )
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
  }

  useEffect(() => {
    fetchTasks()
    // 轮询刷新
    const interval = setInterval(() => fetchTasks(pagination.current, pagination.pageSize), 3000)
    return () => clearInterval(interval)
  }, [pagination.current, pagination.pageSize])

  const handleCancel = async (taskId: string) => {
    try {
      await cancelTask(taskId)
      message.success('任务已取消')
      fetchTasks()
    } catch (error: any) {
      message.error(error.message || '取消失败')
    }
  }

  const columns: ColumnsType<TaskItem> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 250, ellipsis: true },
    { title: '文件名', dataIndex: 'filename', key: 'filename' },
    { title: '排版规范', dataIndex: 'standard', key: 'standard', width: 150 },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
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
        ) : (
          <Progress percent={progress} size="small" />
        ),
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_, record) => (
        <Space size="small">
          <Link to={`/tasks/${record.id}`}>
            <Button type="link" size="small">
              详情
            </Button>
          </Link>
          {record.status === 'processing' && (
            <Popconfirm
              title="确认取消?"
              onConfirm={() => handleCancel(record.id)}
            >
              <Button type="link" danger size="small">
                取消
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <h2>任务管理</h2>
      <Table
        columns={columns}
        dataSource={tasks}
        loading={loading}
        pagination={{
          ...pagination,
          onChange: (page, pageSize) => {
            setPagination((prev) => ({ ...prev, current: page, pageSize: pageSize || 10 }))
            fetchTasks(page, pageSize || 10)
          },
        }}
      />
    </div>
  )
}

export default TasksPage
