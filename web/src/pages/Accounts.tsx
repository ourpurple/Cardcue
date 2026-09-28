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
import { BankAccount, AccountCard, HistoricalOwnershipPreview, HistoricalOwnershipPreflightResult } from '../types';
import { getBankShort, formatBankHolderTails, getCustomDisplayName, cleanAccountAlias } from '../utils/bankDisplay';

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

  const [historyPreview, setHistoryPreview] = useState<HistoricalOwnershipPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [ownershipMapping, setOwnershipMapping] = useState<Record<string, { accountId?: string; cardId?: string }>>({});
  const [preflightResult, setPreflightResult] = useState<HistoricalOwnershipPreflightResult | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(false);

  const runHistoryPreflight = async () => {
    if (!historyPreview) return;
    if (historyPreview.statements.some(stmt => !accounts.some(a => a.id === ownershipMapping[stmt.id]?.accountId))) {
      message.warning('请为每份账单选择有效目标账户；保留原归属也需要选择');
      return;
    }
    setPreflightLoading(true);
    try {
      const response = await accountsApi.preflightHistory(historyPreview.account.id, {
        expected_account_revision: historyPreview.account.revision,
        decisions: historyPreview.statements.map(stmt => {
          const choice = ownershipMapping[stmt.id];
          const target = accounts.find(a => a.id === choice.accountId)!;
          return {
            statement_id: stmt.id,
            expected_current_version_id: stmt.current_version_id,
            target_account_id: target.id,
            target_account_revision: target.revision,
            target_card_id: choice.cardId || null,
          };
        }),
      });
      setPreflightResult(response.data);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '映射预检失败，请刷新预览');
      setPreflightResult(null);
    } finally {
      setPreflightLoading(false);
    }
  };

  const openHistoryPreview = async (accountId: string) => {
    setOwnershipMapping({});
    setPreflightResult(null);
    setPreviewLoading(true);
    try {
      const response = await accountsApi.previewHistory(accountId);
      setHistoryPreview(response.data);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '读取历史归属预览失败');
    } finally {
      setPreviewLoading(false);
    }
  };
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

  // One row represents exactly one repayment account. Same bank and holder
  // do not prove that two historical accounts can be merged safely.
  const displayRows = useMemo<DisplayRow[]>(() => accounts.map((acct) => {
    const bank = acct.bank || acct.bank_name || '';
    const bankShort = getBankShort(bank);
    const holder = acct.holder || '';
    const cards = acct.cards || [];
    const tails = cards.map(c => c.tail || c.card_last4 || '').filter(Boolean);
    return {
      key: acct.id,
      bankShort,
      bankFull: bank,
      holder,
      merged: false,
      accounts: [acct],
      allCards: cards,
      displayTitle: formatBankHolderTails(bankShort, holder, tails) || acct.alias || bank,
      status: acct.status,
      created_at: acct.created_at,
    };
  }), [accounts]);

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
              <Tag color={acct.billing_mode === 'per_card' ? 'purple' : acct.billing_mode === 'consolidated' ? 'green' : 'orange'}>
                {acct.billing_mode === 'per_card' ? '独立还款' : acct.billing_mode === 'consolidated' ? '合并还款' : '归属待确认'}
              </Tag>
              {acct.billing_mode === 'per_card' && row.allCards.length > 1 && <Tag color="red">多卡历史异常，需核对</Tag>}
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
            <Button size="small" loading={previewLoading} onClick={() => openHistoryPreview(r.id)}>
              历史归属预览
            </Button>            <Button size="small" icon={<EditOutlined />} onClick={() => openEditAccount(r)}>
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

      <Modal
        title="历史归属预览（只读）"
        open={historyPreview !== null}
        onCancel={() => setHistoryPreview(null)}
        footer={<Space><Button onClick={() => setHistoryPreview(null)}>关闭</Button><Button type="primary" loading={preflightLoading} onClick={runHistoryPreflight} disabled={!historyPreview?.statements.length}>检验映射（不执行）</Button></Space>}
        width={800}
      >
        {historyPreview && <Space direction="vertical" style={{ width: '100%' }}>
          <Text strong>{historyPreview.account.bank} · {historyPreview.account.alias || historyPreview.account.holder || '未命名账户'}</Text>
          <Text>账户 ID：{historyPreview.account.id}；修订号：{historyPreview.account.revision}</Text>
          <Text>现行模式：{historyPreview.account.billing_mode === 'per_card' ? '独立还款' : historyPreview.account.billing_mode === 'consolidated' ? '合并还款' : '待确认'}；银行默认仅供参考：{historyPreview.account.bank_default_mode_hint === 'per_card' ? '独立还款' : historyPreview.account.bank_default_mode_hint === 'consolidated' ? '合并还款' : '未知'}</Text>
          <Text>卡片 {historyPreview.counts.cards} · 账单 {historyPreview.counts.statements} · 版本 {historyPreview.counts.versions} · 还款记录 {historyPreview.counts.payments} · 已确认明细 {historyPreview.counts.confirmed_transactions} · 关联草稿 {historyPreview.counts.linked_drafts}</Text>
          {historyPreview.cards.map(card => <Text key={card.id}>卡片 {card.tail}（{card.status}）· ID {card.id} · 修订 {card.revision}</Text>)}
          {historyPreview.peer_account_ids.length > 0 && <Text type="warning">同银行同持卡人的其他底层账户：{historyPreview.peer_account_ids.join('、')}（不自动合并）</Text>}
          {historyPreview.risks.map((risk, index) => <Text type="warning" key={index}>⚠ {risk}</Text>)}
          <Table
            size="small"
            rowKey="id"
            pagination={{ pageSize: 10 }}
            dataSource={historyPreview.statements}
            columns={[
              { title: '原账单 / 日期', render: (_: unknown, s: HistoricalOwnershipPreview['statements'][number]) => <Space direction="vertical"><Text>{s.statement_date} · {s.currency}</Text><Text copyable>{s.id}</Text></Space> },
              { title: '现归属账户', dataIndex: 'account_id', render: (id: string) => <Text copyable>{id}</Text> },
              { title: '关联记录', render: (_: unknown, s: HistoricalOwnershipPreview['statements'][number]) => `版本 ${s.version_count} / 还款 ${s.payment_count}（有效 ${s.active_payment_count}）/ 明细 ${s.confirmed_transaction_count}` },
              { title: '卡尾线索', render: (_: unknown, s: HistoricalOwnershipPreview['statements'][number]) => s.observed_card_tails.join('、') || '无' },
              { title: '拟调整归属', render: (_: unknown, s: HistoricalOwnershipPreview['statements'][number]) => <Space direction="vertical">
                <Select
                  placeholder="选择目标账户（可选原账户）"
                  style={{ width: 230 }}
                  value={ownershipMapping[s.id]?.accountId}
                  options={accounts.map(a => ({ value: a.id, disabled: a.status !== 'active', label: `${a.bank} · ${a.alias || a.holder || '未命名'} · ${a.id.slice(0, 8)}` }))}
                  onChange={accountId => {
                    setOwnershipMapping(current => ({ ...current, [s.id]: { accountId } }));
                    setPreflightResult(null);
                  }}
                />
                {(() => {
                  const target = accounts.find(a => a.id === ownershipMapping[s.id]?.accountId);
                  return target?.billing_mode === 'per_card' ? <Select
                    placeholder="明确指定卡片 ID"
                    style={{ width: 230 }}
                    value={ownershipMapping[s.id]?.cardId}
                    options={(target.cards || []).filter(card => card.status === 'active').map(card => ({ value: card.id, label: `尾号 ${card.tail || card.card_last4} · ${card.id.slice(0, 8)}` }))}
                    onChange={cardId => {
                      setOwnershipMapping(current => ({ ...current, [s.id]: { accountId: target.id, cardId } }));
                      setPreflightResult(null);
                    }}
                  /> : null;
                })()}
                {s.risks.map((risk, index) => <Text type="warning" key={index}>{risk}</Text>)}
              </Space> },
            ]}
          />
          {preflightResult && <Space direction="vertical">
            <Text type={preflightResult.valid_mapping ? 'success' : 'danger'}>
              {preflightResult.valid_mapping ? '映射预检通过（不是迁移批准）' : '映射存在冲突，不能执行'}
            </Text>
            {preflightResult.issues.map((issue, index) => <Text type="danger" key={index}>{issue}</Text>)}
            <Text type="secondary">{preflightResult.notice}</Text>
          </Space>}
          <Text type="secondary">{historyPreview.next_step}。此页面不会拆分、合并或修改账单。</Text>
        </Space>}
      </Modal>
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
