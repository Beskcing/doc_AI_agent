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
  InputNumber,
  Collapse,
  Row,
  Col,
  Input,
  Typography,
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
  EditOutlined,
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

  // 修正样式
  const [editStyleModalVisible, setEditStyleModalVisible] = useState(false)
  const [editStyleConfig, setEditStyleConfig] = useState<Record<string, unknown> | null>(null)
  const [editJsonText, setEditJsonText] = useState('')
  const [editJsonError, setEditJsonError] = useState('')
  const [applyingStyle, setApplyingStyle] = useState(false)

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

  // Bug#6 修复：任务完成/失败后停止高频轮询
  const isTerminal = task?.status === 'completed' || task?.status === 'failed' || task?.status === 'cancelled'

  useEffect(() => {
    fetchTask()
    // 终态时降低轮询频率（30s），非终态时 3s 高频轮询
    const interval = setInterval(fetchTask, isTerminal ? 30000 : 3000)
    return () => clearInterval(interval)
  }, [fetchTask, isTerminal])

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

  // 打开修正样式 Modal：优先使用预览中的 style_config，没有则加载预览
  const handleOpenEditStyle = async () => {
    let config = preview?.style_config || task?.style_config_preview
    if (!config) {
      // 先加载预览获取 style_config
      if (!preview) {
        await fetchPreview()
      }
      config = preview?.style_config || task?.style_config_preview
    }
    if (!config) {
      message.warning('无法获取当前样式配置，请先点击「预览结果」加载')
      return
    }
    setEditStyleConfig({ ...config })
    setEditJsonText(JSON.stringify(config, null, 2))
    setEditJsonError('')
    setEditStyleModalVisible(true)
  }

  // 应用修正后的样式
  const handleApplyEditStyle = async () => {
    if (!taskId || !editStyleConfig) return

    // 验证 JSON
    let configToApply = editStyleConfig
    if (editJsonText.trim()) {
      try {
        configToApply = JSON.parse(editJsonText)
        setEditJsonError('')
      } catch {
        setEditJsonError('JSON 格式错误，请检查后再保存')
        return
      }
    }

    setApplyingStyle(true)
    try {
      await applyTemplateToTask(taskId, { style_config: configToApply })
      message.success('样式修正已应用，DOCX 已重新渲染')
      setEditStyleModalVisible(false)
      fetchTask()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '应用失败')
    } finally {
      setApplyingStyle(false)
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
                icon={<EditOutlined />}
                onClick={handleOpenEditStyle}
              >
                修正样式
              </Button>
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

      {/* 修正样式 Modal */}
      <Modal
        title="修正样式配置"
        open={editStyleModalVisible}
        onOk={handleApplyEditStyle}
        onCancel={() => setEditStyleModalVisible(false)}
        okText="应用并重新渲染"
        cancelText="取消"
        width={800}
        confirmLoading={applyingStyle}
      >
        <p style={{ marginBottom: 12, color: '#999' }}>
          修改样式配置后点击「应用」，将重新渲染 DOCX 文件。此操作不会重新解析 PDF，仅重新应用排版样式。
        </p>
        {editStyleConfig && (() => {
          const pl = editStyleConfig.page_layout as Record<string, unknown> | undefined
          const bs = editStyleConfig.body_style as Record<string, unknown> | undefined
          const bodyFont = bs?.font as Record<string, unknown> | undefined
          const ts = editStyleConfig.table_style as Record<string, unknown> | undefined

          const updateField = (section: string, field: string, value: unknown) => {
            const sectionData = editStyleConfig[section] as Record<string, unknown> | undefined
            const newConfig = { ...editStyleConfig, [section]: { ...sectionData, [field]: value } }
            setEditStyleConfig(newConfig)
            setEditJsonText(JSON.stringify(newConfig, null, 2))
          }
          const updateFontField = (section: string, field: string, value: unknown) => {
            const sectionData = editStyleConfig[section] as Record<string, unknown> | undefined
            const fontData = sectionData?.font as Record<string, unknown> | undefined
            const newConfig = { ...editStyleConfig, [section]: { ...sectionData, font: { ...fontData, [field]: value } } }
            setEditStyleConfig(newConfig)
            setEditJsonText(JSON.stringify(newConfig, null, 2))
          }

          return (
            <Collapse defaultActiveKey={['page', 'body', 'table', 'json']} size="small">
              <Collapse.Panel header="页面布局" key="page">
                <Row gutter={8}>
                  <Col span={8}>
                    <Typography.Text type="secondary">上边距(cm)</Typography.Text>
                    <InputNumber value={pl?.margin_top_cm as number} style={{ width: '100%' }} size="small" step={0.1} onChange={v => updateField('page_layout', 'margin_top_cm', v)} />
                  </Col>
                  <Col span={8}>
                    <Typography.Text type="secondary">下边距(cm)</Typography.Text>
                    <InputNumber value={pl?.margin_bottom_cm as number} style={{ width: '100%' }} size="small" step={0.1} onChange={v => updateField('page_layout', 'margin_bottom_cm', v)} />
                  </Col>
                  <Col span={8}>
                    <Typography.Text type="secondary">左边距(cm)</Typography.Text>
                    <InputNumber value={pl?.margin_left_cm as number} style={{ width: '100%' }} size="small" step={0.1} onChange={v => updateField('page_layout', 'margin_left_cm', v)} />
                  </Col>
                </Row>
                <Row gutter={8} style={{ marginTop: 8 }}>
                  <Col span={8}>
                    <Typography.Text type="secondary">右边距(cm)</Typography.Text>
                    <InputNumber value={pl?.margin_right_cm as number} style={{ width: '100%' }} size="small" step={0.1} onChange={v => updateField('page_layout', 'margin_right_cm', v)} />
                  </Col>
                </Row>
              </Collapse.Panel>

              <Collapse.Panel header="正文样式" key="body">
                <Row gutter={8}>
                  <Col span={8}>
                    <Typography.Text type="secondary">中文字体</Typography.Text>
                    <Input value={String(bodyFont?.east_asia_family || bodyFont?.family || '')} size="small" onChange={e => updateFontField('body_style', 'east_asia_family', e.target.value)} />
                  </Col>
                  <Col span={4}>
                    <Typography.Text type="secondary">字号(pt)</Typography.Text>
                    <InputNumber value={bodyFont?.size_pt as number} style={{ width: '100%' }} size="small" step={0.5} onChange={v => updateFontField('body_style', 'size_pt', v)} />
                  </Col>
                  <Col span={4}>
                    <Typography.Text type="secondary">加粗</Typography.Text>
                    <Select value={bodyFont?.bold ? 'yes' : 'no'} style={{ width: '100%' }} size="small" onChange={v => updateFontField('body_style', 'bold', v === 'yes')} options={[{ value: 'no', label: '否' }, { value: 'yes', label: '是' }]} />
                  </Col>
                  <Col span={4}>
                    <Typography.Text type="secondary">行距</Typography.Text>
                    <InputNumber value={bs?.line_spacing as number} style={{ width: '100%' }} size="small" step={0.1} onChange={v => updateField('body_style', 'line_spacing', v)} />
                  </Col>
                  <Col span={4}>
                    <Typography.Text type="secondary">首行缩进(字)</Typography.Text>
                    <InputNumber value={bs?.first_line_indent_chars as number} style={{ width: '100%' }} size="small" step={0.5} onChange={v => updateField('body_style', 'first_line_indent_chars', v)} />
                  </Col>
                </Row>
              </Collapse.Panel>

              {ts && (
                <Collapse.Panel header="表格样式" key="table">
                  <Row gutter={8}>
                    <Col span={8}>
                      <Typography.Text type="secondary">边框样式</Typography.Text>
                      <Select value={String(ts.border_style || 'single')} style={{ width: '100%' }} size="small" onChange={v => updateField('table_style', 'border_style', v)} options={[{ value: 'single', label: '单线' }, { value: 'double', label: '双线' }, { value: 'three-line', label: '三线表' }, { value: 'none', label: '无边框' }]} />
                    </Col>
                    <Col span={4}>
                      <Typography.Text type="secondary">线宽(pt)</Typography.Text>
                      <InputNumber value={ts.border_width_pt as number} style={{ width: '100%' }} size="small" step={0.1} onChange={v => updateField('table_style', 'border_width_pt', v)} />
                    </Col>
                    <Col span={4}>
                      <Typography.Text type="secondary">表头加粗</Typography.Text>
                      <Select value={ts.header_bold ? 'yes' : 'no'} style={{ width: '100%' }} size="small" onChange={v => updateField('table_style', 'header_bold', v === 'yes')} options={[{ value: 'no', label: '否' }, { value: 'yes', label: '是' }]} />
                    </Col>
                    <Col span={8}>
                      <Typography.Text type="secondary">表格对齐</Typography.Text>
                      <Select value={String(ts.table_alignment || 'left')} style={{ width: '100%' }} size="small" onChange={v => updateField('table_style', 'table_alignment', v)} options={[{ value: 'left', label: '左' }, { value: 'center', label: '居中' }, { value: 'right', label: '右' }]} />
                    </Col>
                  </Row>
                </Collapse.Panel>
              )}

              <Collapse.Panel header="原始 JSON 编辑" key="json">
                {editJsonError && <Typography.Text type="danger" style={{ display: 'block', marginBottom: 4 }}>{editJsonError}</Typography.Text>}
                <Input.TextArea
                  value={editJsonText}
                  rows={16}
                  onChange={e => {
                    setEditJsonText(e.target.value)
                    try {
                      const parsed = JSON.parse(e.target.value)
                      setEditStyleConfig(parsed)
                      setEditJsonError('')
                    } catch {
                      setEditJsonError('JSON 格式错误，修改后无法同步表单')
                    }
                  }}
                  style={{ fontFamily: 'monospace', fontSize: 12 }}
                />
              </Collapse.Panel>
            </Collapse>
          )
        })()}
      </Modal>
    </div>
  )
}

export default TaskDetailPage
