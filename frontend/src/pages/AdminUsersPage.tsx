import React, { useState, useEffect, useCallback } from 'react'
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  Tag,
  Badge,
  Space,
  Popconfirm,
  message,
} from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { listUsers, createUser, updateUser, deleteUser } from '../services/api'

interface UserItem {
  id: string
  username: string
  role: string
  is_active: boolean
  created_at: string
}

const AdminUsersPage: React.FC = () => {
  const [users, setUsers] = useState<UserItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<UserItem | null>(null)
  const [createSaving, setCreateSaving] = useState(false)
  const [editSaving, setEditSaving] = useState(false)

  const [createForm] = Form.useForm()
  const [editForm] = Form.useForm()

  const fetchUsers = useCallback(async (p: number = page) => {
    setLoading(true)
    try {
      const res = await listUsers({ page: p, page_size: 20 })
      const data = res.data.data
      setUsers(data.items || [])
      setTotal(data.total || 0)
    } catch (error: any) {
      message.error(error.message || '获取用户列表失败')
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    fetchUsers()
  }, [])

  const handlePageChange = (p: number) => {
    setPage(p)
    fetchUsers(p)
  }

  // 创建
  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields()
      setCreateSaving(true)
      await createUser(values)
      message.success('用户创建成功')
      setCreateOpen(false)
      createForm.resetFields()
      fetchUsers()
    } catch (error: any) {
      if (error.errorFields) return // 校验失败
      message.error(error.message || '创建失败')
    } finally {
      setCreateSaving(false)
    }
  }

  // 编辑
  const openEdit = (user: UserItem) => {
    setEditingUser(user)
    editForm.setFieldsValue({ role: user.role, password: undefined })
    setEditOpen(true)
  }

  const handleEdit = async () => {
    try {
      const values = await editForm.validateFields()
      setEditSaving(true)
      const payload: any = {}
      if (values.role !== editingUser?.role) payload.role = values.role
      if (values.password) payload.password = values.password
      if (Object.keys(payload).length === 0) {
        message.info('无变更')
        setEditOpen(false)
        return
      }
      await updateUser(editingUser!.id, payload)
      message.success('用户更新成功')
      setEditOpen(false)
      fetchUsers()
    } catch (error: any) {
      if (error.errorFields) return
      message.error(error.message || '更新失败')
    } finally {
      setEditSaving(false)
    }
  }

  // 删除
  const handleDelete = async (userId: string) => {
    try {
      await deleteUser(userId)
      message.success('用户已删除')
      fetchUsers()
    } catch (error: any) {
      message.error(error.message || '删除失败')
    }
  }

  // 启用/禁用
  const handleToggleActive = async (user: UserItem) => {
    try {
      await updateUser(user.id, { is_active: !user.is_active })
      message.success(`${user.username} 已${user.is_active ? '禁用' : '启用'}`)
      fetchUsers()
    } catch (error: any) {
      message.error(error.message || '操作失败')
    }
  }

  const columns = [
    {
      title: '用户 ID',
      dataIndex: 'id',
      key: 'id',
      width: 100,
      render: (id: string) => (
        <span style={{ fontFamily: 'monospace', fontSize: 12 }}>
          {id.slice(0, 8)}...
        </span>
      ),
    },
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
      width: 140,
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      width: 80,
      render: (role: string) => (
        <Tag color={role === 'admin' ? 'red' : 'blue'}>{role}</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      render: (active: boolean, record: UserItem) => (
        <Space>
          <Badge status={active ? 'success' : 'error'} text={active ? '启用' : '禁用'} />
          <Switch
            size="small"
            checked={active}
            onChange={() => handleToggleActive(record)}
          />
        </Space>
      ),
    },
    {
      title: '注册时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (d: string) => d ? new Date(d).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_: unknown, record: UserItem) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定删除此用户？"
            description="删除将级联清理该用户的所有任务、对话、模板数据"
            onConfirm={() => handleDelete(record.id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <h2>用户管理</h2>
      <Card
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => fetchUsers()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              创建用户
            </Button>
          </Space>
        }
      >
        <Table
          dataSource={users}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize: 20,
            total,
            onChange: handlePageChange,
            showSizeChanger: false,
            showTotal: (t) => `共 ${t} 个用户`,
          }}
          size="middle"
        />
      </Card>

      {/* 创建用户弹窗 */}
      <Modal
        title="创建用户"
        open={createOpen}
        onCancel={() => { setCreateOpen(false); createForm.resetFields() }}
        onOk={handleCreate}
        confirmLoading={createSaving}
        okText="创建"
        cancelText="取消"
      >
        <Form form={createForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            label="用户名"
            name="username"
            rules={[
              { required: true, message: '请输入用户名' },
              { pattern: /^[a-zA-Z0-9_]+$/, message: '仅支持字母、数字、下划线' },
              { min: 3, max: 20, message: '3-20 个字符' },
            ]}
          >
            <Input placeholder="3-20位字母数字下划线" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 8, max: 64, message: '8-64 个字符' },
            ]}
          >
            <Input.Password placeholder="至少8位" />
          </Form.Item>
          <Form.Item
            label="角色"
            name="role"
            initialValue="user"
            rules={[{ required: true }]}
          >
            <Select>
              <Select.Option value="user">普通用户 (user)</Select.Option>
              <Select.Option value="admin">管理员 (admin)</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑用户弹窗 */}
      <Modal
        title={`编辑用户 ${editingUser?.username || ''}`}
        open={editOpen}
        onCancel={() => { setEditOpen(false); editForm.resetFields() }}
        onOk={handleEdit}
        confirmLoading={editSaving}
        okText="保存"
        cancelText="取消"
      >
        <Form form={editForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            label="角色"
            name="role"
            rules={[{ required: true }]}
          >
            <Select>
              <Select.Option value="user">普通用户 (user)</Select.Option>
              <Select.Option value="admin">管理员 (admin)</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item
            label="新密码（留空不修改）"
            name="password"
            rules={[
              { min: 8, max: 64, message: '8-64 个字符', warningOnly: true },
            ]}
          >
            <Input.Password placeholder="留空则不修改密码" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default AdminUsersPage
