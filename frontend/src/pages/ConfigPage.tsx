import React, { useState, useEffect } from 'react'
import { Card, Form, Input, InputNumber, Select, Button, message } from 'antd'
import { SaveOutlined } from '@ant-design/icons'
import { getConfig, updateConfig } from '../services/api'

const ConfigPage: React.FC = () => {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const fetchConfig = async () => {
    setLoading(true)
    try {
      const res = await getConfig()
      form.setFieldsValue(res.data.data)
    } catch (error: any) {
      message.error(error.message || '获取配置失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchConfig()
  }, [])

  const handleSave = async () => {
    try {
      const values = form.getFieldsValue()
      setSaving(true)
      await updateConfig(values)
      message.success('配置保存成功')
    } catch (error: any) {
      message.error(error.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <h2>系统配置</h2>
      <Card loading={loading}>
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item
            label="LLM Provider"
            name="llm_provider"
            rules={[{ required: true }]}
          >
            <Select>
              <Select.Option value="qwen">通义千问</Select.Option>
              <Select.Option value="glm">智谱</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            label="LLM 模型"
            name="llm_model"
            rules={[{ required: true }]}
          >
            <Input />
          </Form.Item>

          <Form.Item label="BM25 权重" name="rag_bm25_weight">
            <InputNumber min={0} max={1} step={0.1} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item label="向量权重" name="rag_vector_weight">
            <InputNumber min={0} max={1} step={0.1} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item label="Top-K 检索数量" name="rag_top_k">
            <InputNumber min={1} max={20} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item label="Pandoc 路径" name="pandoc_path">
            <Input />
          </Form.Item>

          <Form.Item label="输出目录" name="output_dir">
            <Input />
          </Form.Item>

          <Form.Item label="最大文件大小 (MB)" name="max_file_size_mb">
            <InputNumber min={1} max={500} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={saving} icon={<SaveOutlined />}>
              保存配置
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}

export default ConfigPage
