import React, { useEffect, useState, useMemo } from 'react';
import {
  Table,
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  Popconfirm,
  Typography,
  message,
  Card,
  Tooltip,
} from 'antd';
import {
  PlusOutlined,
  CreditCardOutlined,
  EditOutlined,
  StopOutlined,
  CheckCircleOutlined,
  ReloadOutlined,
  DeleteOutlined,
  SplitCellsOutlined,
} from '@ant-design/icons';
import { accountsApi } from '../api';
import { BankAccount, AccountCard } from '../types';
import { getBankShort, isMultiAccountBank, isSingleAccountBank, formatBankHolderTails, getCustomDisplayName, cleanAccountAlias } from '../utils/bankDisplay';

const { Text } = Typography;



/**
 * Represents a display row: either a single account (multi-account bank)
 * or a merged group of accounts (single-account-per-holder bank).
 */
interface DisplayRow {
  /** Unique key for table */
  key: string;
  /** Bank short name */
  bankShort: string;
  /** Bank full name */
  bankFull: string;
  /** Card holder name */
  holder: string;
  /** Whether this is a merged row (multiple accounts under one holder at one bank) */
  merged: boolean;
  /** The account(s) behind this row */
  accounts: BankAccount[];
  /** All cards across all accounts in this row */
  allCards: AccountCard[];
  /** Primary display text: "银行缩写 持卡人 尾号" */
  displayTitle: string;
  /** Status of the first/primary account */
  status: string;
  /** Created at of earliest account */
  created_at: string;
}

export const Accounts: React.FC = () => {
  const [loading, setLoading] = useState<boolean>(false);
  const [accounts, setAccounts] = useState<BankAccount[]>([]);

  // Account Modal
  const [accountModalOpen, setAccountModalOpen] = useState<boolean>(false);
  const [editingAccount, setEditingAccount] = useState<BankAccount | null>(null);
  const [accountForm] = Form.useForm();
  const [accountSaving, setAccountSaving] = useState<boolean>(false);

  // Card Add Modal
  const [cardModalOpen, setCardModalOpen] = useState<boolean>(false);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [cardForm] = Form.useForm();
  const [cardSaving, setCardSaving] = useState<boolean>(false);

  // Card Edit Modal
  const [cardEditModalOpen, setCardEditModalOpen] = useState<boolean>(false);
  const [editingCard, setEditingCard] = useState<AccountCard | null>(null);
  const [cardEditForm] = Form.useForm();
  const [cardEditSaving, setCardEditSaving] = useState<boolean>(false);

  const fetchAccounts = async () => {
    try {
      setLoading(true);
      const res = await accountsApi.listAccounts();
      const list = Array.isArray(res.data) ? res.data : (res.data?.accounts || []);
      setAccounts(list);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '获取银行账户列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
  }, []);

  // ---- Build display rows ----
  const displayRows = useMemo<DisplayRow[]>(() => {
    // Group accounts by (bankShort, holder)
    const groups = new Map<string, BankAccount[]>();
    for (const acct of accounts) {
      const bank = acct.bank || acct.bank_name || '';
      const holder = (acct.holder || '').trim();
      const bankShort = getBankShort(bank);
      const key = `${bankShort}||${holder}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(acct);
    }

    const rows: DisplayRow[] = [];
    for (const [, group] of groups) {
      const bank = group[0].bank || group[0].bank_name || '';
      const holder = group[0].holder || '';
      const bankShort = getBankShort(bank);

      // Decide merge strategy based on bank type:
      // - Multi-account banks: always show each account separately
      // - Single-account banks: always merge into one row
      // - Unknown banks: merge if only 1 account, separate if >1
      const shouldMerge = isSingleAccountBank(bankShort)
        ? true
        : isMultiAccountBank(bankShort)
          ? false
          : group.length === 1;

      if (shouldMerge) {
        // Merge all accounts for this bank+holder into one row
        const allCards: AccountCard[] = [];
        for (const acct of group) {
          for (const card of (acct.cards || [])) {
            allCards.push(card);
          }
        }
        const tailParts = allCards.map(c => c.tail || c.card_last4 || '').filter(Boolean);
        const title = formatBankHolderTails(bankShort, holder, tailParts);

        rows.push({
          key: group.map(a => a.id).join('__'),
          bankShort,
          bankFull: bank,
          holder,
          merged: group.length > 1,
          accounts: group,
          allCards,
          displayTitle: title || group[0].alias || bank,
          status: group[0].status,
          created_at: group.reduce((earliest, a) =>
            a.created_at < earliest ? a.created_at : earliest, group[0].created_at),
        });
      } else {
        // Multi-account bank: show each card as its own row.
        // If an account has multiple cards, each card becomes a separate row
        // so the user sees e.g. "广发 牛鋆辉 2090" and "广发 牛鋆辉 9759".
        for (const acct of group) {
          const cards = acct.cards || [];
          if (cards.length <= 1) {
            // 0 or 1 card — one row for this account
            const tail = cards.length === 1 ? (cards[0].tail || cards[0].card_last4 || '') : '';
            const title = formatBankHolderTails(bankShort, holder, tail);
            rows.push({
              key: acct.id,
              bankShort,
              bankFull: acct.bank || bank,
              holder,
              merged: false,
              accounts: [acct],
              allCards: cards,
              displayTitle: title || acct.alias || bank,
              status: acct.status,
              created_at: acct.created_at,
            });
          } else {
            // Multiple cards — one row per card
            for (const card of cards) {
              const tail = card.tail || card.card_last4 || '';
              const title = formatBankHolderTails(bankShort, holder, tail);
              rows.push({
                key: `${acct.id}__${card.id}`,
                bankShort,
                bankFull: acct.bank || bank,
                holder,
                merged: false,
                accounts: [acct],
                allCards: [card],
                displayTitle: title || acct.alias || bank,
                status: acct.status,
                created_at: acct.created_at,
              });
            }
          }
        }
      }
    }

    return rows;
  }, [accounts]);

  // Account Form Handlers
  const openCreateAccount = () => {
    setEditingAccount(null);
    accountForm.resetFields();
    accountForm.setFieldsValue({
      status: 'active',
    });
    setAccountModalOpen(true);
  };

  const openEditAccount = (record: BankAccount) => {
    setEditingAccount(record);
    accountForm.resetFields();
    accountForm.setFieldsValue({
      bank: record.bank || record.bank_name,
      alias: record.alias || record.account_name,
      holder: record.holder || '',
      reference: record.reference,
      status: record.status || 'active',
    });
    setAccountModalOpen(true);
  };

  const handleSaveAccount = async () => {
    try {
      const values = await accountForm.validateFields();
      setAccountSaving(true);

      if (editingAccount) {
        await accountsApi.updateAccount(editingAccount.id, {
          bank: values.bank?.trim(),
          alias: values.alias?.trim() || null,
          holder: values.holder?.trim() || null,
          reference: values.reference?.trim() || null,
          status: values.status || editingAccount.status || 'active',
          expected_revision: editingAccount.revision,
        });
        message.success('账户修改成功');
      } else {
        await accountsApi.createAccount({
          bank: values.bank.trim(),
          alias: values.alias?.trim() || null,
          holder: values.holder?.trim() || null,
          reference: values.reference?.trim() || null,
        });
        message.success('账户新建成功');
      }
      setAccountModalOpen(false);
      fetchAccounts();
    } catch (err: any) {
      if (err?.response?.data?.detail) {
        message.error(err.response.data.detail);
      }
    } finally {
      setAccountSaving(false);
    }
  };

  const handleToggleAccountStatus = async (record: BankAccount, nextStatus: 'active' | 'archived') => {
    try {
      await accountsApi.updateAccount(record.id, {
        alias: record.alias,
        status: nextStatus,
        expected_revision: record.revision,
      });
      message.success(nextStatus === 'archived' ? '账户已归档' : '账户已恢复');
      fetchAccounts();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '修改账户状态失败');
    }
  };

  const handleDeleteAccount = async (record: BankAccount) => {
    try {
      await accountsApi.deleteAccount(record.id);
      message.success('账户已彻底删除');
      fetchAccounts();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '删除账户失败');
    }
  };

  const handleDeleteCard = async (card: AccountCard) => {
    try {
      await accountsApi.deleteCard(card.id);
      message.success(`卡片「尾号 ${card.tail || card.card_last4}」已彻底删除`);
      fetchAccounts();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '删除卡片失败');
    }
  };

  const handleSplitCard = async (card: AccountCard) => {
    try {
      const res = await accountsApi.splitCard(card.id);
      message.success(res.data?.message || `卡片尾号 ${card.tail || card.card_last4} 已拆分到新账户`);
      fetchAccounts();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '拆分卡片失败');
    }
  };

  // Card Add Handlers
  const openAddCard = (accountId: string) => {
    setSelectedAccountId(accountId);
    cardForm.resetFields();
    setCardModalOpen(true);
  };

  const handleSaveCard = async () => {
    try {
      const values = await cardForm.validateFields();
      setCardSaving(true);
      await accountsApi.createCard({
        account_id: selectedAccountId,
        tail: values.tail.trim(),
        display_name: values.display_name?.trim() || null,
      });
      message.success('信用卡绑定成功');
      setCardModalOpen(false);
      fetchAccounts();
    } catch (err: any) {
      if (err?.response?.data?.detail) {
        message.error(err.response.data.detail);
      }
    } finally {
      setCardSaving(false);
    }
  };

  // Card Edit Handlers
  const openEditCard = (card: AccountCard) => {
    setEditingCard(card);
    cardEditForm.resetFields();
    cardEditForm.setFieldsValue({
      tail: card.tail || card.card_last4,
      display_name: card.display_name || card.card_alias,
      status: card.status || (card.is_active ? 'active' : 'archived'),
    });
    setCardEditModalOpen(true);
  };

  const handleSaveEditCard = async () => {
    if (!editingCard) return;
    try {
      const values = await cardEditForm.validateFields();
      setCardEditSaving(true);
      await accountsApi.updateCard(editingCard.id, {
        tail: values.tail?.trim(),
        display_name: values.display_name?.trim() || null,
        status: values.status,
        expected_revision: editingCard.revision,
      });
      message.success('卡片信息已更新');
      setCardEditModalOpen(false);
      fetchAccounts();
    } catch (err: any) {
      if (err?.response?.data?.detail) {
        message.error(err.response.data.detail);
      }
    } finally {
      setCardEditSaving(false);
    }
  };

  const handleToggleCardStatus = async (card: AccountCard, nextStatus: 'active' | 'archived') => {
    try {
      await accountsApi.updateCard(card.id, {
        display_name: card.display_name,
        status: nextStatus,
        expected_revision: card.revision,
      });
      message.success(nextStatus === 'archived' ? '卡片已停用' : '卡片已启用');
      fetchAccounts();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '修改卡片状态失败');
    }
  };

  // Expanded Cards Table
  const expandedRowRender = (row: DisplayRow) => {
    // For merged rows, show cards from ALL accounts
    const allAccounts = row.accounts;
    const cards = row.allCards;
    const cardColumns = [
      {
        title: '卡号尾号',
        key: 'tail',
        render: (_: any, card: AccountCard) => (
          <Tag color="cyan" style={{ fontWeight: 'bold' }}>
            尾号 {card.tail || card.card_last4}
          </Tag>
        ),
      },
      {
        title: '卡片名称 / 备注',
        key: 'display_name',
        render: (_: any, card: AccountCard) => (
          <Text strong>{getCustomDisplayName(card.display_name || card.card_alias, row.bankFull, card.tail || card.card_last4) || '信用卡'}</Text>
        ),
      },
      ...(row.merged ? [{
        title: '所属账户',
        key: 'account_alias',
        render: (_: any, card: AccountCard) => {
          const parentAcct = allAccounts.find(a => a.id === card.account_id);
          return <Text type="secondary">{parentAcct?.alias || parentAcct?.reference || '-'}</Text>;
        },
      }] : []),
      {
        title: '状态',
        key: 'status',
        render: (_: any, card: AccountCard) => {
          const isActive = card.status === 'active' || card.is_active;
          return isActive ? <Tag color="success">正常</Tag> : <Tag color="default">已停用</Tag>;
        },
      },
      {
        title: '绑定时间',
        dataIndex: 'created_at',
        key: 'created_at',
        render: (t: string) => (t ? new Date(t).toLocaleString('zh-CN') : '-'),
      },
      {
        title: '操作',
        key: 'action',
        render: (_: any, card: AccountCard) => {
          const isActive = card.status === 'active' || card.is_active;
          return (
            <Space>
              <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEditCard(card)}>
                编辑
              </Button>
              {isActive ? (
                <Popconfirm
                  title="确定停用该卡片吗？停用后仍保留历史账单"
                  onConfirm={() => handleToggleCardStatus(card, 'archived')}
                >
                  <Button type="link" size="small" icon={<StopOutlined />}>
                    停用
                  </Button>
                </Popconfirm>
              ) : (
                <Popconfirm
                  title="确定重新启用该卡片吗？"
                  onConfirm={() => handleToggleCardStatus(card, 'active')}
                >
                  <Button type="link" size="small" style={{ color: '#52c41a' }} icon={<CheckCircleOutlined />}>
                    启用
                  </Button>
                </Popconfirm>
              )}
              {(() => {
                const parentAcct = allAccounts.find(a => a.id === card.account_id);
                const canSplit = parentAcct && (parentAcct.cards?.length || 0) > 1;
                if (!canSplit) return null;
                return (
                  <Popconfirm
                    title="确定将此卡片拆分为独立账户吗？"
                    description="拆分后该卡将拥有独立的账户和账单。"
                    onConfirm={() => handleSplitCard(card)}
                    okText="拆分"
                    cancelText="取消"
                  >
                    <Button type="link" size="small" icon={<SplitCellsOutlined />}>
                      拆分
                    </Button>
                  </Popconfirm>
                );
              })()}
              <Popconfirm
                title="确定删除此信用卡吗？"
                description="彻底删除后不可恢复。"
                onConfirm={() => handleDeleteCard(card)}
                okText="删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
              >
                <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                  删除
                </Button>
              </Popconfirm>
            </Space>
          );
        },
      },
    ];

    return (
      <div style={{ margin: '8px 0 16px 36px', background: '#fafafa', padding: 14, borderRadius: 8, border: '1px solid #f0f0f0' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <Space>
            <CreditCardOutlined style={{ color: '#1677ff' }} />
            <Text strong style={{ fontSize: 13 }}>
              名下绑定的信用卡（共 {cards.length} 张）
            </Text>
          </Space>
          {!row.merged ? (
            <Button
              size="small"
              type="dashed"
              icon={<PlusOutlined />}
              onClick={() => openAddCard(row.accounts[0].id)}
            >
              绑定新卡片
            </Button>
          ) : (
            <Space>
              {allAccounts.map(a => (
                <Button
                  key={a.id}
                  size="small"
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={() => openAddCard(a.id)}
                >
                  绑定到 {a.alias || a.reference || '账户'}
                </Button>
              ))}
            </Space>
          )}
        </div>
        <Table
          columns={cardColumns}
          dataSource={cards}
          rowKey="id"
          pagination={false}
          size="small"
          locale={{ emptyText: '该银行账户下暂无绑定卡片，点击上方「绑定新卡片」添加' }}
        />
      </div>
    );
  };

  const accountColumns = [
    {
      title: '银行 / 持卡人 / 卡号',
      key: 'name',
      render: (_: any, row: DisplayRow) => {
        const acct = row.accounts[0];
        return (
          <Space direction="vertical" size={2}>
            <Text strong style={{ fontSize: 16 }}>
              {row.displayTitle}
            </Text>
            <Space size={8}>
              <Tag color="blue">{row.bankShort}</Tag>
              {row.merged ? (
                <Tag color="orange" style={{ fontSize: 11 }}>
                  {row.accounts.length} 个账户合并
                </Tag>
              ) : null}
              {(() => {
                const cleaned = cleanAccountAlias(acct.alias, row.bankFull, row.holder);
                return cleaned ? (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {cleaned}
                  </Text>
                ) : null;
              })()}
              {acct.reference ? (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  参考编号: {acct.reference}
                </Text>
              ) : null}
            </Space>
          </Space>
        );
      },
    },
    {
      title: '名下卡片',
      key: 'cards_count',
      render: (_: any, row: DisplayRow) => {
        const count = row.allCards.length;
        return (
          <Tag color="geekblue" icon={<CreditCardOutlined />}>
            {count} 张信用卡
          </Tag>
        );
      },
    },
    {
      title: '账户状态',
      key: 'status',
      render: (_: any, row: DisplayRow) =>
        row.status === 'active' ? <Tag color="success">正常</Tag> : <Tag color="default">已归档</Tag>,
    },
    {
      title: '创建时间',
      key: 'created_at',
      render: (_: any, row: DisplayRow) =>
        row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, row: DisplayRow) => {
        const r = row.accounts[0];
        return (
          <Space>
            <Button size="small" icon={<EditOutlined />} onClick={() => openEditAccount(r)}>
              编辑
            </Button>
            <Button size="small" icon={<PlusOutlined />} onClick={() => openAddCard(r.id)}>
              加卡
            </Button>
            {r.status === 'active' ? (
              <Popconfirm
                title="确定归档此账户吗？归档后不会参与新邮件匹配，但保留历史账单。"
                onConfirm={() => handleToggleAccountStatus(r, 'archived')}
              >
                <Button size="small">
                  归档
                </Button>
              </Popconfirm>
            ) : (
              <Popconfirm
                title="确定恢复此归档账户吗？"
                onConfirm={() => handleToggleAccountStatus(r, 'active')}
              >
                <Button size="small" style={{ color: '#52c41a' }}>
                  恢复
                </Button>
              </Popconfirm>
            )}
            <Popconfirm
              title="确定彻底删除此银行账户吗？"
              description={
                (r.cards?.length || 0) > 0
                  ? `将连同名下 ${r.cards?.length} 张信用卡一并彻底删除。若已有正式账单将无法删除。`
                  : '彻底删除后不可恢复。若已有正式账单将无法删除。'
              }
              onConfirm={() => handleDeleteAccount(r)}
              okText="彻底删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button size="small" danger icon={<DeleteOutlined />}>
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
            <CreditCardOutlined />
            <span>银行账户与卡片管理</span>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={fetchAccounts} loading={loading}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateAccount}>
              新建账户
            </Button>
          </Space>
        }
      >
        <Table
          dataSource={displayRows}
          columns={accountColumns}
          rowKey="key"
          loading={loading}
          expandable={{ expandedRowRender }}
          pagination={{ pageSize: 15, showTotal: (total) => `共 ${total} 个银行账户` }}
        />
      </Card>

      {/* Account Modal (Create / Edit) */}
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
            name="bank"
            label="发卡银行名称"
            rules={[{ required: true, message: '请输入发卡行名称，如：招商银行、中国银行、中信银行' }]}
          >
            <Input placeholder="发卡行名称，如：招商银行" />
          </Form.Item>

          <Form.Item
            name="holder"
            label="持卡人姓名"
            tooltip="持卡人真实姓名，用于在列表中醒目显示"
          >
            <Input placeholder="如：牛鋆辉、杨小宾" />
          </Form.Item>

          <Form.Item
            name="alias"
            label="账户别名 / 账本名称"
            tooltip="自定义展示名称，如：中信银行信用卡 (张三)、招行经典白信用卡账户"
          >
            <Input placeholder="如：中信银行信用卡 (牛鋆辉)" />
          </Form.Item>

          <Form.Item
            name="reference"
            label="银行参考标识 (可选)"
            tooltip="银行账单邮件中的账号识别编号或自定义英文编码"
          >
            <Input placeholder="如：CITIC_001 或 CMB_CLASSIC" />
          </Form.Item>

          {editingAccount ? (
            <Form.Item name="status" label="账户状态" rules={[{ required: true }]}>
              <Select>
                <Select.Option value="active">正常 (active)</Select.Option>
                <Select.Option value="archived">已归档 (archived)</Select.Option>
              </Select>
            </Form.Item>
          ) : null}
        </Form>
      </Modal>

      {/* Card Modal (Add) */}
      <Modal
        title="绑定新信用卡"
        open={cardModalOpen}
        onOk={handleSaveCard}
        onCancel={() => setCardModalOpen(false)}
        confirmLoading={cardSaving}
        destroyOnClose
      >
        <Form form={cardForm} layout="vertical">
          <Form.Item
            name="tail"
            label="卡号后四位 (尾号)"
            rules={[
              { required: true, message: '请输入4位数字尾号' },
              { pattern: /^\d{4}$/, message: '必须为精确4位数字' },
            ]}
          >
            <Input maxLength={4} placeholder="如：8821" />
          </Form.Item>

          <Form.Item name="display_name" label="卡片名称 / 备注 (可选)">
            <Input placeholder="如：金穗白金信用卡主卡、工资快捷卡" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Card Modal (Edit) */}
      <Modal
        title="编辑信用卡信息"
        open={cardEditModalOpen}
        onOk={handleSaveEditCard}
        onCancel={() => setCardEditModalOpen(false)}
        confirmLoading={cardEditSaving}
        destroyOnClose
      >
        <Form form={cardEditForm} layout="vertical">
          <Form.Item
            name="tail"
            label="卡号后四位 (尾号)"
            rules={[
              { required: true, message: '请输入4位数字尾号' },
              { pattern: /^\d{4}$/, message: '必须为精确4位数字' },
            ]}
          >
            <Input maxLength={4} placeholder="如：8821" />
          </Form.Item>

          <Form.Item name="display_name" label="卡片名称 / 备注">
            <Input placeholder="如：金穗白金信用卡主卡" />
          </Form.Item>

          <Form.Item name="status" label="卡片状态" rules={[{ required: true }]}>
            <Select>
              <Select.Option value="active">正常</Select.Option>
              <Select.Option value="archived">已停用</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};
