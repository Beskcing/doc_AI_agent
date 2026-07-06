import React, { useState, useEffect, useCallback } from 'react'
import {
  Card,
  Table,
  Button,
  Space,
  Typography,
  Tag,
  Modal,
  Form,
  Input,
  Upload,
  message,
  Popconfirm,
  Empty,
  Spin,
  Collapse,
  Select,
  InputNumber,
  Row,
  Col,
} from 'antd'
import {
  UploadOutlined,
  EditOutlined,
  DeleteOutlined,
  EyeOutlined,
  PlusOutlined,
  FileWordOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  listTemplates,
  saveTemplate,
  updateTemplate,
  deleteTemplate,
  uploadTemplate,
} from '../services/api'

const { Text } = Typography
const { TextArea } = Input

interface TemplateItem {
  id: string
  name: string
  description: string | null
  style_config: Record<string, unknown>
  source_docx_path: string | null
  created_at: string
  updated_at: string
}

const TemplatesPage: React.FC = () => {
  const [templates, setTemplates] = useState<TemplateItem[]>([])
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  // 上传提取
  const [uploadLoading, setUploadLoading] = useState(false)
  const [extractedConfig, setExtractedConfig] = useState<Record<string, unknown> | null>(null)
  const [extractedDocxPath, setExtractedDocxPath] = useState('')
  const [extractedFilename, setExtractedFilename] = useState('')
  const [createModalVisible, setCreateModalVisible] = useState(false)
  const [createForm] = Form.useForm()

  // 编辑
  const [editModalVisible, setEditModalVisible] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<TemplateItem | null>(null)
  const [editForm] = Form.useForm()
  const [editStyleConfig, setEditStyleConfig] = useState<Record<string, unknown> | null>(null)
  const [editJsonText, setEditJsonText] = useState('')
  const [editJsonError, setEditJsonError] = useState('')
  const [savingEdit, setSavingEdit] = useState(false)

  // 查看
  const [viewModalVisible, setViewModalVisible] = useState(false)
  const [viewingTemplate, setViewingTemplate] = useState<TemplateItem | null>(null)

  const fetchTemplates = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listTemplates({ page, page_size: pageSize })
      setTemplates(res.data.data.items)
      setTotal(res.data.data.total)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '获取模板列表失败')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize])

  useEffect(() => {
    fetchTemplates()
  }, [fetchTemplates])

  // 上传 docx 提取样式
  const handleUploadExtract = async (file: File) => {
    setUploadLoading(true)
    try {
      const res = await uploadTemplate(file)
      const data = res.data.data
      setExtractedConfig(data.style_config)
      setExtractedDocxPath(data.source_docx_path || '')
      setExtractedFilename(data.filename || file.name)
      setCreateModalVisible(true)
      createForm.setFieldsValue({
        name: data.filename ? data.filename.replace(/\.docx$/i, '') : '',
        description: `从 ${file.name} 提取的排版模板`,
      })
      message.success('样式提取成功，请填写模板信息保存')
    } catch (err) {
      message.error(err instanceof Error ? err.message : '模板提取失败')
    } finally {
      setUploadLoading(false)
    }
    return false
  }

  const handleSaveNewTemplate = async () => {
    try {
      const values = await createForm.validateFields()
      await saveTemplate({
        name: values.name,
        style_config: extractedConfig!,
        description: values.description,
        source_docx_path: extractedDocxPath || undefined,
      })
      message.success('模板保存成功')
      setCreateModalVisible(false)
      setExtractedConfig(null)
      setExtractedDocxPath('')
      createForm.resetFields()
      fetchTemplates()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    }
  }

  // 编辑模板
  const handleEdit = async (template: TemplateItem) => {
    setEditingTemplate(template)
    setEditStyleConfig(template.style_config)
    setEditJsonText(JSON.stringify(template.style_config, null, 2))
    setEditJsonError('')
    editForm.setFieldsValue({
      name: template.name,
      description: template.description || '',
    })
    setEditModalVisible(true)
  }

  const handleSaveEdit = async () => {
    if (!editingTemplate) return

    // 验证 JSON
    let parsedConfig = editStyleConfig
    if (editJsonText.trim()) {
      try {
        parsedConfig = JSON.parse(editJsonText)
        setEditJsonError('')
      } catch {
        setEditJsonError('JSON 格式错误，请检查')
        return
      }
    }

    setSavingEdit(true)
    try {
      const values = await editForm.validateFields()
      await updateTemplate(editingTemplate.id, {
        name: values.name,
        description: values.description,
        style_config: parsedConfig!,
      })
      message.success('模板更新成功')
      setEditModalVisible(false)
      setEditingTemplate(null)
      fetchTemplates()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '更新失败')
    } finally {
      setSavingEdit(false)
    }
  }

  // 删除模板
  const handleDelete = async (id: string) => {
    try {
      await deleteTemplate(id)
      message.success('模板已删除')
      fetchTemplates()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败')
    }
  }

  // 查看模板
  const handleView = (template: TemplateItem) => {
    setViewingTemplate(template)
    setViewModalVisible(true)
  }

  const columns = [
    {
      title: '模板名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (name: string) => <Text strong>{name}</Text>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (desc: string | null) =>
        desc ? <Text type="secondary">{desc}</Text> : <Text type="secondary">-</Text>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (t: string) => (t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: unknown, record: TemplateItem) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleView(record)}
          >
            查看
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定删除此模板？"
            onConfirm={() => handleDelete(record.id)}
            okText="删除"
            cancelText="取消"
          >
            <Button type="link" size="small" icon={<DeleteOutlined />} danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // 渲染样式配置摘要
  const renderStyleSummary = (config: Record<string, unknown>) => {
    const pl = config.page_layout as Record<string, unknown> | undefined
    const bs = config.body_style as Record<string, unknown> | undefined
    const bodyFont = bs?.font as Record<string, unknown> | undefined
    const hs = config.heading_styles as Array<Record<string, unknown>> | undefined
    const ts = config.table_style as Record<string, unknown> | undefined

    const items: React.ReactNode[] = []

    if (pl) {
      items.push(
        <Tag key="page" color="blue">
          {String(pl.paper_size || 'A4')} {String(pl.orientation || '纵向')}
        </Tag>
      )
    }
    if (bodyFont) {
      items.push(
        <Tag key="body" color="green">
          正文: {String(bodyFont.east_asia_family || bodyFont.family || '')} {String(bodyFont.size_pt || '')}pt
        </Tag>
      )
    }
    if (hs && hs.length > 0) {
      items.push(
        <Tag key="headings" color="orange">
          {hs.length} 级标题
        </Tag>
      )
    }
    if (ts) {
      items.push(
        <Tag key="table" color="purple">
          表格: {String(ts.border_style || '单线')}
        </Tag>
      )
    }

    return <Space wrap size={[4, 4]}>{items}</Space>
  }

  // 样式编辑器（用于编辑 Modal）
  const renderStyleEditor = () => {
    if (!editStyleConfig) return null
    const pl = editStyleConfig.page_layout as Record<string, unknown> | undefined
    const bs = editStyleConfig.body_style as Record<string, unknown> | undefined
    const bodyFont = bs?.font as Record<string, unknown> | undefined

    const updateField = (section: string, field: string, value: unknown) => {
      const sectionData = editStyleConfig[section] as Record<string, unknown> | undefined
      const newConfig = {
        ...editStyleConfig,
        [section]: { ...sectionData, [field]: value },
      }
      setEditStyleConfig(newConfig)
      setEditJsonText(JSON.stringify(newConfig, null, 2))
    }

    const updateFontField = (section: string, field: string, value: unknown) => {
      const sectionData = editStyleConfig[section] as Record<string, unknown> | undefined
      const fontData = sectionData?.font as Record<string, unknown> | undefined
      const newConfig = {
        ...editStyleConfig,
        [section]: { ...sectionData, font: { ...fontData, [field]: value } },
      }
      setEditStyleConfig(newConfig)
      setEditJsonText(JSON.stringify(newConfig, null, 2))
    }

    return (
      <Collapse defaultActiveKey={['page', 'body', 'json']} size="small" style={{ marginBottom: 16 }}>
        <Collapse.Panel header="页面布局" key="page">
          <Row gutter={8}>
            <Col span={12}>
              <Text type="secondary">纸张</Text>
              <Select
                value={String(pl?.paper_size || 'A4')}
                style={{ width: '100%' }}
                size="small"
                onChange={v => updateField('page_layout', 'paper_size', v)}
                options={[{ value: 'A4', label: 'A4' }, { value: 'A3', label: 'A3' }, { value: 'B5', label: 'B5' }]}
              />
            </Col>
            <Col span={6}>
              <Text type="secondary">上边距</Text>
              <InputNumber
                value={pl?.margin_top_cm as number}
                style={{ width: '100%' }}
                size="small"
                step={0.1}
                onChange={v => updateField('page_layout', 'margin_top_cm', v)}
              />
            </Col>
            <Col span={6}>
              <Text type="secondary">下边距</Text>
              <InputNumber
                value={pl?.margin_bottom_cm as number}
                style={{ width: '100%' }}
                size="small"
                step={0.1}
                onChange={v => updateField('page_layout', 'margin_bottom_cm', v)}
              />
            </Col>
          </Row>
          <Row gutter={8} style={{ marginTop: 8 }}>
            <Col span={6}>
              <Text type="secondary">左边距</Text>
              <InputNumber
                value={pl?.margin_left_cm as number}
                style={{ width: '100%' }}
                size="small"
                step={0.1}
                onChange={v => updateField('page_layout', 'margin_left_cm', v)}
              />
            </Col>
            <Col span={6}>
              <Text type="secondary">右边距</Text>
              <InputNumber
                value={pl?.margin_right_cm as number}
                style={{ width: '100%' }}
                size="small"
                step={0.1}
                onChange={v => updateField('page_layout', 'margin_right_cm', v)}
              />
            </Col>
          </Row>
        </Collapse.Panel>

        <Collapse.Panel header="正文样式" key="body">
          <Row gutter={8}>
            <Col span={12}>
              <Text type="secondary">中文字体</Text>
              <Input
                value={String(bodyFont?.east_asia_family || bodyFont?.family || '')}
                size="small"
                onChange={e => updateFontField('body_style', 'east_asia_family', e.target.value)}
              />
            </Col>
            <Col span={6}>
              <Text type="secondary">字号(pt)</Text>
              <InputNumber
                value={bodyFont?.size_pt as number}
                style={{ width: '100%' }}
                size="small"
                step={0.5}
                onChange={v => updateFontField('body_style', 'size_pt', v)}
              />
            </Col>
            <Col span={6}>
              <Text type="secondary">加粗</Text>
              <Select
                value={bodyFont?.bold ? 'yes' : 'no'}
                style={{ width: '100%' }}
                size="small"
                onChange={v => updateFontField('body_style', 'bold', v === 'yes')}
                options={[{ value: 'no', label: '否' }, { value: 'yes', label: '是' }]}
              />
            </Col>
          </Row>
          <Row gutter={8} style={{ marginTop: 8 }}>
            <Col span={8}>
              <Text type="secondary">行距</Text>
              <InputNumber
                value={bs?.line_spacing as number}
                style={{ width: '100%' }}
                size="small"
                step={0.1}
                onChange={v => updateField('body_style', 'line_spacing', v)}
              />
            </Col>
            <Col span={8}>
              <Text type="secondary">首行缩进(字)</Text>
              <InputNumber
                value={bs?.first_line_indent_chars as number}
                style={{ width: '100%' }}
                size="small"
                step={0.5}
                onChange={v => updateField('body_style', 'first_line_indent_chars', v)}
              />
            </Col>
            <Col span={8}>
              <Text type="secondary">对齐</Text>
              <Select
                value={String(bs?.alignment || 'left')}
                style={{ width: '100%' }}
                size="small"
                onChange={v => updateField('body_style', 'alignment', v)}
                options={[
                  { value: 'left', label: '左对齐' },
                  { value: 'center', label: '居中' },
                  { value: 'right', label: '右对齐' },
                  { value: 'justify', label: '两端对齐' },
                ]}
              />
            </Col>
          </Row>
        </Collapse.Panel>

        <Collapse.Panel header="原始 JSON 编辑" key="json">
          <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
            直接编辑 JSON，修改后自动同步到上方表单
          </Text>
          {editJsonError && <Text type="danger" style={{ display: 'block', marginBottom: 4 }}>{editJsonError}</Text>}
          <TextArea
            value={editJsonText}
            rows={16}
            onChange={e => {
              setEditJsonText(e.target.value)
              try {
                const parsed = JSON.parse(e.target.value)
                setEditStyleConfig(parsed)
                setEditJsonError('')
              } catch {
                setEditJsonError('JSON 格式错误，保存时将使用表单值')
              }
            }}
            style={{ fontFamily: 'monospace', fontSize: 12 }}
          />
        </Collapse.Panel>
      </Collapse>
    )
  }

  return (
    <div>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>模板管理</h2>
        <Space>
          <Upload accept=".docx" showUploadList={false} beforeUpload={handleUploadExtract}>
            <Button icon={<UploadOutlined />} loading={uploadLoading}>
              上传 Word 模板提取
            </Button>
          </Upload>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => {
            setExtractedConfig(null)
            setExtractedDocxPath('')
            createForm.resetFields()
            setCreateModalVisible(true)
          }}>
            手动创建
          </Button>
        </Space>
      </Space>

      <Card>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin tip="加载中..." />
          </div>
        ) : templates.length === 0 ? (
          <Empty description="暂无模板，点击「上传 Word 模板提取」创建">
            <Upload accept=".docx" showUploadList={false} beforeUpload={handleUploadExtract}>
              <Button type="primary" icon={<UploadOutlined />} loading={uploadLoading}>
                上传 Word 模板
              </Button>
            </Upload>
          </Empty>
        ) : (
          <Table
            dataSource={templates}
            columns={columns}
            rowKey="id"
            size="middle"
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: true,
              showTotal: (t) => `共 ${t} 个模板`,
              onChange: (p, ps) => {
                setPage(p)
                setPageSize(ps)
              },
            }}
            expandable={{
              expandedRowRender: (record) => (
                <div style={{ padding: '8px 0' }}>
                  {renderStyleSummary(record.style_config)}
                </div>
              ),
            }}
          />
        )}
      </Card>

      {/* 创建模板 Modal */}
      <Modal
        title="保存样式模板"
        open={createModalVisible}
        onOk={handleSaveNewTemplate}
        onCancel={() => {
          setCreateModalVisible(false)
          setExtractedConfig(null)
        }}
        okText="保存"
        cancelText="取消"
        width={700}
      >
        {extractedConfig ? (
          <div>
            <Tag color="success" style={{ marginBottom: 12 }}>
              <FileWordOutlined /> 已从 {extractedFilename} 提取样式
            </Tag>
            <Form form={createForm} layout="vertical">
              <Form.Item
                name="name"
                label="模板名称"
                rules={[{ required: true, message: '请输入模板名称' }]}
              >
                <Input placeholder="如：GB/T 14454 国标模板" />
              </Form.Item>
              <Form.Item name="description" label="描述">
                <TextArea rows={2} placeholder="可选" />
              </Form.Item>
            </Form>
            <div style={{ marginTop: 8 }}>
              <Text type="secondary">样式配置摘要：</Text>
              <div style={{ marginTop: 4 }}>{renderStyleSummary(extractedConfig)}</div>
            </div>
          </div>
        ) : (
          <Form form={createForm} layout="vertical">
            <Form.Item
              name="name"
              label="模板名称"
              rules={[{ required: true, message: '请输入模板名称' }]}
            >
              <Input placeholder="如：国标公文模板" />
            </Form.Item>
            <Form.Item name="description" label="描述">
              <TextArea rows={2} placeholder="可选" />
            </Form.Item>
            <Form.Item
              name="style_config_json"
              label="样式配置 JSON"
              rules={[{ required: true, message: '请输入样式配置' }]}
            >
              <TextArea
                rows={12}
                placeholder='{"page_layout": {...}, "body_style": {...}, ...}'
                style={{ fontFamily: 'monospace', fontSize: 12 }}
                onChange={e => {
                  try {
                    setExtractedConfig(JSON.parse(e.target.value))
                  } catch {
                    // 忽略
                  }
                }}
              />
            </Form.Item>
          </Form>
        )}
      </Modal>

      {/* 编辑模板 Modal */}
      <Modal
        title="编辑模板"
        open={editModalVisible}
        onOk={handleSaveEdit}
        onCancel={() => {
          setEditModalVisible(false)
          setEditingTemplate(null)
        }}
        okText="保存"
        cancelText="取消"
        width={800}
        confirmLoading={savingEdit}
      >
        {editingTemplate && (
          <div>
            <Form form={editForm} layout="vertical" style={{ marginBottom: 16 }}>
              <Form.Item
                name="name"
                label="模板名称"
                rules={[{ required: true, message: '请输入模板名称' }]}
              >
                <Input />
              </Form.Item>
              <Form.Item name="description" label="描述">
                <TextArea rows={2} />
              </Form.Item>
            </Form>
            {renderStyleEditor()}
          </div>
        )}
      </Modal>

      {/* 查看模板 Modal */}
      <Modal
        title="模板详情"
        open={viewModalVisible}
        onCancel={() => {
          setViewModalVisible(false)
          setViewingTemplate(null)
        }}
        footer={null}
        width={700}
      >
        {viewingTemplate && (
          <div>
            <DescriptionsCompact template={viewingTemplate} />
            <div style={{ marginTop: 16 }}>
              <Text strong>样式配置：</Text>
              <pre
                style={{
                  background: '#f5f5f5',
                  padding: 16,
                  borderRadius: 8,
                  fontSize: 12,
                  maxHeight: 400,
                  overflow: 'auto',
                  fontFamily: 'monospace',
                }}
              >
                {JSON.stringify(viewingTemplate.style_config, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}

// 简单描述列表组件
const DescriptionsCompact: React.FC<{ template: TemplateItem }> = ({ template }) => {
  const items: Array<{ label: string; value: string }> = [
    { label: '模板名称', value: template.name },
    { label: '描述', value: template.description || '-' },
    { label: '创建时间', value: template.created_at ? dayjs(template.created_at).format('YYYY-MM-DD HH:mm:ss') : '-' },
    { label: '更新时间', value: template.updated_at ? dayjs(template.updated_at).format('YYYY-MM-DD HH:mm:ss') : '-' },
    { label: '源文件', value: template.source_docx_path || '-' },
  ]
  return (
    <div>
      {items.map((item, i) => (
        <Row key={i} style={{ marginBottom: 8 }}>
          <Col span={6}>
            <Text type="secondary">{item.label}：</Text>
          </Col>
          <Col span={18}>
            <Text>{item.value}</Text>
          </Col>
        </Row>
      ))}
    </div>
  )
}

export default TemplatesPage
