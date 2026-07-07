import React, { useState, useEffect, useCallback, useRef, Suspense, lazy } from 'react'
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
  Upload,
  List,
  Alert,
  Switch,
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
  SaveOutlined,
  HistoryOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { getTask, previewTask, getDownloadUrl, getDocxPreviewUrl, retryTask, getMineruDocxDownloadUrl, getMineruDocxPreviewUrl, getOriginalPdfPages, listTemplates, applyTemplateToTask, uploadCorrectedDocx, saveStyleToTemplate, getStyleHistory, getTaskContent, getTaskContentHtml, updateTaskContent } from '../services/api'
// 懒加载 DocEditor，避免 TinyMCE 影响首屏渲染
const DocEditor = lazy(() => import('../components/DocEditor'))

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
  auto_matched_template?: { id: string; name: string; description?: string | null } | null
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

  // 功能1：上传修正后 DOCX
  const [uploadingCorrected, setUploadingCorrected] = useState(false)

  // 功能3：保存到模板
  const [saveTemplateModalVisible, setSaveTemplateModalVisible] = useState(false)
  const [saveTemplateName, setSaveTemplateName] = useState('')
  const [saveTemplateDesc, setSaveTemplateDesc] = useState('')
  const [saveTemplateId, setSaveTemplateId] = useState<string>('')
  const [savingTemplate, setSavingTemplate] = useState(false)

  // 功能4：样式调整历史
  const [styleHistory, setStyleHistory] = useState<Array<{
    id: string
    source: string
    diff_summary: string | null
    created_at: string
  }>>([])
  const [styleHistoryVisible, setStyleHistoryVisible] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(false)

  // 内容编辑
  const [contentEditMode, setContentEditMode] = useState<'markdown' | 'richtext'>('markdown')
  const [editorHtml, setEditorHtml] = useState('')
  const [editorMarkdown, setEditorMarkdown] = useState('')
  const [contentLoading, setContentLoading] = useState(false)
  const [contentSaving, setContentSaving] = useState(false)
  const [contentLoaded, setContentLoaded] = useState(false)

  // PDF 对比预览（分页加载）
  const [pdfPages, setPdfPages] = useState<Array<{ page: number; image: string; width: number; height: number }>>([])
  const [pdfLoading, setPdfLoading] = useState(false)
  const [pdfLoaded, setPdfLoaded] = useState(false)
  const [syncScroll, setSyncScroll] = useState(true)
  const [pdfTotalPages, setPdfTotalPages] = useState(0)
  const [pdfCurrentPage, setPdfCurrentPage] = useState(1)
  const pdfPageSize = 5

  // 同步滚动 refs
  const pdfScrollRef = useRef<HTMLDivElement>(null)
  const markdownScrollRef = useRef<any>(null)
  const tinyMceEditorRef = useRef<any>(null)
  const isSyncingRef = useRef(false)

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
    setSaveTemplateId('')
    setSaveTemplateName('')
    setSaveTemplateDesc('')
    setEditStyleModalVisible(true)
  }

  // 功能1：上传修正后 DOCX
  const handleUploadCorrected = async (file: File) => {
    if (!taskId) return
    const ext = file.name.split('.').pop()?.toLowerCase()
    if (ext !== 'docx') {
      message.error('请上传 .docx 格式文件')
      return false
    }
    setUploadingCorrected(true)
    try {
      await uploadCorrectedDocx(taskId, file)
      message.success('修正后 DOCX 已上传，样式已提取并重新渲染')
      fetchTask()
      return false // 阻止 antd Upload 的自动上传
    } catch (err) {
      message.error(err instanceof Error ? err.message : '上传失败')
      return false
    } finally {
      setUploadingCorrected(false)
    }
  }

  // 功能3：保存样式到模板
  const handleSaveStyleToTemplate = async () => {
    if (!taskId || !editStyleConfig) return
    if (!saveTemplateName.trim()) {
      message.warning('请输入模板名称')
      return
    }

    // 验证 JSON
    let configToSave = editStyleConfig
    if (editJsonText.trim()) {
      try {
        configToSave = JSON.parse(editJsonText)
      } catch {
        message.error('JSON 格式错误，请修正后再保存')
        return
      }
    }

    setSavingTemplate(true)
    try {
      const res = await saveStyleToTemplate(taskId, {
        template_id: saveTemplateId || undefined,
        template_name: saveTemplateName,
        style_config: configToSave,
        description: saveTemplateDesc || undefined,
      })
      message.success(saveTemplateId ? '模板已更新' : `新模板已创建: ${res.data.data.template_name}`)
      setSaveTemplateModalVisible(false)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSavingTemplate(false)
    }
  }

  // 功能4：加载样式调整历史
  const handleLoadStyleHistory = async () => {
    if (!taskId) return
    setLoadingHistory(true)
    setStyleHistoryVisible(true)
    try {
      const res = await getStyleHistory(taskId)
      setStyleHistory(res.data.data?.items || [])
    } catch {
      // 静默
    } finally {
      setLoadingHistory(false)
    }
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
      await applyTemplateToTask(taskId, { style_config: configToApply, source: 'edit_style' })
      message.success('样式修正已应用，DOCX 已重新渲染')
      setEditStyleModalVisible(false)
      fetchTask()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '应用失败')
    } finally {
      setApplyingStyle(false)
    }
  }

  // 加载原始 PDF 页面图片（分页加载，首次加载前 5 页）
  const handleLoadPdfPages = async () => {
    if (!taskId) return
    setPdfLoading(true)
    try {
      const res = await getOriginalPdfPages(taskId, 1, pdfPageSize)
      const pages = res.data.data?.pages || []
      const totalPages = res.data.data?.total_pages || 0
      if (pages.length === 0) {
        message.warning('该任务无原始 PDF 文件（可能上传的是 Markdown/TXT）')
        return
      }
      setPdfPages(pages)
      setPdfTotalPages(totalPages)
      setPdfCurrentPage(1)
      setPdfLoaded(true)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载 PDF 预览失败')
    } finally {
      setPdfLoading(false)
    }
  }

  // 加载更多 PDF 页面
  const handleLoadMorePdfPages = async () => {
    if (!taskId) return
    const nextPage = pdfCurrentPage + 1
    setPdfLoading(true)
    try {
      const res = await getOriginalPdfPages(taskId, nextPage, pdfPageSize)
      const newPages = res.data.data?.pages || []
      if (newPages.length > 0) {
        setPdfPages(prev => [...prev, ...newPages])
        setPdfCurrentPage(nextPage)
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载更多 PDF 页面失败')
    } finally {
      setPdfLoading(false)
    }
  }

  // 同步滚动：左侧 PDF 滚动 → 同步右侧编辑区
  const handlePdfScroll = useCallback(() => {
    if (!syncScroll || isSyncingRef.current) return
    const pdfEl = pdfScrollRef.current
    if (!pdfEl) return
    const maxScroll = pdfEl.scrollHeight - pdfEl.clientHeight
    if (maxScroll <= 0) return
    const ratio = pdfEl.scrollTop / maxScroll

    isSyncingRef.current = true

    // 同步到 Markdown TextArea
    if (contentEditMode === 'markdown' && markdownScrollRef.current) {
      const mdEl = markdownScrollRef.current?.resizableTextArea?.textArea || markdownScrollRef.current
      const mdMax = mdEl.scrollHeight - mdEl.clientHeight
      if (mdMax > 0) mdEl.scrollTop = ratio * mdMax
    }

    // 同步到 TinyMCE iframe
    if (contentEditMode === 'richtext' && tinyMceEditorRef.current) {
      const editor = tinyMceEditorRef.current
      const iframe = editor.iframeElement
      if (iframe && iframe.contentWindow) {
        const win = iframe.contentWindow
        const doc = win.document?.documentElement
        if (doc) {
          const max = doc.scrollHeight - win.innerHeight
          if (max > 0) win.scrollTo(0, ratio * max)
        }
      }
    }

    requestAnimationFrame(() => { isSyncingRef.current = false })
  }, [syncScroll, contentEditMode])

  // 同步滚动：右侧编辑区滚动 → 同步左侧 PDF
  const handleEditorScroll = useCallback(() => {
    if (!syncScroll || isSyncingRef.current) return
    const pdfEl = pdfScrollRef.current
    if (!pdfEl) return

    let ratio = 0
    if (contentEditMode === 'markdown' && markdownScrollRef.current) {
      const mdEl = markdownScrollRef.current?.resizableTextArea?.textArea || markdownScrollRef.current
      const mdMax = mdEl.scrollHeight - mdEl.clientHeight
      if (mdMax <= 0) return
      ratio = mdEl.scrollTop / mdMax
    } else if (contentEditMode === 'richtext' && tinyMceEditorRef.current) {
      const editor = tinyMceEditorRef.current
      const iframe = editor.iframeElement
      if (iframe && iframe.contentWindow) {
        const win = iframe.contentWindow
        const doc = win.document?.documentElement
        if (!doc) return
        const max = doc.scrollHeight - win.innerHeight
        if (max <= 0) return
        ratio = win.scrollY / max
      }
    } else {
      return
    }

    isSyncingRef.current = true
    const maxScroll = pdfEl.scrollHeight - pdfEl.clientHeight
    if (maxScroll > 0) pdfEl.scrollTop = ratio * maxScroll
    requestAnimationFrame(() => { isSyncingRef.current = false })
  }, [syncScroll, contentEditMode])

  // 自动加载：切换 tab 时自动加载对应内容
  useEffect(() => {
    if (!taskId || task?.status !== 'completed') return
    if (activeTab === 'content_editor' && !contentLoaded) {
      setContentLoading(true)
      getTaskContent(taskId).then(res => {
        setEditorMarkdown(res.data.data?.content || '')
        setContentLoaded(true)
      }).catch(() => {}).finally(() => setContentLoading(false))
      if (!pdfLoaded) handleLoadPdfPages()
    }
    if (activeTab === 'mineru_docx' && !mineruDocxPreviewLoaded) {
      setMineruDocxPreviewLoaded(true)
    }
    if (activeTab === 'markdown' && !preview) {
      fetchPreview()
    }
  }, [activeTab, taskId, task?.status])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
        <div style={{ marginTop: 8, color: '#999' }}>加载中...</div>
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
              <>
                {preview.markdown_preview.length > 50000 && (
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 12 }}
                    message={`文档较大（${(preview.markdown_preview.length / 1024).toFixed(1)} KB），仅显示前 50,000 字符。完整内容请通过「下载 Word」获取。`}
                  />
                )}
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                  {preview.markdown_preview.slice(0, 50000)}
                </ReactMarkdown>
              </>
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

    // 内容编辑 Tab（左右分栏：左侧 PDF 对比预览 + 右侧编辑区）
    tabItems.push({
      key: 'content_editor',
      label: <span><EditOutlined /> 内容编辑</span>,
      children: (
        <Card>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="内容编辑 + PDF 对比预览"
            description="左侧显示原始 PDF 页面，右侧为 MinerU 原始 DOCX 编辑区。对照 PDF 内容检查解析结果是否有误，直接在右侧编辑修正。支持左右同步滚动。"
          />
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
            {/* 左侧：PDF 预览 */}
            <div style={{ width: '40%', minWidth: 300, flexShrink: 0 }}>
              <div style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography.Text strong>原始 PDF 预览</Typography.Text>
                <Space size={8}>
                  <Switch
                    checked={syncScroll}
                    onChange={setSyncScroll}
                    checkedChildren="同步滚动"
                    unCheckedChildren="独立滚动"
                    size="small"
                  />
                  <Button
                    size="small"
                    icon={<EyeOutlined />}
                    onClick={handleLoadPdfPages}
                    loading={pdfLoading}
                    type="primary"
                  >
                    {pdfLoaded ? '刷新' : '加载 PDF'}
                  </Button>
                </Space>
              </div>
              {pdfLoaded && pdfPages.length > 0 ? (
                <div
                  ref={pdfScrollRef}
                  onScroll={handlePdfScroll}
                  style={{
                    height: 'calc(100vh - 220px)',
                    minHeight: 500,
                    overflowY: 'auto',
                    border: '1px solid #d9d9d9',
                    borderRadius: 8,
                    padding: 8,
                    background: '#f5f5f5',
                  }}
                >
                  {pdfPages.map((p) => (
                    <div key={p.page} style={{ marginBottom: 8, textAlign: 'center' }}>
                      <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>第 {p.page} 页</div>
                      <img
                        src={p.image}
                        alt={`PDF 第 ${p.page} 页`}
                        style={{ width: '100%', boxShadow: '0 2px 8px rgba(0,0,0,0.15)' }}
                      />
                    </div>
                  ))}
                  {pdfPages.length < pdfTotalPages && (
                    <div style={{ textAlign: 'center', padding: '12px 0' }}>
                      <Button
                        size="small"
                        onClick={handleLoadMorePdfPages}
                        loading={pdfLoading}
                      >
                        加载更多（{pdfPages.length}/{pdfTotalPages} 页）
                      </Button>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{
                  height: 'calc(100vh - 220px)',
                  minHeight: 500,
                  border: '1px dashed #d9d9d9',
                  borderRadius: 8,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#999',
                }}>
                  {pdfLoading ? <Spin /> : '点击「加载 PDF」按钮预览原始文件'}
                </div>
              )}
            </div>

            {/* 右侧：编辑区 */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ marginBottom: 8 }}>
                <Space wrap>
                  <Button
                    size="small"
                    type={contentEditMode === 'markdown' ? 'primary' : 'default'}
                    onClick={() => setContentEditMode('markdown')}
                  >
                    Markdown 编辑
                  </Button>
                  <Button
                    size="small"
                    type={contentEditMode === 'richtext' ? 'primary' : 'default'}
                    onClick={async () => {
                      setContentEditMode('richtext')
                      if (!contentLoaded) {
                        setContentLoading(true)
                        try {
                          const res = await getTaskContentHtml(taskId!)
                          setEditorHtml(res.data.data?.html || '')
                          setContentLoaded(true)
                        } catch (err) {
                          message.error('加载内容失败')
                        } finally {
                          setContentLoading(false)
                        }
                      }
                    }}
                  >
                    DOC 富文本编辑（MinerU原始）
                  </Button>
                  <Button
                    size="small"
                    type="primary"
                    icon={<SaveOutlined />}
                    loading={contentSaving}
                    onClick={async () => {
                      setContentSaving(true)
                      try {
                        const contentType = contentEditMode === 'richtext' ? 'html' : 'markdown'
                        const content = contentEditMode === 'richtext' ? editorHtml : editorMarkdown
                        await updateTaskContent(taskId!, { content, content_type: contentType, regenerate_docx: true })
                        message.success(contentEditMode === 'richtext'
                          ? 'DOC 已保存，样式已重新应用'
                          : 'Markdown 已保存，样式已重新应用'
                        )
                        fetchTask()
                        setContentLoaded(false)
                      } catch (err) {
                        message.error(err instanceof Error ? err.message : '保存失败')
                      } finally {
                        setContentSaving(false)
                      }
                    }}
                  >
                    {contentEditMode === 'richtext' ? '保存 DOC 并重新渲染' : '保存 Markdown 并重新渲染'}
                  </Button>
                </Space>
              </div>
              {contentLoading ? (
                <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
              ) : contentEditMode === 'richtext' ? (
                <div
                  onScroll={handleEditorScroll}
                  style={{ height: 'calc(100vh - 220px)', minHeight: 500, overflow: 'hidden' }}
                >
                  <Suspense fallback={<div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>}>
                    <DocEditor
                      initialHtml={editorHtml}
                      onChange={setEditorHtml}
                      onEditorInit={(editor) => {
                        tinyMceEditorRef.current = editor
                        // 监听 TinyMCE iframe 内部滚动
                        const iframe = editor.iframeElement
                        if (iframe && iframe.contentWindow) {
                          iframe.contentWindow.addEventListener('scroll', handleEditorScroll)
                        }
                      }}
                    />
                  </Suspense>
                </div>
              ) : (
                <div style={{ height: 'calc(100vh - 220px)', minHeight: 500 }}>
                  <Button
                    style={{ marginBottom: 8 }}
                    size="small"
                    onClick={async () => {
                      setContentLoading(true)
                      try {
                        const res = await getTaskContent(taskId!)
                        setEditorMarkdown(res.data.data?.content || '')
                        setContentLoaded(true)
                      } catch (err) {
                        message.error('加载内容失败')
                      } finally {
                        setContentLoading(false)
                      }
                    }}
                    loading={contentLoading && !contentLoaded}
                  >
                    加载 Markdown 内容
                  </Button>
                  <Input.TextArea
                    ref={markdownScrollRef as any}
                    value={editorMarkdown}
                    onChange={(e) => setEditorMarkdown(e.target.value)}
                    onScroll={handleEditorScroll}
                    rows={25}
                    style={{ fontFamily: 'monospace', fontSize: 14, height: 'calc(100vh - 280px)' }}
                    placeholder="点击「加载 Markdown 内容」按钮加载当前文档内容"
                  />
                </div>
              )}
            </div>
          </div>
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
              {/* 功能1：上传修正后 DOCX */}
              <Upload
                accept=".docx"
                showUploadList={false}
                beforeUpload={(file) => {
                  handleUploadCorrected(file as File)
                  return false
                }}
              >
                <Button
                  icon={<UploadOutlined />}
                  loading={uploadingCorrected}
                >
                  上传修正后 DOCX
                </Button>
              </Upload>
              {/* 功能3：保存到模板（在修正样式 Modal 内） */}
              <Button
                icon={<ThunderboltOutlined />}
                onClick={() => {
                  setTemplateModalVisible(true)
                  loadTemplates()
                }}
              >
                应用模板
              </Button>
              {/* 功能4：样式调整历史 */}
              <Button
                icon={<HistoryOutlined />}
                onClick={handleLoadStyleHistory}
              >
                调整历史
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
          {/* 功能2：自动匹配模板信息 */}
          {task.auto_matched_template && (
            <Descriptions.Item label="自动匹配模板" span={3}>
              <Tag color="blue">{task.auto_matched_template.name}</Tag>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                ID: {task.auto_matched_template.id}
              </Typography.Text>
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
        footer={[
          <Button key="cancel" onClick={() => setEditStyleModalVisible(false)}>取消</Button>,
          <Button
            key="saveTemplate"
            icon={<SaveOutlined />}
            onClick={() => {
              setSaveTemplateModalVisible(true)
              setSaveTemplateName('')
              setSaveTemplateId('')
              setSaveTemplateDesc('')
              // 加载模板列表供选择更新
              loadTemplates()
            }}
          >
            保存到模板
          </Button>,
          <Button
            key="apply"
            type="primary"
            loading={applyingStyle}
            onClick={handleApplyEditStyle}
          >
            应用并重新渲染
          </Button>,
        ]}
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

      {/* 功能3：保存到模板 Modal */}
      <Modal
        title="保存样式到模板"
        open={saveTemplateModalVisible}
        onOk={handleSaveStyleToTemplate}
        onCancel={() => setSaveTemplateModalVisible(false)}
        okText={saveTemplateId ? '更新模板' : '创建新模板'}
        cancelText="取消"
        confirmLoading={savingTemplate}
      >
        <p style={{ marginBottom: 12, color: '#999' }}>
          将当前修正后的样式配置保存为模板，后续可在创建任务时直接使用。
        </p>
        <div style={{ marginBottom: 12 }}>
          <Typography.Text type="secondary">选择已有模板更新（可选）</Typography.Text>
          <Select
            style={{ width: '100%' }}
            placeholder="不选则创建新模板"
            value={saveTemplateId || undefined}
            onChange={(v) => {
              setSaveTemplateId(v || '')
              // 选中模板时自动填充名称
              const selected = templates.find(t => t.value === v)
              if (selected && !saveTemplateName) {
                setSaveTemplateName(selected.label)
              }
            }}
            options={templates}
            showSearch
            optionFilterProp="label"
            allowClear
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <Typography.Text type="secondary">模板名称</Typography.Text>
          <Input
            value={saveTemplateName}
            placeholder="如: GB/T 14454.13 样式模板"
            onChange={e => setSaveTemplateName(e.target.value)}
          />
        </div>
        <div>
          <Typography.Text type="secondary">模板描述（可选）</Typography.Text>
          <Input.TextArea
            value={saveTemplateDesc}
            placeholder="描述模板适用场景"
            rows={2}
            onChange={e => setSaveTemplateDesc(e.target.value)}
          />
        </div>
      </Modal>

      {/* 功能4：样式调整历史 Modal */}
      <Modal
        title="样式调整历史"
        open={styleHistoryVisible}
        onCancel={() => setStyleHistoryVisible(false)}
        footer={null}
        width={700}
      >
        <Spin spinning={loadingHistory}>
          {styleHistory.length > 0 ? (
            <List
              dataSource={styleHistory}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space>
                        <Tag color={
                          item.source === 'upload_corrected' ? 'blue' :
                          item.source === 'edit_style' ? 'green' :
                          item.source === 'apply_template' ? 'orange' : 'default'
                        }>
                          {item.source === 'upload_corrected' ? '上传修正DOCX' :
                           item.source === 'edit_style' ? '修正样式' :
                           item.source === 'apply_template' ? '应用模板' : item.source}
                        </Tag>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {dayjs(item.created_at).format('YYYY-MM-DD HH:mm:ss')}
                        </Typography.Text>
                      </Space>
                    }
                    description={item.diff_summary || '无差异摘要'}
                  />
                </List.Item>
              )}
            />
          ) : (
            <Empty description="暂无调整历史" />
          )}
        </Spin>
      </Modal>
    </div>
  )
}

export default TaskDetailPage
