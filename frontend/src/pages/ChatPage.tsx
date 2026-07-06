import React, { useState, useRef, useEffect } from 'react'
import {
  Row,
  Col,
  Card,
  Button,
  Input,
  Upload,
  Space,
  Typography,
  message,
  Modal,
  Form,
  Select,
  Spin,
  Tag,
  InputNumber,
  Collapse,
  List,
  Popconfirm,
  Tooltip,
} from 'antd'
import {
  UploadOutlined,
  SaveOutlined,
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  EyeOutlined,
  ThunderboltOutlined,
  PlusOutlined,
  DeleteOutlined,
  MessageOutlined,
} from '@ant-design/icons'
import {
  uploadTemplate,
  saveTemplate,
  chatStyle,
  chatEditContent,
  applyTemplateToTask,
  listTasks,
  listChatSessions,
  createChatSession,
  getChatSession,
  deleteChatSession,
} from '../services/api'

const { Text } = Typography
const { TextArea } = Input
const { Panel } = Collapse

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

interface StyleConfig {
  page_layout?: Record<string, unknown>
  cover_style?: Record<string, unknown> | null
  preface_style?: Record<string, unknown> | null
  heading_styles?: Array<Record<string, unknown>>
  body_style?: Record<string, unknown>
  table_style?: Record<string, unknown> | null
  rag_sources?: string[]
  [key: string]: unknown
}

interface ChatSession {
  id: string
  title: string
  style_config: Record<string, unknown>
  message_count: number
  created_at: string
  updated_at: string
}

const DEFAULT_STYLE_CONFIG: StyleConfig = {
  page_layout: {
    paper_size: 'A4',
    margin_top_cm: 3.7,
    margin_bottom_cm: 3.5,
    margin_left_cm: 2.8,
    margin_right_cm: 2.6,
    header_distance_cm: 1.5,
    footer_distance_cm: 1.75,
    orientation: 'portrait',
  },
  body_style: {
    font: { family: '仿宋_GB2312', size_pt: 16, bold: false, italic: false, color_hex: '#000000' },
    line_spacing: 1.5,
    space_before_pt: 0,
    space_after_pt: 0,
    alignment: 'justify',
    first_line_indent_chars: 2,
  },
  heading_styles: [],
  table_style: null,
  rag_sources: [],
}

const ChatPage: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content: '你好！我是排版格式专家。你可以上传 Word 模板自动提取格式，也可以用自然语言告诉我你想要的修改，比如"正文改为仿宋16pt"、"标题居中加粗"。',
    },
  ])
  const [inputValue, setInputValue] = useState('')
  const [styleConfig, setStyleConfig] = useState<StyleConfig>(DEFAULT_STYLE_CONFIG)
  const [sourceDocxPath, setSourceDocxPath] = useState<string>('')
  const [chatLoading, setChatLoading] = useState(false)
  const [uploadLoading, setUploadLoading] = useState(false)
  const [saveModalVisible, setSaveModalVisible] = useState(false)
  const [previewModalVisible, setPreviewModalVisible] = useState(false)
  const [tasks, setTasks] = useState<Array<{ id: string; filename: string }>>([])
  const [selectedTaskId, setSelectedTaskId] = useState<string>('')
  const [applying, setApplying] = useState(false)
  const [saveForm] = Form.useForm()
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 对话模式：样式编辑 / 内容编辑
  const [chatMode, setChatMode] = useState<'style' | 'content'>('style')
  const [contentEditTaskId, setContentEditTaskId] = useState<string>('')

  // 会话管理状态
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string>('')
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [messagesLoading, setMessagesLoading] = useState(false)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    loadCompletedTasks()
    loadSessions()
  }, [])

  const loadSessions = async () => {
    setSessionsLoading(true)
    try {
      const res = await listChatSessions({ page: 1, page_size: 50 })
      setSessions(res.data.data.items)
    } catch {
      // 静默
    } finally {
      setSessionsLoading(false)
    }
  }

  const loadCompletedTasks = async () => {
    try {
      const res = await listTasks({ page: 1, page_size: 50, status: 'completed' })
      setTasks(res.data.data.items.map((t: { id: string; filename: string }) => ({ id: t.id, filename: t.filename })))
    } catch {
      // 静默
    }
  }

  const handleNewSession = async () => {
    try {
      const res = await createChatSession({ title: '新对话', style_config: styleConfig })
      const newSession = res.data.data
      setSessions(prev => [newSession, ...prev])
      setCurrentSessionId(newSession.id)
      setMessages([{
        role: 'assistant',
        content: '你好！我是排版格式专家。你可以上传 Word 模板自动提取格式，也可以用自然语言告诉我你想要的修改，比如"正文改为仿宋16pt"、"标题居中加粗"。',
      }])
      setStyleConfig(DEFAULT_STYLE_CONFIG)
      message.success('已创建新对话')
    } catch (err) {
      message.error(err instanceof Error ? err.message : '创建对话失败')
    }
  }

  const handleSwitchSession = async (sessionId: string) => {
    if (sessionId === currentSessionId) return
    setMessagesLoading(true)
    try {
      const res = await getChatSession(sessionId)
      const { session: sessionData, messages: historyMessages } = res.data.data

      setCurrentSessionId(sessionId)
      setStyleConfig(sessionData.style_config || DEFAULT_STYLE_CONFIG)

      // 恢复历史消息
      const restored: ChatMessage[] = historyMessages.map((m: { role: string; content: string }) => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
      }))
      setMessages(restored)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '加载对话失败')
    } finally {
      setMessagesLoading(false)
    }
  }

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await deleteChatSession(sessionId)
      setSessions(prev => prev.filter(s => s.id !== sessionId))
      if (currentSessionId === sessionId) {
        setCurrentSessionId('')
        setMessages([{
          role: 'assistant',
          content: '你好！我是排版格式专家。你可以上传 Word 模板自动提取格式，也可以用自然语言告诉我你想要的修改，比如"正文改为仿宋16pt"、"标题居中加粗"。',
        }])
        setStyleConfig(DEFAULT_STYLE_CONFIG)
      }
      message.success('对话已删除')
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  const handleUploadTemplate = async (file: File) => {
    setUploadLoading(true)
    try {
      const res = await uploadTemplate(file)
      const data = res.data.data
      setStyleConfig(data.style_config)
      setSourceDocxPath(data.source_docx_path || '')
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `已从模板 "${data.filename}" 中提取排版格式。你可以在右侧查看和编辑配置，或继续用对话微调。`,
      }])
      message.success('模板格式提取成功')
    } catch (err) {
      message.error(err instanceof Error ? err.message : '模板上传失败')
    } finally {
      setUploadLoading(false)
    }
    return false // 阻止 antd 自动上传
  }

  const handleSendMessage = async () => {
    if (!inputValue.trim() || chatLoading) return

    const userMessage = inputValue.trim()
    setMessages(prev => [...prev, { role: 'user', content: userMessage }])
    setInputValue('')
    setChatLoading(true)

    try {
      if (chatMode === 'content') {
        // 内容编辑模式
        if (!contentEditTaskId) {
          setMessages(prev => [...prev, { role: 'assistant', content: '请先选择要编辑的任务' }])
          setChatLoading(false)
          return
        }
        const res = await chatEditContent({
          message: userMessage,
          task_id: contentEditTaskId,
          session_id: currentSessionId || undefined,
        })
        const data = res.data.data
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `✅ ${data.reply || '内容已修改'}\n\n文档内容已更新并重新生成 DOCX。`,
        }])
      } else {
        // 样式编辑模式（原有逻辑）
        const res = await chatStyle({
          message: userMessage,
          current_style_config: styleConfig,
          session_id: currentSessionId || undefined,
        })
        const data = res.data.data
        setMessages(prev => [...prev, { role: 'assistant', content: data.reply }])
        if (data.updated_style_config) {
          setStyleConfig(data.updated_style_config)
        }
        // 更新或设置会话 ID
        if (data.session_id && !currentSessionId) {
          setCurrentSessionId(data.session_id)
          loadSessions()
        }
      }
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `处理失败: ${err instanceof Error ? err.message : '未知错误'}`,
      }])
    } finally {
      setChatLoading(false)
    }
  }

  const handleSaveTemplate = async () => {
    try {
      const values = await saveForm.validateFields()
      await saveTemplate({
        name: values.name,
        style_config: styleConfig,
        description: values.description,
        source_docx_path: sourceDocxPath || undefined,
      })
      message.success('模板保存成功')
      setSaveModalVisible(false)
      saveForm.resetFields()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    }
  }

  const handleApplyToTask = async () => {
    if (!selectedTaskId) {
      message.warning('请选择一个任务')
      return
    }
    setApplying(true)
    try {
      await applyTemplateToTask(selectedTaskId, { style_config: styleConfig })
      message.success('模板已应用到任务')
      setPreviewModalVisible(false)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '应用失败')
    } finally {
      setApplying(false)
    }
  }

  // 样式配置编辑器
  const renderStyleEditor = () => {
    const pl = styleConfig.page_layout as Record<string, unknown> | undefined
    const bs = styleConfig.body_style as Record<string, unknown> | undefined
    const bodyFont = bs?.font as Record<string, unknown> | undefined
    const hs = styleConfig.heading_styles as Array<Record<string, unknown>> | undefined
    const cs = styleConfig.cover_style as Record<string, unknown> | undefined | null
    const ps = styleConfig.preface_style as Record<string, unknown> | undefined | null
    const coverFont = cs?.font as Record<string, unknown> | undefined
    const prefaceFont = ps?.font as Record<string, unknown> | undefined

    return (
      <Collapse defaultActiveKey={['page', 'body']} size="small">
        <Panel header="页面布局" key="page">
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <Row gutter={8}>
              <Col span={12}>
                <Text type="secondary">纸张大小</Text>
                <Select
                  value={(pl?.paper_size as string) || 'A4'}
                  style={{ width: '100%' }}
                  size="small"
                  onChange={v => setStyleConfig({
                    ...styleConfig,
                    page_layout: { ...pl, paper_size: v },
                  })}
                  options={[
                    { value: 'A4', label: 'A4' },
                    { value: 'A3', label: 'A3' },
                    { value: 'B5', label: 'B5' },
                    { value: 'Letter', label: 'Letter' },
                  ]}
                />
              </Col>
              <Col span={12}>
                <Text type="secondary">方向</Text>
                <Select
                  value={(pl?.orientation as string) || 'portrait'}
                  style={{ width: '100%' }}
                  size="small"
                  onChange={v => setStyleConfig({
                    ...styleConfig,
                    page_layout: { ...pl, orientation: v },
                  })}
                  options={[
                    { value: 'portrait', label: '纵向' },
                    { value: 'landscape', label: '横向' },
                  ]}
                />
              </Col>
            </Row>
            <Row gutter={8}>
              <Col span={6}>
                <Text type="secondary">上边距(cm)</Text>
                <InputNumber
                  value={pl?.margin_top_cm as number}
                  style={{ width: '100%' }}
                  size="small"
                  step={0.1}
                  onChange={v => setStyleConfig({
                    ...styleConfig,
                    page_layout: { ...pl, margin_top_cm: v },
                  })}
                />
              </Col>
              <Col span={6}>
                <Text type="secondary">下边距(cm)</Text>
                <InputNumber
                  value={pl?.margin_bottom_cm as number}
                  style={{ width: '100%' }}
                  size="small"
                  step={0.1}
                  onChange={v => setStyleConfig({
                    ...styleConfig,
                    page_layout: { ...pl, margin_bottom_cm: v },
                  })}
                />
              </Col>
              <Col span={6}>
                <Text type="secondary">左边距(cm)</Text>
                <InputNumber
                  value={pl?.margin_left_cm as number}
                  style={{ width: '100%' }}
                  size="small"
                  step={0.1}
                  onChange={v => setStyleConfig({
                    ...styleConfig,
                    page_layout: { ...pl, margin_left_cm: v },
                  })}
                />
              </Col>
              <Col span={6}>
                <Text type="secondary">右边距(cm)</Text>
                <InputNumber
                  value={pl?.margin_right_cm as number}
                  style={{ width: '100%' }}
                  size="small"
                  step={0.1}
                  onChange={v => setStyleConfig({
                    ...styleConfig,
                    page_layout: { ...pl, margin_right_cm: v },
                  })}
                />
              </Col>
            </Row>
          </Space>
        </Panel>

        {cs && (
          <Panel header="封面样式" key="cover">
            <Space direction="vertical" style={{ width: '100%' }} size="small">
              <Row gutter={8}>
                <Col span={12}>
                  <Text type="secondary">中文字体</Text>
                  <Input
                    value={String(coverFont?.east_asia_family || coverFont?.family || '')}
                    size="small"
                    onChange={e => setStyleConfig({
                      ...styleConfig,
                      cover_style: { ...cs, font: { ...coverFont, east_asia_family: e.target.value } },
                    })}
                  />
                </Col>
                <Col span={6}>
                  <Text type="secondary">字号(pt)</Text>
                  <InputNumber
                    value={coverFont?.size_pt as number}
                    style={{ width: '100%' }}
                    size="small"
                    step={0.5}
                    onChange={v => setStyleConfig({
                      ...styleConfig,
                      cover_style: { ...cs, font: { ...coverFont, size_pt: v } },
                    })}
                  />
                </Col>
                <Col span={6}>
                  <Text type="secondary">加粗</Text>
                  <Select
                    value={coverFont?.bold ? 'yes' : 'no'}
                    style={{ width: '100%' }}
                    size="small"
                    onChange={v => setStyleConfig({
                      ...styleConfig,
                      cover_style: { ...cs, font: { ...coverFont, bold: v === 'yes' } },
                    })}
                    options={[{ value: 'no', label: '否' }, { value: 'yes', label: '是' }]}
                  />
                </Col>
              </Row>
              <Row gutter={8}>
                <Col span={12}>
                  <Text type="secondary">对齐</Text>
                  <Select
                    value={String(cs.alignment || 'center')}
                    style={{ width: '100%' }}
                    size="small"
                    onChange={v => setStyleConfig({ ...styleConfig, cover_style: { ...cs, alignment: v } })}
                    options={[
                      { value: 'left', label: '左对齐' },
                      { value: 'center', label: '居中' },
                      { value: 'right', label: '右对齐' },
                      { value: 'justify', label: '两端对齐' },
                    ]}
                  />
                </Col>
                <Col span={6}>
                  <Text type="secondary">行距</Text>
                  <InputNumber
                    value={cs.line_spacing as number}
                    style={{ width: '100%' }}
                    size="small"
                    step={0.1}
                    onChange={v => setStyleConfig({ ...styleConfig, cover_style: { ...cs, line_spacing: v } })}
                  />
                </Col>
              </Row>
            </Space>
          </Panel>
        )}

        {ps && (
          <Panel header="前言样式" key="preface">
            <Space direction="vertical" style={{ width: '100%' }} size="small">
              <Row gutter={8}>
                <Col span={12}>
                  <Text type="secondary">中文字体</Text>
                  <Input
                    value={String(prefaceFont?.east_asia_family || prefaceFont?.family || '')}
                    size="small"
                    onChange={e => setStyleConfig({
                      ...styleConfig,
                      preface_style: { ...ps, font: { ...prefaceFont, east_asia_family: e.target.value } },
                    })}
                  />
                </Col>
                <Col span={6}>
                  <Text type="secondary">字号(pt)</Text>
                  <InputNumber
                    value={prefaceFont?.size_pt as number}
                    style={{ width: '100%' }}
                    size="small"
                    step={0.5}
                    onChange={v => setStyleConfig({
                      ...styleConfig,
                      preface_style: { ...ps, font: { ...prefaceFont, size_pt: v } },
                    })}
                  />
                </Col>
                <Col span={6}>
                  <Text type="secondary">加粗</Text>
                  <Select
                    value={prefaceFont?.bold ? 'yes' : 'no'}
                    style={{ width: '100%' }}
                    size="small"
                    onChange={v => setStyleConfig({
                      ...styleConfig,
                      preface_style: { ...ps, font: { ...prefaceFont, bold: v === 'yes' } },
                    })}
                    options={[{ value: 'no', label: '否' }, { value: 'yes', label: '是' }]}
                  />
                </Col>
              </Row>
              <Row gutter={8}>
                <Col span={12}>
                  <Text type="secondary">对齐</Text>
                  <Select
                    value={String(ps.alignment || 'center')}
                    style={{ width: '100%' }}
                    size="small"
                    onChange={v => setStyleConfig({ ...styleConfig, preface_style: { ...ps, alignment: v } })}
                    options={[
                      { value: 'left', label: '左对齐' },
                      { value: 'center', label: '居中' },
                      { value: 'right', label: '右对齐' },
                      { value: 'justify', label: '两端对齐' },
                    ]}
                  />
                </Col>
                <Col span={6}>
                  <Text type="secondary">行距</Text>
                  <InputNumber
                    value={ps.line_spacing as number}
                    style={{ width: '100%' }}
                    size="small"
                    step={0.1}
                    onChange={v => setStyleConfig({ ...styleConfig, preface_style: { ...ps, line_spacing: v } })}
                  />
                </Col>
              </Row>
            </Space>
          </Panel>
        )}

        <Panel header="正文样式" key="body">
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <Row gutter={8}>
              <Col span={12}>
                <Text type="secondary">中文字体</Text>
                <Input
                  value={(bodyFont?.east_asia_family as string) || (bodyFont?.family as string) || ''}
                  size="small"
                  onChange={e => setStyleConfig({
                    ...styleConfig,
                    body_style: { ...bs, font: { ...bodyFont, east_asia_family: e.target.value } },
                  })}
                />
              </Col>
              <Col span={6}>
                <Text type="secondary">字号(pt)</Text>
                <InputNumber
                  value={bodyFont?.size_pt as number}
                  style={{ width: '100%' }}
                  size="small"
                  step={0.5}
                  onChange={v => setStyleConfig({
                    ...styleConfig,
                    body_style: { ...bs, font: { ...bodyFont, size_pt: v } },
                  })}
                />
              </Col>
              <Col span={6}>
                <Text type="secondary">对齐</Text>
                <Select
                  value={(bs?.alignment as string) || 'left'}
                  style={{ width: '100%' }}
                  size="small"
                  onChange={v => setStyleConfig({
                    ...styleConfig,
                    body_style: { ...bs, alignment: v },
                  })}
                  options={[
                    { value: 'left', label: '左对齐' },
                    { value: 'center', label: '居中' },
                    { value: 'right', label: '右对齐' },
                    { value: 'justify', label: '两端对齐' },
                  ]}
                />
              </Col>
            </Row>
            <Row gutter={8}>
              <Col span={8}>
                <Text type="secondary">行距</Text>
                <InputNumber
                  value={bs?.line_spacing as number}
                  style={{ width: '100%' }}
                  size="small"
                  step={0.1}
                  onChange={v => setStyleConfig({
                    ...styleConfig,
                    body_style: { ...bs, line_spacing: v },
                  })}
                />
              </Col>
              <Col span={8}>
                <Text type="secondary">首行缩进(字)</Text>
                <InputNumber
                  value={bs?.first_line_indent_chars as number}
                  style={{ width: '100%' }}
                  size="small"
                  step={0.5}
                  onChange={v => setStyleConfig({
                    ...styleConfig,
                    body_style: { ...bs, first_line_indent_chars: v },
                  })}
                />
              </Col>
              <Col span={8}>
                <Text type="secondary">加粗</Text>
                <br />
                <Select
                  value={bodyFont?.bold ? 'yes' : 'no'}
                  style={{ width: '100%' }}
                  size="small"
                  onChange={v => setStyleConfig({
                    ...styleConfig,
                    body_style: { ...bs, font: { ...bodyFont, bold: v === 'yes' } },
                  })}
                  options={[
                    { value: 'no', label: '否' },
                    { value: 'yes', label: '是' },
                  ]}
                />
              </Col>
            </Row>
            <Row gutter={8}>
              <Col span={8}>
                <Text type="secondary">段前(pt)</Text>
                <InputNumber
                  value={bs?.space_before_pt as number}
                  style={{ width: '100%' }}
                  size="small"
                  step={0.5}
                  onChange={v => setStyleConfig({
                    ...styleConfig,
                    body_style: { ...bs, space_before_pt: v },
                  })}
                />
              </Col>
              <Col span={8}>
                <Text type="secondary">段后(pt)</Text>
                <InputNumber
                  value={bs?.space_after_pt as number}
                  style={{ width: '100%' }}
                  size="small"
                  step={0.5}
                  onChange={v => setStyleConfig({
                    ...styleConfig,
                    body_style: { ...bs, space_after_pt: v },
                  })}
                />
              </Col>
              <Col span={8}>
                <Text type="secondary">左缩进(cm)</Text>
                <InputNumber
                  value={bs?.left_indent_cm as number}
                  style={{ width: '100%' }}
                  size="small"
                  step={0.1}
                  onChange={v => setStyleConfig({
                    ...styleConfig,
                    body_style: { ...bs, left_indent_cm: v },
                  })}
                />
              </Col>
            </Row>
          </Space>
        </Panel>

        {hs && hs.length > 0 && (
          <Panel header={`标题样式 (${hs.length})`} key="headings">
            {hs.map((h, i) => {
              const hf = h.font as Record<string, unknown> | undefined
              return (
                <div key={i} style={{ marginBottom: 8, padding: '4px 0', borderBottom: i < hs.length - 1 ? '1px solid #f0f0f0' : 'none' }}>
                  <Tag color="blue">第{String(h.level)}级</Tag>
                  <Text>{String(hf?.east_asia_family ?? hf?.family ?? '')} {String(hf?.size_pt ?? '')}pt </Text>
                  {Boolean(hf?.bold) && <Tag>加粗</Tag>}
                  <Text type="secondary">{String(h.alignment ?? '')}</Text>
                  <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                    行距: {String(h.line_spacing ?? '')} | 缩进: {String(h.first_line_indent_chars ?? '')}字
                    {h.numbering_format ? ` | 编号: ${String(h.numbering_format)}` : ''}
                  </div>
                </div>
              )
            })}
          </Panel>
        )}

        {(() => {
          const ts = styleConfig.table_style as Record<string, unknown> | undefined | null
          if (!ts) return null
          return (
            <Panel header="表格样式" key="table">
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                <Row gutter={8}>
                  <Col span={12}>
                    <Text type="secondary">边框样式</Text>
                    <Select
                      value={(ts.border_style as string) || 'single'}
                      style={{ width: '100%' }}
                      size="small"
                      onChange={v => setStyleConfig({ ...styleConfig, table_style: { ...ts, border_style: v } })}
                      options={[
                        { value: 'single', label: '单线' },
                        { value: 'double', label: '双线' },
                        { value: 'three-line', label: '三线表' },
                        { value: 'none', label: '无边框' },
                      ]}
                    />
                  </Col>
                  <Col span={6}>
                    <Text type="secondary">线宽(pt)</Text>
                    <InputNumber
                      value={ts.border_width_pt as number}
                      style={{ width: '100%' }}
                      size="small"
                      step={0.1}
                      onChange={v => setStyleConfig({ ...styleConfig, table_style: { ...ts, border_width_pt: v } })}
                    />
                  </Col>
                  <Col span={6}>
                    <Text type="secondary">对齐</Text>
                    <Select
                      value={(ts.table_alignment as string) || 'left'}
                      style={{ width: '100%' }}
                      size="small"
                      onChange={v => setStyleConfig({ ...styleConfig, table_style: { ...ts, table_alignment: v } })}
                      options={[
                        { value: 'left', label: '左' },
                        { value: 'center', label: '居中' },
                        { value: 'right', label: '右' },
                      ]}
                    />
                  </Col>
                </Row>
                <Row gutter={8}>
                  <Col span={12}>
                    <Text type="secondary">表头加粗</Text>
                    <Select
                      value={ts.header_bold ? 'yes' : 'no'}
                      style={{ width: '100%' }}
                      size="small"
                      onChange={v => setStyleConfig({ ...styleConfig, table_style: { ...ts, header_bold: v === 'yes' } })}
                      options={[{ value: 'no', label: '否' }, { value: 'yes', label: '是' }]}
                    />
                  </Col>
                  <Col span={12}>
                    <Text type="secondary">表头背景色</Text>
                    <Input
                      value={(ts.header_bg_color as string) || ''}
                      size="small"
                      placeholder="如 #D9E2F3"
                      onChange={e => setStyleConfig({ ...styleConfig, table_style: { ...ts, header_bg_color: e.target.value || null } })}
                    />
                  </Col>
                </Row>
                <Row gutter={8}>
                  <Col span={12}>
                    <Text type="secondary">表头跨页重复</Text>
                    <Select
                      value={ts.header_repeat ? 'yes' : 'no'}
                      style={{ width: '100%' }}
                      size="small"
                      onChange={v => setStyleConfig({ ...styleConfig, table_style: { ...ts, header_repeat: v === 'yes' } })}
                      options={[{ value: 'no', label: '否' }, { value: 'yes', label: '是' }]}
                    />
                  </Col>
                  <Col span={12}>
                    <Text type="secondary">垂直对齐</Text>
                    <Select
                      value={(ts.cell_vertical_alignment as string) || 'center'}
                      style={{ width: '100%' }}
                      size="small"
                      onChange={v => setStyleConfig({ ...styleConfig, table_style: { ...ts, cell_vertical_alignment: v } })}
                      options={[
                        { value: 'top', label: '顶部' },
                        { value: 'center', label: '居中' },
                        { value: 'bottom', label: '底部' },
                      ]}
                    />
                  </Col>
                </Row>
              </Space>
            </Panel>
          )
        })()}

        {(() => {
          const ls = styleConfig.list_style as Record<string, unknown> | undefined | null
          const fs = styleConfig.footnote_style as Record<string, unknown> | undefined | null
          const hfs = styleConfig.header_footer_style as Record<string, unknown> | undefined | null
          const cs = styleConfig.caption_style as Record<string, unknown> | undefined | null
          if (!ls && !fs && !hfs && !cs) return null
          return (
            <Panel header="其他样式" key="other">
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                {ls && (
                  <div>
                    <Tag color="green">列表</Tag>
                    <Text>{String((ls.font as Record<string, unknown>)?.east_asia_family ?? (ls.font as Record<string, unknown>)?.family ?? '')} {String((ls.font as Record<string, unknown>)?.size_pt ?? '')}pt</Text>
                  </div>
                )}
                {cs && (
                  <div>
                    <Tag color="orange">图表标题</Tag>
                    <Text>{String((cs.font as Record<string, unknown>)?.east_asia_family ?? (cs.font as Record<string, unknown>)?.family ?? '')} {String((cs.font as Record<string, unknown>)?.size_pt ?? '')}pt</Text>
                  </div>
                )}
                {fs && (
                  <div>
                    <Tag color="purple">脚注</Tag>
                    <Text>{String((fs.font as Record<string, unknown>)?.east_asia_family ?? (fs.font as Record<string, unknown>)?.family ?? '')} {String((fs.font as Record<string, unknown>)?.size_pt ?? '')}pt</Text>
                  </div>
                )}
                {hfs && (
                  <div>
                    <Tag color="cyan">页眉页脚</Tag>
                    <Text>{String((hfs.font as Record<string, unknown>)?.east_asia_family ?? (hfs.font as Record<string, unknown>)?.family ?? '')} {String((hfs.font as Record<string, unknown>)?.size_pt ?? '')}pt</Text>
                  </div>
                )}
              </Space>
            </Panel>
          )
        })()}

        <Panel header="原始 JSON" key="json">
          <TextArea
            value={JSON.stringify(styleConfig, null, 2)}
            rows={12}
            onChange={e => {
              try {
                const parsed = JSON.parse(e.target.value)
                setStyleConfig(parsed)
              } catch {
                // 忽略解析错误
              }
            }}
            style={{ fontFamily: 'monospace', fontSize: 12 }}
          />
        </Panel>
      </Collapse>
    )
  }

  return (
    <div style={{ height: 'calc(100vh - 160px)', display: 'flex', flexDirection: 'column' }}>
      <Row gutter={16} style={{ flex: 1, minHeight: 0 }}>
        {/* 左侧 - 会话列表 */}
        <Col span={4} style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <Card
            size="small"
            style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}
            styles={{ body: { flex: 1, overflowY: 'auto', padding: '8px' } }}
            title={
              <Space>
                <MessageOutlined />
                <Text strong>对话列表</Text>
              </Space>
            }
            extra={
              <Tooltip title="新建对话">
                <Button
                  type="text"
                  icon={<PlusOutlined />}
                  size="small"
                  onClick={handleNewSession}
                />
              </Tooltip>
            }
          >
            {sessionsLoading ? (
              <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>
            ) : sessions.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 20, color: '#999' }}>
                暂无对话记录
              </div>
            ) : (
              <List
                size="small"
                dataSource={sessions}
                renderItem={(session) => (
                  <List.Item
                    style={{
                      cursor: 'pointer',
                      padding: '8px',
                      background: session.id === currentSessionId ? '#e6f4ff' : 'transparent',
                      borderRadius: 4,
                      marginBottom: 4,
                    }}
                    onClick={() => handleSwitchSession(session.id)}
                    actions={[
                      <Popconfirm
                        key="delete"
                        title="确定删除此对话？"
                        onConfirm={(e) => {
                          e?.stopPropagation()
                          handleDeleteSession(session.id)
                        }}
                        onCancel={(e) => e?.stopPropagation()}
                        okText="确定"
                        cancelText="取消"
                      >
                        <Button
                          type="text"
                          size="small"
                          icon={<DeleteOutlined />}
                          onClick={(e) => e.stopPropagation()}
                          danger
                        />
                      </Popconfirm>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Text ellipsis style={{ maxWidth: 120, display: 'inline-block' }}>
                          {session.title}
                        </Text>
                      }
                      description={
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {session.message_count} 条消息
                        </Text>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>

        {/* 中间 - 对话区 */}
        <Col span={12} style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <Card
            size="small"
            style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}
            styles={{ body: { flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, padding: '12px' } }}
            title={
              <Space>
                <RobotOutlined />
                <Text strong>对话排版助手</Text>
                {currentSessionId && (
                  <Tag color="blue" style={{ marginLeft: 8 }}>
                    {sessions.find(s => s.id === currentSessionId)?.title || '对话中'}
                  </Tag>
                )}
              </Space>
            }
            extra={
              <Space>
                <Upload
                  accept=".docx"
                  showUploadList={false}
                  beforeUpload={handleUploadTemplate}
                >
                  <Button icon={<UploadOutlined />} loading={uploadLoading} size="small">
                    上传Word模板
                  </Button>
                </Upload>
                <Button
                  icon={<SaveOutlined />}
                  size="small"
                  onClick={() => setSaveModalVisible(true)}
                >
                  保存为模板
                </Button>
              </Space>
            }
          >
            {messagesLoading ? (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                <Spin />
                <div style={{ marginTop: 8, color: '#999' }}>加载对话历史...</div>
              </div>
            ) : (
              <>
                {/* 消息列表 */}
                <div style={{ flex: 1, overflowY: 'auto', marginBottom: 12 }}>
                  {messages.map((msg, i) => (
                    <div
                      key={i}
                      style={{
                        display: 'flex',
                        flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
                        marginBottom: 12,
                      }}
                    >
                      <div
                        style={{
                          maxWidth: '80%',
                          padding: '8px 12px',
                          borderRadius: 8,
                          background: msg.role === 'user' ? '#e6f4ff' : '#f5f5f5',
                          marginLeft: msg.role === 'user' ? 8 : 0,
                          marginRight: msg.role === 'user' ? 0 : 8,
                        }}
                      >
                        {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                        <span style={{ marginLeft: 6, whiteSpace: 'pre-wrap' }}>{msg.content}</span>
                      </div>
                    </div>
                  ))}
                  {chatLoading && (
                    <div style={{ textAlign: 'center', padding: 12 }}>
                      <Spin size="small" />
                      <Text type="secondary" style={{ marginLeft: 8 }}>AI 思考中...</Text>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>

                {/* 输入区 */}
                <div style={{ flexShrink: 0 }}>
                  {/* 模式切换 */}
                  <div style={{ marginBottom: 8 }}>
                    <Space>
                      <Button
                        type={chatMode === 'style' ? 'primary' : 'default'}
                        size="small"
                        onClick={() => setChatMode('style')}
                      >
                        样式编辑
                      </Button>
                      <Button
                        type={chatMode === 'content' ? 'primary' : 'default'}
                        size="small"
                        onClick={() => setChatMode('content')}
                      >
                        内容编辑
                      </Button>
                      {chatMode === 'content' && (
                        <Select
                          style={{ width: 200 }}
                          placeholder="选择要编辑的任务"
                          value={contentEditTaskId || undefined}
                          onChange={setContentEditTaskId}
                          size="small"
                          options={tasks.map(t => ({ value: t.id, label: t.filename }))}
                        />
                      )}
                    </Space>
                  </div>
                  <Space.Compact style={{ width: '100%' }}>
                    <Input
                      value={inputValue}
                      onChange={e => setInputValue(e.target.value)}
                      onPressEnter={handleSendMessage}
                      placeholder={chatMode === 'content'
                        ? '输入内容修改指令，如：删除第三章、修改标题为...'
                        : '输入排版修改需求，如：正文改为仿宋16pt，标题居中...'
                      }
                      disabled={chatLoading}
                    />
                    <Button
                      type="primary"
                      icon={<SendOutlined />}
                      onClick={handleSendMessage}
                      loading={chatLoading}
                    >
                      发送
                    </Button>
                  </Space.Compact>
                </div>
              </>
            )}
          </Card>
        </Col>

        {/* 右侧 - 样式编辑区 */}
        <Col span={8} style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <Card
            size="small"
            style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}
            styles={{ body: { flex: 1, overflowY: 'auto', padding: '12px' } }}
            title={
              <Space>
                <EyeOutlined />
                <Text strong>样式配置编辑</Text>
              </Space>
            }
            extra={
              <Button
                icon={<ThunderboltOutlined />}
                size="small"
                onClick={() => setPreviewModalVisible(true)}
              >
                应用到任务
              </Button>
            }
          >
            {renderStyleEditor()}
          </Card>
        </Col>
      </Row>

      {/* 保存模板 Modal */}
      <Modal
        title="保存为样式模板"
        open={saveModalVisible}
        onOk={handleSaveTemplate}
        onCancel={() => setSaveModalVisible(false)}
        okText="保存"
        cancelText="取消"
      >
        <Form form={saveForm} layout="vertical">
          <Form.Item
            name="name"
            label="模板名称"
            rules={[{ required: true, message: '请输入模板名称' }]}
          >
            <Input placeholder="如：国标公文模板" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={3} placeholder="可选：模板描述" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 应用到任务 Modal */}
      <Modal
        title="应用样式到任务"
        open={previewModalVisible}
        onOk={handleApplyToTask}
        onCancel={() => setPreviewModalVisible(false)}
        okText="应用"
        cancelText="取消"
        confirmLoading={applying}
      >
        <Text type="secondary">选择一个已完成的任务，将当前样式配置应用并重新生成 DOCX：</Text>
        <Select
          style={{ width: '100%', marginTop: 8 }}
          placeholder="选择任务"
          value={selectedTaskId || undefined}
          onChange={v => setSelectedTaskId(v)}
          showSearch
          optionFilterProp="label"
          options={tasks.map(t => ({ value: t.id, label: t.filename }))}
        />
      </Modal>
    </div>
  )
}

export default ChatPage
