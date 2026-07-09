import React, { useState, useEffect, useCallback } from 'react'
import {
  Table,
  Button,
  Upload,
  message,
  Popconfirm,
  Space,
  Card,
  Modal,
  Input,
  Checkbox,
} from 'antd'
import { UploadOutlined, ReloadOutlined, DeleteOutlined, EyeOutlined, EditOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { listKbDocuments, uploadKbDocument, deleteKbDocument, rebuildKbIndex, getKbDocumentContent, updateKbDocumentContent } from '../services/api'

interface KbDocument {
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
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10, total: 0 })
  const [uploading, setUploading] = useState(false)
  const [viewModalOpen, setViewModalOpen] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [currentDoc, setCurrentDoc] = useState<KbDocument | null>(null)
  const [docContent, setDocContent] = useState('')
  const [editContent, setEditContent] = useState('')
  const [contentLoading, setContentLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [rebuildAfterSave, setRebuildAfterSave] = useState(false)

  const fetchDocuments = useCallback(async (page = 1, pageSize = 10) => {
    setLoading(true)
    try {
      const res = await listKbDocuments({ page, page_size: pageSize })
      const data = res.data.data
      setDocuments(data.items || [])
      setPagination({
        current: data.page || 1,
        pageSize: data.page_size || 10,
        total: data.total || 0,
      })
    } catch (error: any) {
      message.error(error.message || '获取知识库文档失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  const handleUpload = async (file: File) => {
    setUploading(true)
    try {
      await uploadKbDocument(file)
      message.success('上传成功')
      fetchDocuments(pagination.current, pagination.pageSize)
    } catch (error: any) {
      message.error(error.message || '上传失败')
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (docId: string) => {
    try {
      await deleteKbDocument(docId)
      message.success('删除成功')
      fetchDocuments(pagination.current, pagination.pageSize)
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

  const handleView = async (record: KbDocument) => {
    setCurrentDoc(record)
    setViewModalOpen(true)
    setContentLoading(true)
    try {
      const res = await getKbDocumentContent(record.id)
      setDocContent(res.data.data.content || '')
    } catch (error: any) {
      message.error(error.message || '获取文档内容失败')
      setDocContent('')
    } finally {
      setContentLoading(false)
    }
  }

  const handleEdit = async (record: KbDocument) => {
    setCurrentDoc(record)
    setEditModalOpen(true)
    setContentLoading(true)
    setRebuildAfterSave(false)
    try {
      const res = await getKbDocumentContent(record.id)
      const content = res.data.data.content || ''
      setEditContent(content)
    } catch (error: any) {
      message.error(error.message || '获取文档内容失败')
      setEditContent('')
    } finally {
      setContentLoading(false)
    }
  }

  const handleSaveEdit = async () => {
    if (!currentDoc) return
    setSaving(true)
    try {
      await updateKbDocumentContent(currentDoc.id, {
        content: editContent,
        rebuild_index: rebuildAfterSave,
      })
      message.success('文档内容已更新')
      setEditModalOpen(false)
      fetchDocuments(pagination.current, pagination.pageSize)
    } catch (error: any) {
      message.error(error.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const columns = [
    { title: '文档名称', dataIndex: 'name', key: 'name', ellipsis: true },
    { title: '来源', dataIndex: 'source', key: 'source', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <span style={{ color: status === 'indexed' ? '#52c41a' : '#faad14' }}>
          {status === 'indexed' ? '已索引' : status === 'pending' ? '待处理' : status}
        </span>
      ),
    },
    { title: '切片数', dataIndex: 'chunk_count', key: 'chunk_count', width: 100 },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180,
      render: (val: string) => val ? dayjs(val).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: unknown, record: KbDocument) => (
        <Space size="small">
          <Button type="link" icon={<EyeOutlined />} size="small" onClick={() => handleView(record)}>
            查看
          </Button>
          <Button type="link" icon={<EditOutlined />} size="small" onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除?"
            description="删除后将无法恢复"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button type="link" danger icon={<DeleteOutlined />} size="small">
              删除
            </Button>
          </Popconfirm>
        </Space>
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
              handleUpload(file)
              return false
            }}
          >
            <Button icon={<UploadOutlined />} loading={uploading}>
              添加规范文档
            </Button>
          </Upload>
          <Button
            icon={<ReloadOutlined />}
            onClick={handleRebuild}
            loading={rebuilding}
          >
            重建索引
          </Button>
          <Button
            onClick={() => fetchDocuments(pagination.current, pagination.pageSize)}
            loading={loading}
          >
            刷新
          </Button>
        </Space>
      </Card>

      <Table
        columns={columns}
        dataSource={documents}
        rowKey="id"
        loading={loading}
        pagination={{
          current: pagination.current,
          pageSize: pagination.pageSize,
          total: pagination.total,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (page, pageSize) => {
            fetchDocuments(page, pageSize || 10)
          },
        }}
      />

      {/* 查看文档 Modal */}
      <Modal
        title={`查看文档 - ${currentDoc?.name || ''}`}
        open={viewModalOpen}
        onCancel={() => { setViewModalOpen(false); setDocContent('') }}
        footer={[
          <Button key="close" onClick={() => { setViewModalOpen(false); setDocContent('') }}>
            关闭
          </Button>,
        ]}
        width={800}
      >
        {contentLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>加载中...</div>
        ) : (
          <Input.TextArea
            value={docContent}
            readOnly
            autoSize={{ minRows: 10, maxRows: 30 }}
            style={{ fontFamily: 'monospace', fontSize: 13 }}
          />
        )}
      </Modal>

      {/* 编辑文档 Modal */}
      <Modal
        title={`编辑文档 - ${currentDoc?.name || ''}`}
        open={editModalOpen}
        onCancel={() => { setEditModalOpen(false); setEditContent('') }}
        onOk={handleSaveEdit}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        width={800}
      >
        {contentLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>加载中...</div>
        ) : (
          <>
            <Input.TextArea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              autoSize={{ minRows: 12, maxRows: 30 }}
              style={{ fontFamily: 'monospace', fontSize: 13 }}
            />
            <div style={{ marginTop: 12 }}>
              <Checkbox
                checked={rebuildAfterSave}
                onChange={(e) => setRebuildAfterSave(e.target.checked)}
              >
                保存后重建索引（内容变更后需要重建索引才能生效）
              </Checkbox>
            </div>
          </>
        )}
      </Modal>
    </div>
  )
}

export default KbPage
