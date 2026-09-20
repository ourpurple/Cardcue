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
  Select,
  Popconfirm,
  Typography,
  message,
  Card,
} from 'antd';
import { PlusOutlined, CreditCardOutlined, EditOutlined, StopOutlined } from '@ant-design/icons';
import { accountsApi } from '../api';
import { CurrencyAmount, centsToYuanString, yuanStringToCents } from '../components/CurrencyAmount';

const { Text } = Typography;

export const Accounts: React.FC = () => {
  const [loading, setLoading] = useState<boolean>(false);
  const [accounts, setAccounts] = useState<any[]>([]);

  // Account Modal
  const [accountModalOpen, setAccountModalOpen] = useState<boolean>(false);
  const [editingAccount, setEditingAccount] = useState<any>(null);
  const [accountForm] = Form.useForm();
  const [accountSaving, setAccountSaving] = useState<boolean>(false);

  // Card Modal
  const [cardModalOpen, setCardModalOpen] = useState<boolean>(false);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [cardForm] = Form.useForm();
  const [cardSaving, setCardSaving] = useState<boolean>(false);

  const fetchAccounts = async () => {
    try {
      setLoading(true);
      const res = await accountsApi.listAccounts();
      setAccounts(res.data?.accounts || []);
    } catch (_) {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
  }, []);

  // Account Form Handlers
  const openCreateAccount = () => {
    setEditingAccount(null);
    accountForm.resetFields();
    accountForm.setFieldsValue({
      currency: 'CNY',
      statement_day: 1,
      payment_due_day_offset: 20,
    });
    setAccountModalOpen(true);
  };

  const openEditAccount = (record: any) => {
    setEditingAccount(record);
    accountForm.resetFields();
    accountForm.setFieldsValue({
      bank_name: record.bank_name,
      account_name: record.account_name,
      currency: record.currency,
      credit_limit_yuan: centsToYuanString(record.credit_limit_cents),
      statement_day: record.statement_day,
      payment_due_day_offset: record.payment_due_day_offset,
    });
    setAccountModalOpen(true);
  };

  const handleSaveAccount = async () => {
    try {
      const values = await accountForm.validateFields();
      setAccountSaving(true);
      const payload = {
        bank_name: values.bank_name.trim(),
        account_name: values.account_name.trim(),
        currency: values.currency,
        credit_limit_cents: yuanStringToCents(values.credit_limit_yuan),
        statement_day: values.statement_day,
        payment_due_day_offset: values.payment_due_day_offset,
      };

      if (editingAccount) {
        await accountsApi.updateAccount(editingAccount.id, {
          ...payload,
          expected_revision: editingAccount.revision,
        });
        message.success('账户修改成功');
      } else {
        await accountsApi.createAccount(payload);
        message.success('账户创建成功');
      }
      setAccountModalOpen(false);
      fetchAccounts();
    } catch (_) {
    } finally {
      setAccountSaving(false);
    }
  };

  const handleArchiveAccount = async (record: any) => {
    try {
      await accountsApi.updateAccount(record.id, {
        status: 'archived',
        expected_revision: record.revision,
      });
      message.success('账户已归档');
      fetchAccounts();
    } catch (_) {}
  };

  // Card Form Handlers
  const openAddCard = (accountId: string) => {
    setSelectedAccountId(accountId);
    cardForm.resetFields();
    cardForm.setFieldsValue({ card_type: 'credit' });
    setCardModalOpen(true);
  };

  const handleSaveCard = async () => {
    try {
      const values = await cardForm.validateFields();
      setCardSaving(true);
      await accountsApi.createCard({
        account_id: selectedAccountId,
        card_last4: values.card_last4.trim(),
        card_alias: values.card_alias?.trim() || '',
        card_type: values.card_type,
      });
      message.success('卡片添加成功');
      setCardModalOpen(false);
      fetchAccounts();
    } catch (_) {
    } finally {
      setCardSaving(false);
    }
  };

  const handleArchiveCard = async (card: any) => {
    try {
      await accountsApi.updateCard(card.id, {
        is_active: false,
        expected_revision: card.revision,
      });
      message.success('卡片已停用');
      fetchAccounts();
    } catch (_) {}
  };

  // Expanded Cards Table
  const expandedRowRender = (accountRecord: any) => {
    const cards = accountRecord.cards || [];
    const cardColumns = [
      {
        title: '卡号尾号',
        dataIndex: 'card_last4',
        key: 'card_last4',
        render: (text: string) => <Tag color="blue">尾号 {text}</Tag>,
      },
      {
        title: '卡片别名 / 备注',
        dataIndex: 'card_alias',
        key: 'card_alias',
        render: (text: string) => text || '-',
      },
      {
        title: '类型',
        dataIndex: 'card_type',
        key: 'card_type',
        render: (type: string) => (type === 'credit' ? '信用卡' : '借记卡'),
      },
      {
        title: '状态',
        dataIndex: 'is_active',
        key: 'is_active',
        render: (active: boolean) =>
          active ? <Tag color="success">正常</Tag> : <Tag color="default">已停用</Tag>,
      },
      {
        title: '操作',
        key: 'action',
        render: (_: any, card: any) => (
          card.is_active ? (
            <Popconfirm
              title="确定停用该卡片吗？停用后仍保留历史账单"
              onConfirm={() => handleArchiveCard(card)}
            >
              <Button type="link" size="small" danger icon={<StopOutlined />}>
                停用
              </Button>
            </Popconfirm>
          ) : null
        ),
      },
    ];

    return (
      <div style={{ margin: '8px 0 16px 36px', background: '#fafafa', padding: 12, borderRadius: 6 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
          <Text strong style={{ fontSize: 13 }}>
            名下卡片列表（共 {cards.length} 张）
          </Text>
          <Button
            size="small"
            type="dashed"
            icon={<PlusOutlined />}
            onClick={() => openAddCard(accountRecord.id)}
          >
            添加卡片
          </Button>
        </div>
        <Table
          columns={cardColumns}
          dataSource={cards}
          rowKey="id"
          pagination={false}
          size="small"
          locale={{ emptyText: '该账户下暂无绑定卡片，点击上方添加' }}
        />
      </div>
    );
  };

  const accountColumns = [
    {
      title: '账户名称 / 发卡行',
      key: 'name',
      render: (_: any, r: any) => (
        <Space direction="vertical" size={0}>
          <Text strong>{r.account_name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{r.bank_name}</Text>
        </Space>
      ),
    },
    {
      title: '币种',
      dataIndex: 'currency',
      key: 'currency',
      render: (c: string) => <Tag color="geekblue">{c}</Tag>,
    },
    {
      title: '信用额度',
      key: 'limit',
      render: (_: any, r: any) => (
        <CurrencyAmount cents={r.credit_limit_cents} currency={r.currency} />
      ),
    },
    {
      title: '账单日 / 还款日',
      key: 'days',
      render: (_: any, r: any) => (
        <span>
          每月 {r.statement_day} 日 / 账单后 {r.payment_due_day_offset} 天
        </span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => (s === 'active' ? <Tag color="success">正常</Tag> : <Tag>已归档</Tag>),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, r: any) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditAccount(r)}>
            编辑
          </Button>
          <Button size="small" icon={<PlusOutlined />} onClick={() => openAddCard(r.id)}>
            加卡
          </Button>
          {r.status === 'active' && (
            <Popconfirm
              title="确定归档此账户吗？归档不会删除关联的历史账单"
              onConfirm={() => handleArchiveAccount(r)}
            >
              <Button size="small" danger>
                归档
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card
        title={
          <Space>
            <CreditCardOutlined />
            <span>银行账户与卡片管理</span>
          </Space>
        }
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateAccount}>
            新建账户
          </Button>
        }
      >
        <Table
          dataSource={accounts}
          columns={accountColumns}
          rowKey="id"
          loading={loading}
          expandable={{ expandedRowRender }}
          pagination={{ pageSize: 15 }}
        />
      </Card>

      {/* Account Modal */}
      <Modal
        title={editingAccount ? '编辑银行账户' : '新建银行账户'}
        open={accountModalOpen}
        onOk={handleSaveAccount}
        onCancel={() => setAccountModalOpen(false)}
        confirmLoading={accountSaving}
        destroyOnClose
      >
        <Form form={accountForm} layout="vertical">
          <Form.Item
            name="bank_name"
            label="发卡行名称"
            rules={[{ required: true, message: '请输入发卡行名称，如：招商银行、工商银行' }]}
          >
            <Input placeholder="发卡行名称，如：招商银行" />
          </Form.Item>

          <Form.Item
            name="account_name"
            label="账户名称 / 账本标识"
            rules={[{ required: true, message: '请输入账户名称' }]}
          >
            <Input placeholder="如：招行经典白信用卡账户" />
          </Form.Item>

          <Form.Item
            name="currency"
            label="币种"
            rules={[{ required: true, message: '请选择币种' }]}
          >
            <Select>
              <Select.Option value="CNY">CNY 人民币</Select.Option>
              <Select.Option value="USD">USD 美元</Select.Option>
              <Select.Option value="EUR">EUR 欧元</Select.Option>
              <Select.Option value="HKD">HKD 港币</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="credit_limit_yuan"
            label="信用额度（元）"
            rules={[{ required: true, message: '请输入信用额度' }]}
          >
            <Input placeholder="如：50000.00" />
          </Form.Item>

          <Space style={{ display: 'flex', width: '100%' }}>
            <Form.Item
              name="statement_day"
              label="每月固定账单日"
              rules={[{ required: true, message: '请输入账单日' }]}
            >
              <InputNumber min={1} max={31} style={{ width: 180 }} />
            </Form.Item>

            <Form.Item
              name="payment_due_day_offset"
              label="还款日相对账单日天数"
              rules={[{ required: true, message: '请输入偏移天数' }]}
            >
              <InputNumber min={1} max={60} style={{ width: 180 }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      {/* Card Modal */}
      <Modal
        title="绑定新卡片"
        open={cardModalOpen}
        onOk={handleSaveCard}
        onCancel={() => setCardModalOpen(false)}
        confirmLoading={cardSaving}
        destroyOnClose
      >
        <Form form={cardForm} layout="vertical">
          <Form.Item
            name="card_last4"
            label="卡号后四位"
            rules={[
              { required: true, message: '请输入4位数字' },
              { pattern: /^\d{4}$/, message: '必须为精确4位数字' },
            ]}
          >
            <Input maxLength={4} placeholder="如：8821" />
          </Form.Item>

          <Form.Item name="card_alias" label="卡片别名 / 备注">
            <Input placeholder="如：工资卡快捷支付、黑金主卡" />
          </Form.Item>

          <Form.Item name="card_type" label="卡片类型">
            <Select>
              <Select.Option value="credit">信用卡</Select.Option>
              <Select.Option value="debit">借记卡</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};
