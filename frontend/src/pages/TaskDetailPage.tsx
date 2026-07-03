import React, { useState, useEffect, useCallback } from 'react'
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
  Tabs,
  Empty,
  Modal,
  Select,
} from 'antd'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  ArrowLeftOutlined,
  DownloadOutlined,
  EyeOutlined,
  ReloadOutlined,
  FileWordOutlined,
  FileTextOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { getTask, previewTask, getDownloadUrl, getDocxPreviewUrl, retryTask, getMineruDocxDownloadUrl, getMineruDocxPreviewUrl, listTemplates, applyTemplateToTask } from '../services/api'

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
  result_path: string | null
  cleaned_markdown_preview: string | null
  style_config_preview: Record<string, unknown> | null
  mineru_docx_available: boolean
}

const statusColor: Record<string, string> = {
  completed: 'success',
  processing: 'processing',
  failed: 'error',
  pending: 'default',
  cancelled: 'warning',
}

const statusText: Record<string, string> = {
  completed: '已完成',
  processing: '处理中',
  failed: '失败',
  pending: '待处理',
  cancelled: '已取消',
}

const WORKFLOW_STEPS = [
  { key: 'parse_input', label: '解析输入文档' },
  { key: 'analyze_intent', label: '分析文档意图' },
  { key: 'review_content', label: '审查 Markdown 内容' },
  { key: 'extract_style', label: '提取排版样式' },
  { key: 'prepare_docx', label: '准备基础 DOCX' },
  { key: 'apply_style', label: '应用国标样式' },
]

const markdownComponents = {
  table: ({ node, ...props }: any) => (
    <table style={{ borderCollapse: 'collapse', width: '100%', margin: '12px 0' }} {...props} />
  ),
  th: ({ node, ...props }: any) => (
    <th style={{ border: '1px solid #d9d9d9', padding: '8px 12px', background: '#fafafa', textAlign: 'left' }} {...props} />
  ),
  td: ({ node, ...props }: any) => (
    <td style={{ border: '1px solid #d9d9d9', padding: '8px 12px' }} {...props} />
  ),
  img: ({ node, ...props }: any) => (
    <img style={{ maxWidth: '100%', margin: '8px 0' }} {...props} />
  ),
  code: ({ node, inline, ...props }: any) => (
    <code
      style={{
        background: '#f5f5f5',
        padding: inline ? '2px 6px' : '12px',
        borderRadius: 4,
        fontSize: 13,
        display: inline ? 'inline' : 'block',
        overflow: 'auto',
      }}
      {...props}
    />
  ),
}

const TaskDetailPage: React.FC = () => {
  const { taskId } = useParams<{ taskId: string }>()
  const [task, setTask] = useState<TaskDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [preview, setPreview] = useState<{ markdown_preview: string; style_config: Record<string, unknown> } | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('timeline')
  const [docxPreviewLoaded, setDocxPreviewLoaded] = useState(false)
  const [mineruDocxPreviewLoaded, setMineruDocxPreviewLoaded] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [templateModalVisible, setTemplateModalVisible] = useState(false)
  const [templates, setTemplates] = useState<Array<{ value: string; label: string }>>([])
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('')
  const [applyingTemplate, setApplyingTemplate] = useState(false)

  const loadTemplates = useCallback(async () => {
    try {
      const res = await listTemplates()
      if (res.data.data?.items) {
        setTemplates(res.data.data.items.map((t: { id: string; name: string }) => ({ value: t.id, label: t.name })))
      }
    } catch {
      // 静默
    }
  }, [])

  const fetchTask = useCallback(async () => {
    if (!taskId) return
    try {
      const res = await getTask(taskId)
      setTask(res.data.data)
    } catch (error: any) {
      message.error(error.message || '获取任务详情失败')
    } finally {
      setLoading(false)
    }
  }, [taskId])

  useEffect(() => {
    fetchTask()
    const interval = setInterval(fetchTask, 3000)
    return () => clearInterval(interval)
  }, [fetchTask])

  const fetchPreview = async () => {
    if (!taskId) return
    setPreviewLoading(true)
    try {
      const res = await previewTask(taskId)
      setPreview(res.data.data)
    } catch (error: any) {
      message.error(error.message || '获取预览失败')
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleDownload = () => {
    if (!taskId) return
    window.open(getDownloadUrl(taskId), '_blank')
  }

  const handleMineruDocxDownload = () => {
    if (!taskId) return
    window.open(getMineruDocxDownloadUrl(taskId), '_blank')
  }

  const handleRetry = async () => {
    if (!taskId) return
    setRetrying(true)
    try {
      await retryTask(taskId)
      message.success('任务已重新提交')
      fetchTask()
    } catch (error: any) {
      message.error(error.message || '重试失败')
    } finally {
      setRetrying(false)
    }
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" tip="加载中..." />
      </div>
    )
  }

  if (!task) {
    return <Empty description="任务不存在" />
  }

  const currentStepIndex = WORKFLOW_STEPS.findIndex((s) => s.key === task.current_step)

  const timelineItems = WORKFLOW_STEPS.map((step, idx) => {
    let color = 'gray'
    if (task.status === 'failed' && idx === Math.max(0, currentStepIndex)) {
      color = 'red'
    } else if (task.status === 'completed' || (currentStepIndex >= 0 && idx < currentStepIndex)) {
      color = 'green'
    } else if (idx === currentStepIndex && task.status === 'processing') {
      color = 'blue'
    }
    return { color, children: step.label }
  })

  const tabItems = [
    {
      key: 'timeline',
      label: '处理流程',
      children: (
        <Card>
          <Timeline items={timelineItems} />
        </Card>
      ),
    },
    {
      key: 'markdown',
      label: <span><FileTextOutlined /> Markdown 预览</span>,
      children: preview ? (
        <Card loading={previewLoading}>
          <div style={{
            padding: '8px 16px',
          }}>
            {preview.markdown_preview ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                {preview.markdown_preview}
              </ReactMarkdown>
            ) : (
              <Empty description="(无预览内容)" />
            )}
          </div>
          {preview.style_config && (
            <div style={{ marginTop: 16 }}>
              <h4>样式配置</h4>
              <pre style={{
                background: '#f5f5f5',
                padding: 16,
                borderRadius: 8,
                fontSize: 13,
                maxHeight: 300,
                overflow: 'auto',
              }}>
                {JSON.stringify(preview.style_config, null, 2)}
              </pre>
            </div>
          )}
        </Card>
      ) : (
        <Card>
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Button icon={<EyeOutlined />} onClick={fetchPreview} loading={previewLoading}>
              加载 Markdown 预览
            </Button>
          </div>
        </Card>
      ),
    },
  ]

  // 已完成的任务添加 Word 预览 Tab
  if (task.status === 'completed') {
    // MinerU 原始 DOCX 预览（仅当 MinerU DOCX 可用时显示）
    if (task.mineru_docx_available) {
      tabItems.push({
        key: 'mineru_docx',
        label: <span><FileWordOutlined /> MinerU 原始 DOCX</span>,
        children: (
          <Card>
            <div style={{ textAlign: 'center', marginBottom: 16 }}>
              <Space>
                <Button
                  icon={<EyeOutlined />}
                  onClick={() => setMineruDocxPreviewLoaded(true)}
                  type="primary"
                >
                  {mineruDocxPreviewLoaded ? '刷新预览' : '加载 MinerU DOCX 预览'}
                </Button>
                <Button icon={<DownloadOutlined />} onClick={handleMineruDocxDownload}>
                  下载 MinerU DOCX
                </Button>
              </Space>
            </div>
            {mineruDocxPreviewLoaded && (
              <div style={{
                border: '1px solid #d9d9d9',
                borderRadius: 8,
                overflow: 'hidden',
              }}>
                <iframe
                  src={getMineruDocxPreviewUrl(taskId!)}
                  style={{
                    width: '100%',
                    height: 'calc(100vh - 200px)',
                    minHeight: 600,
                    border: 'none',
                  }}
                  title="MinerU 原始 DOCX 预览"
                />
              </div>
            )}
          </Card>
        ),
      })
    }

    // 最终样式化后的 Word 预览
    tabItems.push({
      key: 'docx',
      label: <span><FileWordOutlined /> 排版后 Word 预览</span>,
      children: (
        <Card>
          <div style={{ textAlign: 'center', marginBottom: 16 }}>
            <Space>
              <Button
                icon={<EyeOutlined />}
                onClick={() => setDocxPreviewLoaded(true)}
                type="primary"
              >
                {docxPreviewLoaded ? '刷新预览' : '加载 Word 预览'}
              </Button>
              <Button icon={<DownloadOutlined />} onClick={handleDownload}>
                下载排版后 Word
              </Button>
            </Space>
          </div>
          {docxPreviewLoaded && (
            <div style={{
              border: '1px solid #d9d9d9',
              borderRadius: 8,
              overflow: 'hidden',
            }}>
              <iframe
                src={getDocxPreviewUrl(taskId!)}
                style={{
                  width: '100%',
                  height: 'calc(100vh - 200px)',
                  minHeight: 600,
                  border: 'none',
                }}
                title="排版后 Word 文档预览"
              />
            </div>
          )}
        </Card>
      ),
    })
  }

  return (
    <div>
      <Space style={{ marginBottom: 24, width: '100%', justifyContent: 'space-between' }}>
        <Space>
          <Link to="/tasks">
            <Button icon={<ArrowLeftOutlined />}>返回</Button>
          </Link>
          <h2 style={{ margin: 0 }}>任务详情</h2>
        </Space>
        <Space>
          {task.status === 'completed' && (
            <>
              <Button
                icon={<ThunderboltOutlined />}
                onClick={() => {
                  setTemplateModalVisible(true)
                  loadTemplates()
                }}
              >
                应用模板
              </Button>
              <Button
                icon={<EyeOutlined />}
                onClick={() => {
                  fetchPreview()
                  setActiveTab('markdown')
                }}
                loading={previewLoading}
              >
                预览结果
              </Button>
              <Button type="primary" icon={<DownloadOutlined />} onClick={handleDownload}>
                下载 Word
              </Button>
              {task.mineru_docx_available && (
                <Button icon={<FileWordOutlined />} onClick={handleMineruDocxDownload}>
                  MinerU 原始 DOCX
                </Button>
              )}
            </>
          )}
          {task.status === 'failed' && (
            <Button type="primary" icon={<ReloadOutlined />} onClick={handleRetry} loading={retrying}>
              重试
            </Button>
          )}
        </Space>
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
            <Tag color={statusColor[task.status] || 'default'}>
              {statusText[task.status] || task.status}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="进度" span={3}>
            <Progress
              percent={task.progress}
              status={task.status === 'processing' ? 'active' : task.status === 'failed' ? 'exception' : undefined}
            />
          </Descriptions.Item>
          <Descriptions.Item label="当前步骤" span={1}>
            {task.current_step || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间" span={1}>
            {task.created_at ? dayjs(task.created_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="更新时间" span={1}>
            {task.updated_at ? dayjs(task.updated_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
          </Descriptions.Item>
          {task.completed_at && (
            <Descriptions.Item label="完成时间" span={3}>
              {dayjs(task.completed_at).format('YYYY-MM-DD HH:mm:ss')}
            </Descriptions.Item>
          )}
          {task.error_message && (
            <Descriptions.Item label="错误信息" span={3}>
              <Tag color="error">{task.error_message}</Tag>
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      <Tabs items={tabItems} activeKey={activeTab} onChange={setActiveTab} />

      {/* 应用模板 Modal */}
      <Modal
        title="应用样式模板"
        open={templateModalVisible}
        onOk={async () => {
          if (!selectedTemplateId) {
            message.warning('请选择一个模板')
            return
          }
          setApplyingTemplate(true)
          try {
            await applyTemplateToTask(taskId!, { template_id: selectedTemplateId })
            message.success('模板应用成功')
            setTemplateModalVisible(false)
            setSelectedTemplateId('')
            fetchTask()
          } catch (err) {
            message.error(err instanceof Error ? err.message : '应用失败')
          } finally {
            setApplyingTemplate(false)
          }
        }}
        onCancel={() => setTemplateModalVisible(false)}
        okText="应用"
        cancelText="取消"
        confirmLoading={applyingTemplate}
      >
        <p style={{ marginBottom: 12 }}>
          选择一个样式模板，将重新渲染 DOCX 文件。此操作不会重新解析 PDF，仅重新应用排版样式。
        </p>
        <Select
          style={{ width: '100%' }}
          placeholder="选择样式模板"
          value={selectedTemplateId || undefined}
          onChange={setSelectedTemplateId}
          options={templates}
          showSearch
          optionFilterProp="label"
        />
      </Modal>
    </div>
  )
}

export default TaskDetailPage
