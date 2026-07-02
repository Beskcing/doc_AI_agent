import React, { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  Card,
  Descriptions,
  Tag,
  Progress,
  Button,
  message,
  Spin,
  Space,
  Timeline,
} from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { getTask } from '../services/api'

interface TaskDetail {
  id: string
  filename: string
  standard: string
  status: string
  progress: number
  current_step: string
  created_at: string
  updated_at: string
  completed_at: string | null
  error_message: string | null
}

const TaskDetailPage: React.FC = () => {
  const { taskId } = useParams<{ taskId: string }>()
  const [task, setTask] = useState<TaskDetail | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchTask = async () => {
    if (!taskId) return
    try {
      const res = await getTask(taskId)
      setTask(res.data.data)
    } catch (error: any) {
      message.error(error.message || '获取任务详情失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTask()
    const interval = setInterval(fetchTask, 2000)
    return () => clearInterval(interval)
  }, [taskId])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" tip="加载中..." />
      </div>
    )
  }

  if (!task) {
    return <div>任务不存在</div>
  }

  const statusColor: Record<string, string> = {
    completed: 'success',
    processing: 'processing',
    failed: 'error',
    pending: 'default',
    cancelled: 'warning',
  }

  return (
    <div>
      <Space style={{ marginBottom: 24 }}>
        <Link to="/tasks">
          <Button icon={<ArrowLeftOutlined />}>返回</Button>
        </Link>
        <h2 style={{ margin: 0 }}>任务详情</h2>
      </Space>

      <Card title="基本信息" style={{ marginBottom: 24 }}>
        <Descriptions bordered>
          <Descriptions.Item label="任务 ID" span={3}>
            {task.id}
          </Descriptions.Item>
          <Descriptions.Item label="文件名" span={1}>
            {task.filename}
          </Descriptions.Item>
          <Descriptions.Item label="排版规范" span={1}>
            {task.standard}
          </Descriptions.Item>
          <Descriptions.Item label="状态" span={1}>
            <Tag color={statusColor[task.status] || 'default'}>{task.status}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="进度" span={3}>
            <Progress percent={task.progress} status={task.status === 'processing' ? 'active' : undefined} />
          </Descriptions.Item>
          <Descriptions.Item label="当前步骤" span={1}>
            {task.current_step || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间" span={1}>
            {task.created_at}
          </Descriptions.Item>
          <Descriptions.Item label="更新时间" span={1}>
            {task.updated_at}
          </Descriptions.Item>
          {task.completed_at && (
            <Descriptions.Item label="完成时间" span={3}>
              {task.completed_at}
            </Descriptions.Item>
          )}
          {task.error_message && (
            <Descriptions.Item label="错误信息" span={3}>
              <Tag color="error">{task.error_message}</Tag>
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      <Card title="处理流程">
        <Timeline
          items={[
            { children: '解析输入文档' },
            { children: '分析文档意图' },
            { children: '审查 Markdown 内容' },
            { children: '提取排版样式' },
            { children: '校验输出' },
            { children: '生成 Word 文档' },
          ]}
        />
      </Card>
    </div>
  )
}

export default TaskDetailPage
