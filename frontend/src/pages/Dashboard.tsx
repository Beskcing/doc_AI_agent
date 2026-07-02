import React from 'react'
import { Link } from 'react-router-dom'
import { Card, Row, Col, Statistic, Table, Tag } from 'antd'
import {
  FileTextOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons'

const Dashboard: React.FC = () => {
  // 统计数据
  const stats = [
    {
      title: '总任务数',
      value: 128,
      icon: <FileTextOutlined style={{ color: '#1890ff', fontSize: 40 }} />,
    },
    {
      title: '已完成',
      value: 96,
      icon: <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 40 }} />,
    },
    {
      title: '处理中',
      value: 12,
      icon: <ClockCircleOutlined style={{ color: '#faad14', fontSize: 40 }} />,
    },
    {
      title: '失败',
      value: 4,
      icon: <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 40 }} />,
    },
  ]

  // 最近任务
  const recentTasks = [
    { key: '1', id: 'task-001', filename: '示例公文.pdf', standard: 'GB/T 9704', status: 'completed', created_at: '2024-12-01 10:30:00' },
    { key: '2', id: 'task-002', filename: '技术报告.pdf', standard: 'GB/T 7713', status: 'processing', created_at: '2024-12-01 09:15:00' },
    { key: '3', id: 'task-003', filename: '扫描件_乱码.pdf', standard: '自定义规范', status: 'failed', created_at: '2024-11-30 16:20:00' },
  ]

  const statusMap: Record<string, { text: string; color: string }> = {
    completed: { text: '已完成', color: 'success' },
    processing: { text: '处理中', color: 'processing' },
    failed: { text: '失败', color: 'error' },
    pending: { text: '待处理', color: 'default' },
  }

  const columns = [
    { title: '文件名', dataIndex: 'filename', key: 'filename' },
    { title: '排版规范', dataIndex: 'standard', key: 'standard' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={statusMap[status]?.color || 'default'}>
          {statusMap[status]?.text || status}
        </Tag>
      ),
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
  ]

  return (
    <div>
      <h2>工作台</h2>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        {stats.map((stat, index) => (
          <Col span={6} key={index}>
            <Card>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                {stat.icon}
                <Statistic title={stat.title} value={stat.value} />
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <Card title="最近任务" extra={<Link to="/tasks">查看全部</Link>}>
        <Table dataSource={recentTasks} columns={columns} pagination={false} />
      </Card>
    </div>
  )
}

export default Dashboard
