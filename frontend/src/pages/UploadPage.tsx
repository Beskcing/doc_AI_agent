import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card,
  Steps,
  Upload,
  Button,
  Select,
  Switch,
  Form,
  message,
  Progress,
  Space,
  Typography,
  Table,
  Tag,
} from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'
import {
  batchUploadFiles,
  batchCreateTasks,
  getSupportedStandards,
  getLlmModels,
  listTemplates,
} from '../services/api'

const { Step } = Steps
const { Text } = Typography
const { Dragger } = Upload

interface UploadedFile {
  upload_id: string
  filename: string
  file_size: number
  content_type: string
}

const UploadPage: React.FC = () => {
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [uploading, setUploading] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])
  const [form] = Form.useForm()
  const navigate = useNavigate()

  const [standards, setStandards] = useState<Array<{ value: string; label: string }>>([
    { value: 'GB/T 9704', label: '党政机关公文格式' },
    { value: 'GB/T 7713', label: '科技报告编写格式' },
    { value: 'custom', label: '自定义规范' },
  ])
  const [llmModels, setLlmModels] = useState<Array<{ value: string; label: string }>>([
    { value: 'qwen-plus', label: '通义千问 Plus' },
    { value: 'glm-4', label: '智谱 GLM-4' },
  ])
  const [templates, setTemplates] = useState<Array<{ value: string; label: string }>>([])

  useEffect(() => {
    const loadOptions = async () => {
      try {
        const [stdRes, modelRes, tplRes] = await Promise.all([getSupportedStandards(), getLlmModels(), listTemplates()])
        if (stdRes.data.data?.length) setStandards(stdRes.data.data)
        if (modelRes.data.data?.length) setLlmModels(modelRes.data.data)
        if (tplRes.data.data?.items?.length) {
          setTemplates(tplRes.data.data.items.map((t: { id: string; name: string }) => ({ value: t.id, label: t.name })))
        }
      } catch {
        // 使用默认值
      }
    }
    loadOptions()
  }, [])

  const handleUpload = async () => {
    if (fileList.length === 0) {
      message.warning('请先选择文件')
      return
    }

    const files = fileList
      .map((f) => f.originFileObj as File)
      .filter((f): f is File => !!f)
    if (files.length === 0) return

    setUploading(true)
    try {
      const res = await batchUploadFiles(files)
      const results: UploadedFile[] = res.data.data.results
      setUploadedFiles(results)
      message.success(`成功上传 ${results.length} 个文件`)
      setCurrentStep(1)
    } catch (error: any) {
      message.error(error.message || '上传失败')
    } finally {
      setUploading(false)
    }
  }

  const handleCreateTasks = async () => {
    if (uploadedFiles.length === 0) {
      message.warning('请先上传文件')
      return
    }

    const values = form.getFieldsValue()
    try {
      const res = await batchCreateTasks({
        items: uploadedFiles.map((f) => ({
          upload_id: f.upload_id,
          filename: f.filename,
        })),
        standard: values.standard,
        use_rag: values.use_rag,
        llm_model: values.llm_model,
        template_id: values.template_id || undefined,
      })
      const count = res.data.data.count
      message.success(`成功创建 ${count} 个任务`)
      setCurrentStep(2)
      setTimeout(() => {
        navigate('/tasks')
      }, 1500)
    } catch (error: any) {
      message.error(error.message || '创建任务失败')
    }
  }

  const uploadProps = {
    onRemove: (file: UploadFile) => {
      setFileList((prev) => prev.filter((f) => f.uid !== file.uid))
    },
    beforeUpload: (file: UploadFile) => {
      setFileList((prev) => [...prev, file])
      return false
    },
    fileList,
    accept: '.pdf,.md,.txt',
    multiple: true,
  }

  const uploadedColumns = [
    {
      title: '文件名',
      dataIndex: 'filename',
      key: 'filename',
      ellipsis: true,
    },
    {
      title: '大小',
      dataIndex: 'file_size',
      key: 'file_size',
      width: 120,
      render: (size: number) => {
        if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
        return `${(size / 1024 / 1024).toFixed(2)} MB`
      },
    },
    {
      title: '状态',
      key: 'status',
      width: 100,
      render: () => <Tag color="success">已上传</Tag>,
    },
  ]

  return (
    <div>
      <h2>文档上传</h2>
      <Steps current={currentStep} style={{ marginBottom: 40 }}>
        <Step title="上传文件" description="选择一个或多个文件" />
        <Step title="配置排版" description="选择排版规范（共享）" />
        <Step title="开始处理" description="提交批量任务" />
      </Steps>

      {currentStep === 0 && (
        <Card>
          <Dragger {...uploadProps} style={{ padding: 40 }}>
            <p className="ant-upload-drag-icon">
              <InboxOutlined style={{ fontSize: 48, color: '#1890ff' }} />
            </p>
            <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
            <p className="ant-upload-hint">支持 PDF、Markdown、TXT 文件，可同时选择多个文件</p>
          </Dragger>
          {fileList.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <Text type="secondary">已选择 {fileList.length} 个文件</Text>
            </div>
          )}
          <div style={{ marginTop: 24, textAlign: 'center' }}>
            <Button
              type="primary"
              onClick={handleUpload}
              loading={uploading}
              disabled={fileList.length === 0}
              size="large"
            >
              {uploading ? '上传中...' : `开始上传${fileList.length > 0 ? ` (${fileList.length} 个文件)` : ''}`}
            </Button>
          </div>
        </Card>
      )}

      {currentStep === 1 && (
        <Card title="排版配置">
          <div style={{ marginBottom: 24 }}>
            <Text strong>已上传文件（{uploadedFiles.length} 个）：</Text>
            <Table
              dataSource={uploadedFiles}
              columns={uploadedColumns}
              rowKey="upload_id"
              size="small"
              pagination={false}
              style={{ marginTop: 12 }}
            />
          </div>
          <Form form={form} layout="vertical" initialValues={{
            standard: 'GB/T 9704',
            use_rag: true,
            llm_model: 'qwen-plus',
          }}>
            <Form.Item
              label="排版规范"
              name="standard"
              rules={[{ required: true, message: '请选择排版规范' }]}
            >
              <Select options={standards} />
            </Form.Item>

            <Form.Item
              label="LLM 模型"
              name="llm_model"
            >
              <Select options={llmModels} />
            </Form.Item>

            <Form.Item
              label="使用 RAG 知识库"
              name="use_rag"
              valuePropName="checked"
              tooltip="启用后将从知识库中检索排版规范"
            >
              <Switch />
            </Form.Item>

            <Form.Item
              label="样式模板"
              name="template_id"
              tooltip="选择模板后将跳过 LLM 样式提取，直接使用模板样式。在对话排版页面创建模板。"
            >
              <Select
                options={templates}
                allowClear
                placeholder="不选择则使用 LLM 自动提取样式"
              />
            </Form.Item>

            <Form.Item>
              <Space>
                <Button onClick={() => setCurrentStep(0)}>上一步</Button>
                <Button type="primary" onClick={handleCreateTasks}>
                  提交 {uploadedFiles.length} 个任务
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </Card>
      )}

      {currentStep === 2 && (
        <Card style={{ textAlign: 'center', padding: 40 }}>
          <Progress type="circle" percent={100} status="success" />
          <h3 style={{ marginTop: 24 }}>批量任务创建成功</h3>
          <Text type="secondary">正在跳转到任务列表页...</Text>
        </Card>
      )}
    </div>
  )
}

export default UploadPage
