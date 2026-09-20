import React, { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  InputNumber,
  Switch,
  Select,
  Typography,
  message,
  Card,
  Popconfirm,
  Radio,
  Divider,
  Alert,
} from 'antd';
import {
  SettingOutlined,
  PlusOutlined,
  CheckCircleOutlined,
  SyncOutlined,
  SafetyCertificateOutlined,
  PlayCircleOutlined,
  StopOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckOutlined,
} from '@ant-design/icons';
import { mailboxApi, jobsApi } from '../api';
import { MailboxItem } from '../types';

const { Text, Paragraph } = Typography;

export const MailboxConfig: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [mailboxes, setMailboxes] = useState<MailboxItem[]>([]);
  const [modalVisible, setModalVisible] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [editingMailbox, setEditingMailbox] = useState<MailboxItem | null>(null);
  const [form] = Form.useForm();
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);

  const fetchMailboxes = async () => {
    setLoading(true);
    try {
      const res = await mailboxApi.listMailboxes();
      setMailboxes(res.data || []);
    } catch (_) {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMailboxes();
  }, []);

  const openAddModal = () => {
    setEditingMailbox(null);
    form.resetFields();
    // Default to Sina preset
    applyPreset('sina');
    setModalVisible(true);
  };

  const openEditModal = (mb: MailboxItem) => {
    setEditingMailbox(mb);
    form.setFieldsValue({
      preset: 'custom',
      name: mb.name || '',
      email_address: mb.email_address,
      username: mb.username || '',
      imap_host: mb.imap_host,
      imap_port: mb.imap_port,
      use_ssl: mb.use_ssl,
      auth_token: '',
      folder: mb.folder || 'INBOX',
      check_interval_minutes: mb.check_interval_minutes || 30,
      since_days: mb.since_days || 90,
      max_messages: mb.max_messages || 100,
      max_attachment_mb: mb.max_attachment_mb || 10,
    });
    setModalVisible(true);
  };

  const applyPreset = (preset: 'sina' | 'custom') => {
    if (preset === 'sina') {
      form.setFieldsValue({
        preset: 'sina',
        name: '新浪邮箱',
        imap_host: 'imap.sina.com',
        imap_port: 993,
        use_ssl: true,
        folder: 'INBOX',
        check_interval_minutes: 30,
        since_days: 90,
        max_messages: 100,
        max_attachment_mb: 10,
      });
    } else {
      form.setFieldsValue({
        preset: 'custom',
        imap_port: 993,
        use_ssl: true,
        folder: 'INBOX',
        check_interval_minutes: 30,
        since_days: 90,
        max_messages: 100,
        max_attachment_mb: 10,
      });
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setModalLoading(true);

      const payload: any = {
        name: values.name,
        email_address: values.email_address,
        username: values.username || '',
        imap_host: values.imap_host,
        imap_port: values.imap_port,
        use_ssl: values.use_ssl,
        folder: values.folder || 'INBOX',
        check_interval_minutes: values.check_interval_minutes,
        since_days: values.since_days,
        max_messages: values.max_messages,
        max_attachment_mb: values.max_attachment_mb,
      };

      if (values.auth_token) {
        payload.auth_token = values.auth_token;
      }

      if (editingMailbox) {
        payload.expected_revision = editingMailbox.revision;
        await mailboxApi.updateMailbox(editingMailbox.id, payload);
        message.success('邮箱配置已保存。如修改了主机或密码，请重新测试连接');
      } else {
        await mailboxApi.createMailbox(payload);
        message.success('邮箱配置创建成功，请先测试连接再启用');
      }

      setModalVisible(false);
      fetchMailboxes();
    } catch (_) {
    } finally {
      setModalLoading(false);
    }
  };

  const handleTest = async (mb: MailboxItem) => {
    setActionLoadingId(mb.id);
    try {
      await mailboxApi.testMailbox(mb.id, mb.revision);
      message.success('IMAP 只读连接测试成功！');
      fetchMailboxes();
    } catch (_) {
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleEnable = async (mb: MailboxItem) => {
    setActionLoadingId(mb.id);
    try {
      await mailboxApi.enableMailbox(mb.id, mb.revision);
      message.success('邮箱已成功启用并生效');
      fetchMailboxes();
    } catch (_) {
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleDisable = async (mb: MailboxItem) => {
    setActionLoadingId(mb.id);
    try {
      await mailboxApi.disableMailbox(mb.id, mb.revision);
      message.success('邮箱已停用');
      fetchMailboxes();
    } catch (_) {
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleSyncNow = async (mb: MailboxItem) => {
    setActionLoadingId(mb.id);
    try {
      await jobsApi.createJob({
        kind: 'sync',
        target_id: mb.id,
      });
      message.success('已加入收件同步队列，后台正在拉取最新账单邮件');
    } catch (_) {
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleDelete = async (mb: MailboxItem) => {
    setActionLoadingId(mb.id);
    try {
      await mailboxApi.deleteMailbox(mb.id);
      message.success(`邮箱【${mb.name || mb.email_address}】配置已成功删除`);
      fetchMailboxes();
    } catch (err: any) {
      const msg = err.response?.data?.detail || '删除失败，请重试';
      message.error(msg);
    } finally {
      setActionLoadingId(null);
    }
  };

  const columns = [
    {
      title: '配置名称 / 邮箱地址',
      key: 'name',
      render: (_: any, mb: MailboxItem) => (
        <div>
          <Text strong>{mb.name || '未命名邮箱'}</Text>
          <div>
            <Text copyable style={{ fontSize: 13, color: '#595959' }}>
              {mb.email_address}
            </Text>
          </div>
        </div>
      ),
    },
    {
      title: 'IMAP 服务端',
      key: 'server',
      render: (_: any, mb: MailboxItem) => (
        <div>
          <Text code>
            {mb.imap_host}:{mb.imap_port}
          </Text>
          {mb.use_ssl && <Tag color="blue" style={{ marginLeft: 6 }}>SSL</Tag>}
        </div>
      ),
    },
    {
      title: '拉取间隔',
      dataIndex: 'check_interval_minutes',
      key: 'interval',
      width: 110,
      render: (min: number) => `${min} 分钟`,
    },
    {
      title: '启用状态',
      key: 'status',
      width: 120,
      render: (_: any, mb: MailboxItem) => {
        if (mb.is_active) return <Tag color="success">已启用运行</Tag>;
        return <Tag color="default">已停用</Tag>;
      },
    },
    {
      title: '连接测试状态',
      key: 'tested',
      width: 140,
      render: (_: any, mb: MailboxItem) => {
        const isTested = mb.tested_revision === mb.revision;
        if (isTested) {
          return <Tag color="green"><CheckCircleOutlined /> 已验证通过</Tag>;
        }
        return <Tag color="orange">未通过测试</Tag>;
      },
    },
    {
      title: '最近拉取时间',
      dataIndex: 'last_checked_at',
      key: 'last_checked_at',
      width: 170,
      render: (t: string | null) => (t ? new Date(t).toLocaleString() : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 380,
      render: (_: any, mb: MailboxItem) => {
        const loadingThis = actionLoadingId === mb.id;
        const isTested = mb.tested_revision === mb.revision;
        return (
          <Space size="small" wrap>
            <Button size="small" icon={<EditOutlined />} onClick={() => openEditModal(mb)}>
              编辑
            </Button>
            <Button
              size="small"
              icon={<SafetyCertificateOutlined />}
              onClick={() => handleTest(mb)}
              loading={loadingThis}
            >
              测试连接
            </Button>
            {mb.has_pending ? (
              <Button
                size="small"
                type="primary"
                icon={<CheckOutlined />}
                disabled={!isTested}
                onClick={() => handleEnable(mb)}
                loading={loadingThis}
              >
                应用生效
              </Button>
            ) : mb.is_active ? (
              <Popconfirm
                title="确定停用该邮箱吗？"
                description="停用后定时任务将不再自动拉取该邮箱的邮件"
                onConfirm={() => handleDisable(mb)}
              >
                <Button size="small" danger icon={<StopOutlined />} loading={loadingThis}>
                  停用
                </Button>
              </Popconfirm>
            ) : (
              <Button
                size="small"
                type="primary"
                icon={<PlayCircleOutlined />}
                disabled={!isTested}
                onClick={() => handleEnable(mb)}
                loading={loadingThis}
              >
                启用
              </Button>
            )}
            {mb.is_active && (
              <Button
                size="small"
                icon={<SyncOutlined />}
                onClick={() => handleSyncNow(mb)}
                loading={loadingThis}
              >
                立即同步
              </Button>
            )}
            <Popconfirm
              title="确定删除此邮箱配置吗？"
              description="删除后相关的拉取历史记录将一并清理，此操作不可撤销。"
              okText="确认删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              onConfirm={() => handleDelete(mb)}
            >
              <Button size="small" danger icon={<DeleteOutlined />} loading={loadingThis}>
                删除
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      <Card
        title={
          <Space>
            <SettingOutlined />
            <span>邮箱与授权码配置</span>
          </Space>
        }
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openAddModal}>
            添加邮箱配置
          </Button>
        }
      >
        <Alert
          type="info"
          showIcon
          message="安全说明"
          description="CardCue 采用严格只读 IMAP 连接协议拉取账单邮件。授权码与密码经服务端对称加密脱敏存储，绝对不回传前端明文。修改主机或授权码后须先通过连接测试方可启用。"
          style={{ marginBottom: 16 }}
        />
        <Table
          rowKey="id"
          columns={columns}
          dataSource={mailboxes}
          loading={loading}
          pagination={false}
        />
      </Card>

      {/* 添加/编辑邮箱弹窗 */}
      <Modal
        title={editingMailbox ? '编辑邮箱配置' : '添加邮箱配置'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        confirmLoading={modalLoading}
        width={650}
        okText={editingMailbox ? '保存修改' : '确认创建'}
        cancelText="取消"
      >
        <Form form={form} layout="vertical" initialValues={{ use_ssl: true }}>
          {!editingMailbox && (
            <Form.Item name="preset" label="快捷预设服务商">
              <Radio.Group onChange={(e) => applyPreset(e.target.value)}>
                <Radio.Button value="sina">新浪邮箱 (Sina Mail)</Radio.Button>
                <Radio.Button value="custom">通用 IMAP 协议</Radio.Button>
              </Radio.Group>
            </Form.Item>
          )}

          <Form.Item
            name="name"
            label="配置别名"
            rules={[{ required: true, message: '请输入配置别名' }]}
          >
            <Input placeholder="例如: 个人新浪账单主邮箱" />
          </Form.Item>

          <Form.Item
            name="email_address"
            label="邮箱地址"
            rules={[
              { required: true, message: '请输入邮箱地址' },
              { type: 'email', message: '请输入合法有效的邮箱格式' },
            ]}
            extra={editingMailbox ? '邮箱地址已绑定历史拉取游标，如需更换邮箱请新建配置或删除后重建' : undefined}
          >
            <Input placeholder="username@sina.com" disabled={!!editingMailbox} />
          </Form.Item>

          <Form.Item
            name="username"
            label="IMAP 登录账号 (留空默认等同于邮箱地址)"
            extra={editingMailbox ? '登录账号与邮箱绑定，不可在此修改' : undefined}
          >
            <Input placeholder="留空默认使用邮箱地址" disabled={!!editingMailbox} />
          </Form.Item>

          <Form.Item
            name="auth_token"
            label={editingMailbox ? '授权码 / 密码 (留空则保留原授权码不变)' : '邮箱授权码 (必填)'}
            rules={editingMailbox ? [] : [{ required: true, message: '首次配置必须输入授权码' }]}
          >
            <Input.Password
              placeholder={editingMailbox ? '留空保持原授权码不变' : '请输入邮箱开启 POP3/IMAP 后生成的授权码'}
            />
          </Form.Item>

          <Divider orientation="left" style={{ margin: '16px 0' }}>
            IMAP 网络与抓取参数
          </Divider>

          <Space style={{ display: 'flex', width: '100%' }} size="large">
            <Form.Item
              name="imap_host"
              label="IMAP 主机地址"
              rules={[{ required: true, message: '请输入 IMAP 主机' }]}
              style={{ flex: 2 }}
            >
              <Input placeholder="imap.sina.com" disabled={!!editingMailbox} />
            </Form.Item>
            <Form.Item
              name="imap_port"
              label="端口"
              rules={[{ required: true, message: '请输入端口' }]}
              style={{ flex: 1 }}
            >
              <InputNumber style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="use_ssl" label="SSL 加密" valuePropName="checked" style={{ flex: 1 }}>
              <Switch checkedChildren="开" unCheckedChildren="关" />
            </Form.Item>
          </Space>

          <Space style={{ display: 'flex', width: '100%' }} size="large">
            <Form.Item
              name="check_interval_minutes"
              label="自动拉取间隔 (分钟)"
              rules={[{ required: true }]}
              style={{ flex: 1 }}
            >
              <InputNumber min={5} max={1440} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="since_days" label="初次同步最近天数" style={{ flex: 1 }}>
              <InputNumber min={1} max={3650} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="folder" label="邮箱文件夹" style={{ flex: 1 }}>
              <Input placeholder="INBOX" disabled={!!editingMailbox} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
};
