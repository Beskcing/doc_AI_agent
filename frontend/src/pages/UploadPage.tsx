import React, { useState } from 'react'
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
} from 'antd'
import { FilePdfOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'
import { uploadFile, createTask } from '../services/api'

const { Step } = Steps
const { Text } = Typography

const UploadPage: React.FC = () => {
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [uploading, setUploading] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)
  const [uploadId, setUploadId] = useState<string | null>(null)
  const [form] = Form.useForm()
  const navigate = useNavigate()

  const handleUpload = async () => {
    if (fileList.length === 0) {
      message.warning('请先选择文件')
      return
    }

    const file = fileList[0].originFileObj
    if (!file) return

    setUploading(true)
    try {
      const res = await uploadFile(file)
      setUploadId(res.data.data.upload_id)
      message.success('文件上传成功')
      setCurrentStep(1)
    } catch (error: any) {
      message.error(error.message || '上传失败')
    } finally {
      setUploading(false)
    }
  }

  const handleCreateTask = async () => {
    if (!uploadId) {
      message.warning('请先上传文件')
      return
    }

    const values = form.getFieldsValue()
    try {
      const res = await createTask({
        upload_id: uploadId,
        standard: values.standard,
        use_rag: values.use_rag,
        llm_model: values.llm_model,
      })
      message.success('任务创建成功')
      setCurrentStep(2)
      // 跳转到任务详情
      const taskId = res.data.data.id
      setTimeout(() => {
        navigate(`/tasks/${taskId}`)
      }, 1500)
    } catch (error: any) {
      message.error(error.message || '创建任务失败')
    }
  }

  const uploadProps = {
    onRemove: () => setFileList([]),
    beforeUpload: (file: UploadFile) => {
      setFileList([file])
      return false
    },
    fileList,
    accept: '.pdf,.md,.txt',
    maxCount: 1,
  }

  return (
    <div>
      <h2>文档上传</h2>
      <Steps current={currentStep} style={{ marginBottom: 40 }}>
        <Step title="上传文件" description="选择 PDF/MD 文件" />
        <Step title="配置排版" description="选择排版规范" />
        <Step title="开始处理" description="提交处理任务" />
      </Steps>

      {currentStep === 0 && (
        <Card>
          <Upload.Dragger {...uploadProps} style={{ padding: 40 }}>
            <p className="ant-upload-drag-icon">
              <FilePdfOutlined style={{ fontSize: 48, color: '#1890ff' }} />
            </p>
            <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
            <p className="ant-upload-hint">支持 PDF、Markdown 文件</p>
          </Upload.Dragger>
          <div style={{ marginTop: 24, textAlign: 'center' }}>
            <Button
              type="primary"
              onClick={handleUpload}
              loading={uploading}
              disabled={fileList.length === 0}
              size="large"
            >
              {uploading ? '上传中...' : '开始上传'}
            </Button>
          </div>
        </Card>
      )}

      {currentStep === 1 && (
        <Card title="排版配置">
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
              <Select>
                <Select.Option value="GB/T 9704">党政机关公文格式</Select.Option>
                <Select.Option value="GB/T 7713">科技报告编写格式</Select.Option>
                <Select.Option value="custom">自定义规范</Select.Option>
              </Select>
            </Form.Item>

            <Form.Item
              label="LLM 模型"
              name="llm_model"
            >
              <Select>
                <Select.Option value="qwen-plus">通义千问 Plus</Select.Option>
                <Select.Option value="qwen-max">通义千问 Max</Select.Option>
                <Select.Option value="glm-4">智谱 GLM-4</Select.Option>
              </Select>
            </Form.Item>

            <Form.Item
              label="使用 RAG 知识库"
              name="use_rag"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>

            <Form.Item>
              <Space>
                <Button onClick={() => setCurrentStep(0)}>上一步</Button>
                <Button type="primary" onClick={handleCreateTask}>
                  提交任务
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </Card>
      )}

      {currentStep === 2 && (
        <Card style={{ textAlign: 'center', padding: 40 }}>
          <Progress type="circle" percent={100} status="success" />
          <h3 style={{ marginTop: 24 }}>任务创建成功</h3>
          <Text type="secondary">正在跳转到任务详情页...</Text>
        </Card>
      )}
    </div>
  )
}

export default UploadPage
