import React, { useState, useEffect } from 'react'
import {
  Table,
  Button,
  Upload,
  message,
  Popconfirm,
  Space,
  Card,
} from 'antd'
import { UploadOutlined, ReloadOutlined, DeleteOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'
import { listKbDocuments, uploadKbDocument, deleteKbDocument, rebuildKbIndex } from '../services/api'

interface KbDocument {
  key: string
  id: string
  name: string
  source: string
  status: string
  chunk_count: number
  created_at: string
}

const KbPage: React.FC = () => {
  const [documents, setDocuments] = useState<KbDocument[]>([])
  const [loading, setLoading] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)

  const fetchDocuments = async () => {
    setLoading(true)
    try {
      const res = await listKbDocuments()
      const data = res.data.data
      setDocuments(
        data.items.map((item: KbDocument) => ({ ...item, key: item.id }))
      )
    } catch (error: any) {
      message.error(error.message || '获取知识库文档失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDocuments()
  }, [])

  const handleUpload = async (file: UploadFile) => {
    if (!file.originFileObj) return
    try {
      await uploadKbDocument(file.originFileObj)
      message.success('上传成功')
      fetchDocuments()
    } catch (error: any) {
      message.error(error.message || '上传失败')
    }
  }

  const handleDelete = async (docId: string) => {
    try {
      await deleteKbDocument(docId)
      message.success('删除成功')
      fetchDocuments()
    } catch (error: any) {
      message.error(error.message || '删除失败')
    }
  }

  const handleRebuild = async () => {
    setRebuilding(true)
    try {
      await rebuildKbIndex()
      message.success('重建索引已启动')
    } catch (error: any) {
      message.error(error.message || '重建失败')
    } finally {
      setRebuilding(false)
    }
  }

  const columns = [
    { title: '文档名称', dataIndex: 'name', key: 'name' },
    { title: '来源', dataIndex: 'source', key: 'source', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <span style={{ color: status === 'indexed' ? '#52c41a' : '#faad14' }}>
          {status === 'indexed' ? '已索引' : status}
        </span>
      ),
    },
    { title: '切片数', dataIndex: 'chunk_count', key: 'chunk_count', width: 100 },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: unknown, record: KbDocument) => (
        <Popconfirm
          title="确认删除?"
          onConfirm={() => handleDelete(record.id)}
        >
          <Button type="link" danger icon={<DeleteOutlined />}>
            删除
          </Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div>
      <h2>知识库管理</h2>
      <Card style={{ marginBottom: 24 }}>
        <Space>
          <Upload
            accept=".md,.txt,.pdf"
            showUploadList={false}
            beforeUpload={(file) => {
              handleUpload(file as unknown as UploadFile)
              return false
            }}
          >
            <Button icon={<UploadOutlined />}>添加规范文档</Button>
          </Upload>
          <Button
            icon={<ReloadOutlined />}
            onClick={handleRebuild}
            loading={rebuilding}
          >
            重建索引
          </Button>
        </Space>
      </Card>

      <Table columns={columns} dataSource={documents} loading={loading} />
    </div>
  )
}

export default KbPage
