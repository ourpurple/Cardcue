import React, { useEffect, useState } from 'react';
import type { TableProps } from 'antd';
import {
  Table,
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  Typography,
  message,
  Card,
  Drawer,
  Timeline,
  Popconfirm,
  Row,
  Col,
  Statistic,
  Divider,
} from 'antd';
import {
  FileTextOutlined,
  DollarOutlined,
  HistoryOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  EditOutlined,
  RollbackOutlined,
} from '@ant-design/icons';
import { statementsApi, accountsApi, draftsApi } from '../api';
import { CurrencyAmount, centsToYuanString, yuanStringToCents } from '../components/CurrencyAmount';
import { StatementListItem, StatementDetailData, BankAccount, StatementDraftItem, StatementDraftDetail, TransactionDetail } from '../types';
import { getBankShort, formatBankHolderTails, cleanAccountAlias } from '../utils/bankDisplay';

const { Text, Title, Paragraph } = Typography;

function generateUUID(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export const Statements: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<StatementListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [statusFilter, setStatusFilter] = useState<'all' | 'unpaid' | 'paid'>('all');
  const [accountFilter, setAccountFilter] = useState<string | undefined>(undefined);
  const [currencyFilter, setCurrencyFilter] = useState<string | undefined>(undefined);
  const [sortField, setSortField] = useState<'due_date' | 'statement_date'>('due_date');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  const [accounts, setAccounts] = useState<BankAccount[]>([]);

  // Drawer detail state
  const [detailVisible, setDetailVisible] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [currentDetail, setCurrentDetail] = useState<StatementDetailData | null>(null);

  // Detail-only completion never changes a statement version or a payment.
  const [completionVisible, setCompletionVisible] = useState(false);
  const [completionLoading, setCompletionLoading] = useState(false);
  const [candidateDrafts, setCandidateDrafts] = useState<StatementDraftItem[]>([]);
  const [manualDraftId, setManualDraftId] = useState('');
  const [completionDraft, setCompletionDraft] = useState<StatementDraftDetail | null>(null);
  const [selectedDetailRows, setSelectedDetailRows] = useState<string[]>([]);
  const [expectedDetailCount, setExpectedDetailCount] = useState('');
  const [replaceDetails, setReplaceDetails] = useState(false);
  const [markDetailsComplete, setMarkDetailsComplete] = useState(false);
  const [historyVisible, setHistoryVisible] = useState(false);
  const [historyRows, setHistoryRows] = useState<TransactionDetail[]>([]);
  const [historyTitle, setHistoryTitle] = useState('');
  const [historyLoading, setHistoryLoading] = useState(false);
  // Correct modal state
  const [correctModalVisible, setCorrectModalVisible] = useState(false);
  const [correctLoading, setCorrectLoading] = useState(false);
  const [correctTarget, setCorrectTarget] = useState<StatementListItem | StatementDetailData | null>(null);
  const [correctForm] = Form.useForm();

  // Payment modal state
  const [paymentModalVisible, setPaymentModalVisible] = useState(false);
  const [paymentLoading, setPaymentLoading] = useState(false);
  const [paymentTarget, setPaymentTarget] = useState<StatementListItem | StatementDetailData | null>(null);
  const [paymentForm] = Form.useForm();

  // Revoke payment state
  const [revokeModalVisible, setRevokeModalVisible] = useState(false);
  const [revokeLoading, setRevokeLoading] = useState(false);
  const [revokePaymentId, setRevokePaymentId] = useState<string | null>(null);
  const [revokeReason, setRevokeReason] = useState('');

  const fetchAccounts = async () => {
    try {
      const res = await accountsApi.listAccounts();
      setAccounts(res.data || []);
    } catch (_) {}
  };

  const fetchStatements = async () => {
    setLoading(true);
    try {
      const params: any = {
        page,
        size: pageSize,
        status: statusFilter,
        sort_by: sortField,
        sort_order: sortOrder,
      };
      if (accountFilter) params.account_id = accountFilter;
      if (currencyFilter) params.currency = currencyFilter;

      const res = await statementsApi.listStatements(params);
      setData(res.data?.items || []);
      setTotal(res.data?.total || 0);
    } catch (_) {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
  }, []);

  useEffect(() => {
    fetchStatements();
  }, [page, pageSize, statusFilter, accountFilter, currencyFilter, sortField, sortOrder]);

  const loadDetail = async (id: string) => {
    setDetailLoading(true);
    setDetailVisible(true);
    try {
      const res = await statementsApi.getStatement(id);
      setCurrentDetail(res.data);
    } catch (_) {
      setDetailVisible(false);
    } finally {
      setDetailLoading(false);
    }
  };

  const openCompletion = async () => {
    if (!currentDetail) return;
    setCompletionVisible(true);
    setCompletionDraft(null);
    setManualDraftId('');
    setCandidateDrafts([]);
    setSelectedDetailRows([]);
    setExpectedDetailCount('');
    setReplaceDetails(false);
    setMarkDetailsComplete(false);
    setCompletionLoading(true);
    try {
      const response = await draftsApi.listDrafts({ page: 1, size: 100, status: 'pending_review' });
      const candidates: StatementDraftItem[] = response.data?.items || [];
      setCandidateDrafts(candidates.filter(d =>
        d.currency === currentDetail.currency && d.statement_date === currentDetail.statement_date &&
        d.bank != null && getBankShort(d.bank) === getBankShort(currentDetail.bank) &&
        (d.matched_account_id == null || d.matched_account_id === currentDetail.account_id) &&
        (d.amount_minor == null || d.amount_minor === currentDetail.amount_minor)));
      if (response.data?.total > 100) message.info('候选仅展示最近 100 条草稿；更早草稿可在下方输入草稿 ID 核对');
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '无法加载待审核草稿');
    } finally {
      setCompletionLoading(false);
    }
  };

  const selectCompletionDraft = async (draftId: string) => {
    setCompletionDraft(null);
    setSelectedDetailRows([]);
    setMarkDetailsComplete(false);
    setCompletionLoading(true);
    try {
      const response = await draftsApi.getDraft(draftId);
      const draft: StatementDraftDetail = response.data;
      if (draft.status !== 'pending_review') {
        message.error('草稿已经处理，请刷新');
        return;
      }
      if (!currentDetail || getBankShort(draft.bank || '') !== getBankShort(currentDetail.bank) ||
          (draft.matched_account_id && draft.matched_account_id !== currentDetail.account_id) ||
          draft.currency !== currentDetail.currency || draft.statement_date !== currentDetail.statement_date ||
          draft.due_date !== currentDetail.due_date || draft.amount_minor !== currentDetail.amount_minor ||
          draft.card_tails.some(tail => !currentDetail.card_tails?.includes(tail))) {
        message.error('草稿与当前账单的账户、卡片或汇总不一致，不能仅补明细');
        return;
      }
      setCompletionDraft(draft);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '草稿加载失败');
    } finally {
      setCompletionLoading(false);
    }
  };

  const submitCompletion = async () => {
    if (!currentDetail?.current_version_id || !completionDraft || !selectedDetailRows.length) {
      message.error('请先选择草稿并勾选已核对的交易');
      return;
    }
    const countText = expectedDetailCount.trim();
    if (countText && (!/^\d+$/.test(countText) || Number(countText) < 1 || Number(countText) > 10000)) {
      message.error('来源预期笔数须为 1～10000 的整数');
      return;
    }
    const totalRows = selectedDetailRows.length + (replaceDetails ? 0 : currentDetail.transactions.length);
    const expectedCount = countText ? Number(countText) : null;
    if (expectedCount !== null && expectedCount < totalRows) {
      message.error('预期笔数不能少于已确认交易笔数');
      return;
    }
    if (markDetailsComplete && (!replaceDetails || selectedDetailRows.length !== completionDraft.transactions.length ||
        expectedCount !== selectedDetailRows.length || !completionDraft.source_manifest?.entries?.length ||
        completionDraft.source_manifest.has_unsupported || completionDraft.source_manifest.entries.some(
          entry => entry.truncated || entry.notes === 'file_adapter_required' || entry.notes === 'unsupported_type'))) {
      message.error('完整明细须全量替换，并核对所有来源、交易和预期笔数');
      return;
    }
    setCompletionLoading(true);
    try {
      await statementsApi.completeDetails(currentDetail.id, {
        request_id: generateUUID(),
        expected_version_id: currentDetail.current_version_id,
        expected_detail_revision: currentDetail.detail_revision ?? 0,
        draft_id: completionDraft.id,
        expected_draft_revision: completionDraft.revision,
        confirm_transaction_ids: selectedDetailRows,
        replace_existing: replaceDetails,
        details_complete: markDetailsComplete,
        expected_transaction_count: expectedCount,
      });
      message.success('明细已保存为新的独立快照，账单金额与还款未改变');
      setCompletionVisible(false);
      await loadDetail(currentDetail.id);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '明细保存失败，请刷新版本后重试');
    } finally {
      setCompletionLoading(false);
    }
  };

  const showDetailHistory = async (setId: string, revision: number) => {
    if (!currentDetail) return;
    setHistoryLoading(true);
    try {
      const response = await statementsApi.getDetailSet(currentDetail.id, setId);
      setHistoryRows(response.data?.transactions || []);
      setHistoryTitle(`明细快照 #${revision}（只读）`);
      setHistoryVisible(true);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '历史明细加载失败');
    } finally {
      setHistoryLoading(false);
    }
  };
  const openCorrectModal = (record: StatementListItem | StatementDetailData) => {
    setCorrectTarget(record);
    correctForm.setFieldsValue({
      amount_yuan: (record.amount_minor / 100).toFixed(2),
      minimum_yuan: record.minimum_minor != null ? (record.minimum_minor / 100).toFixed(2) : '',
      reason: '',
    });
    setCorrectModalVisible(true);
  };

  const handleCorrectSubmit = async () => {
    if (!correctTarget || !correctTarget.current_version_id) return;
    try {
      const values = await correctForm.validateFields();
      const amountMinor = yuanStringToCents(values.amount_yuan);
      const minMinor = values.minimum_yuan ? yuanStringToCents(values.minimum_yuan) : null;

      if (amountMinor < correctTarget.total_paid_minor) {
        message.error(`更正金额(${values.amount_yuan}元)不能低于已有效还款总额(${centsToYuanString(correctTarget.total_paid_minor)}元)`);
        return;
      }

      setCorrectLoading(true);
      await statementsApi.correctStatement(correctTarget.id, {
        expected_version_id: correctTarget.current_version_id,
        request_id: generateUUID(),
        amount_minor: amountMinor,
        minimum_minor: minMinor,
        reason: values.reason,
      });

      message.success('账单更正版本创建成功');
      setCorrectModalVisible(false);
      fetchStatements();
      if (currentDetail && currentDetail.id === correctTarget.id) {
        loadDetail(currentDetail.id);
      }
    } catch (_) {
    } finally {
      setCorrectLoading(false);
    }
  };

  const openPaymentModal = (record: StatementListItem | StatementDetailData) => {
    setPaymentTarget(record);
    paymentForm.setFieldsValue({
      amount_yuan: (record.remaining_minor / 100).toFixed(2),
      note: '',
    });
    setPaymentModalVisible(true);
  };

  const handlePaymentSubmit = async () => {
    if (!paymentTarget) return;
    try {
      const values = await paymentForm.validateFields();
      const amountMinor = yuanStringToCents(values.amount_yuan);

      if (amountMinor <= 0) {
        message.error('还款金额必须大于 0');
        return;
      }
      if (amountMinor > paymentTarget.remaining_minor) {
        message.error(`还款金额不可超过剩余应还金额(${centsToYuanString(paymentTarget.remaining_minor)}元)`);
        return;
      }

      setPaymentLoading(true);
      await statementsApi.recordPayment(paymentTarget.id, {
        statement_id: paymentTarget.id,
        amount_minor: amountMinor,
        currency: paymentTarget.currency,
        note: values.note || undefined,
        request_id: generateUUID(),
      });

      message.success('还款记录成功');
      setPaymentModalVisible(false);
      fetchStatements();
      if (currentDetail && currentDetail.id === paymentTarget.id) {
        loadDetail(currentDetail.id);
      }
    } catch (_) {
    } finally {
      setPaymentLoading(false);
    }
  };

  const handleRevokePayment = async () => {
    if (!revokePaymentId || !revokeReason.trim()) {
      message.error('请输入撤销原因');
      return;
    }
    setRevokeLoading(true);
    try {
      await statementsApi.revokePayment(revokePaymentId, revokeReason.trim());
      message.success('还款记录已撤销');
      setRevokeModalVisible(false);
      setRevokeReason('');
      setRevokePaymentId(null);
      fetchStatements();
      if (currentDetail) {
        loadDetail(currentDetail.id);
      }
    } catch (_) {
    } finally {
      setRevokeLoading(false);
    }
  };

  const handleDeleteStatement = async (id: string) => {
    try {
      await statementsApi.deleteStatement(id);
      message.success('账单已成功删除');
      fetchStatements();
      if (currentDetail && currentDetail.id === id) {
        setDetailVisible(false);
        setCurrentDetail(null);
      }
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '删除账单失败');
    }
  };

  const handleDeletePayment = async (paymentId: string) => {
    try {
      await statementsApi.deletePayment(paymentId);
      message.success('还款记录已成功删除');
      fetchStatements();
      if (currentDetail) {
        loadDetail(currentDetail.id);
      }
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '删除还款记录失败');
    }
  };

  const handleTableChange = (newPagination: any, _filters: any, sorter: any) => {
    if (newPagination.pageSize && newPagination.pageSize !== pageSize) {
      setPageSize(newPagination.pageSize);
      setPage(1);
    } else if (newPagination.current && newPagination.current !== page) {
      setPage(newPagination.current);
    }

    if (!Array.isArray(sorter) && sorter && (sorter.field || sorter.columnKey)) {
      const field = (sorter.field || sorter.columnKey) as 'due_date' | 'statement_date';
      if (field === 'due_date' || field === 'statement_date') {
        if (sorter.order) {
          const order = sorter.order === 'descend' ? 'desc' : 'asc';
          if (field !== sortField || order !== sortOrder) {
            setSortField(field);
            setSortOrder(order);
            setPage(1);
          }
        } else {
          if (sortField !== 'due_date' || sortOrder !== 'asc') {
            setSortField('due_date');
            setSortOrder('asc');
            setPage(1);
          }
        }
      }
    }
  };

  const columns: TableProps<StatementListItem>['columns'] = [
    {
      title: '银行与账户',
      key: 'bank',
      render: (_: any, record: StatementListItem) => {
        const bankShort = getBankShort(record.bank);
        const title = formatBankHolderTails(record.bank, record.holder, record.card_tails);
        return (
          <Space direction="vertical" size={2}>
            <Text strong style={{ fontSize: 16 }}>{title || record.bank}</Text>
            <Space size={8} style={{ marginTop: 2 }}>
              <Tag color="blue">{bankShort}</Tag>
              {(() => {
                const cleaned = cleanAccountAlias(record.account_alias, record.bank, record.holder);
                return cleaned ? (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {cleaned}
                  </Text>
                ) : null;
              })()}
            </Space>
          </Space>
        );
      },
    },
    {
      title: '账单日',
      dataIndex: 'statement_date',
      key: 'statement_date',
      width: 130,
      sorter: true,
      sortOrder: sortField === 'statement_date' ? (sortOrder === 'asc' ? 'ascend' as const : 'descend' as const) : null,
    },
    {
      title: '到期还款日',
      dataIndex: 'due_date',
      key: 'due_date',
      width: 140,
      sorter: true,
      sortOrder: sortField === 'due_date' ? (sortOrder === 'asc' ? 'ascend' as const : 'descend' as const) : null,
      render: (date: string, record: StatementListItem) => {
        const isOverdue = !record.is_paid && new Date(date).getTime() < new Date().setHours(0, 0, 0, 0);
        return (
          <Text type={isOverdue ? 'danger' : undefined} strong={isOverdue}>
            {date}
            {isOverdue && ' (已逾期)'}
          </Text>
        );
      },
    },
    {
      title: '本期应还',
      key: 'amount_minor',
      render: (_: any, record: StatementListItem) => (
        <div>
          <CurrencyAmount cents={record.amount_minor} currency={record.currency} style={{ fontWeight: 600 }} />
          {record.minimum_minor != null && (
            <div style={{ fontSize: 12, color: '#8c8c8c' }}>
              最低: <CurrencyAmount cents={record.minimum_minor} currency={record.currency} />
            </div>
          )}
        </div>
      ),
    },
    {
      title: '已还金额',
      key: 'total_paid_minor',
      render: (_: any, record: StatementListItem) => (
        <CurrencyAmount cents={record.total_paid_minor} currency={record.currency} style={{ color: '#52c41a' }} />
      ),
    },
    {
      title: '剩余应还',
      key: 'remaining_minor',
      render: (_: any, record: StatementListItem) => (
        <CurrencyAmount
          cents={record.remaining_minor}
          currency={record.currency}
          style={{
            fontWeight: 700,
            color: record.remaining_minor > 0 ? '#ff4d4f' : '#52c41a',
          }}
        />
      ),
    },
    {
      title: '状态',
      key: 'status',
      width: 100,
      render: (_: any, record: StatementListItem) => {
        if (record.is_paid) {
          return <Tag color="success">已结清</Tag>;
        }
        return <Tag color="warning">待还款</Tag>;
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_: any, record: StatementListItem) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => loadDetail(record.id)}>
            详情/版本
          </Button>
          {!record.is_paid && (
            <Button type="primary" size="small" onClick={() => openPaymentModal(record)}>
              还款
            </Button>
          )}
          <Button size="small" onClick={() => openCorrectModal(record)}>
            更正
          </Button>
          <Popconfirm
            title="确定彻底删除该账单吗？"
            description={
              record.total_paid_minor > 0
                ? '该账单包含已有还款记录，删除将一并清理还款流水及关联版本，操作不可恢复！'
                : '将删除该账单及关联的所有版本记录，操作不可恢复。'
            }
            onConfirm={() => handleDeleteStatement(record.id)}
            okText="删除"
            okButtonProps={{ danger: true }}
            cancelText="取消"
          >
            <Button danger size="small">
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card
        title={
          <Space>
            <FileTextOutlined />
            <span>账单与还款管理</span>
          </Space>
        }
        extra={
          <Space>
            <Select
              style={{ width: 140 }}
              placeholder="还款状态"
              value={statusFilter}
              onChange={(val) => {
                setStatusFilter(val);
                setPage(1);
              }}
              options={[
                { label: '全部状态', value: 'all' },
                { label: '仅待还款', value: 'unpaid' },
                { label: '仅已结清', value: 'paid' },
              ]}
            />
            <Select
              showSearch
              optionFilterProp="label"
              style={{ width: 280 }}
              placeholder="筛选银行账户"
              allowClear
              value={accountFilter}
              onChange={(val) => {
                setAccountFilter(val);
                setPage(1);
              }}
              options={accounts.map((a) => {
                const tails = (a.cards || []).map(c => c.tail || c.card_last4).filter(Boolean) as string[];
                const title = formatBankHolderTails(a.bank || a.bank_name, a.holder, tails);
                const label = a.alias && !title.includes(a.alias) ? `${title} (${a.alias})` : title;
                return {
                  label,
                  value: a.id,
                };
              })}
            />
            <Select
              style={{ width: 100 }}
              placeholder="币种"
              allowClear
              value={currencyFilter}
              onChange={(val) => {
                setCurrencyFilter(val);
                setPage(1);
              }}
              options={[
                { label: 'CNY', value: 'CNY' },
                { label: 'USD', value: 'USD' },
              ]}
            />
            <Button onClick={fetchStatements}>刷新</Button>
          </Space>
        }
      >
        <Table
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          onChange={handleTableChange}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
          }}
        />
      </Card>

      {/* 账单明细与历史版本抽屉 */}
      <Drawer
        title="账单明细与历史版本"
        placement="right"
        width={680}
        onClose={() => {
          setDetailVisible(false);
          setCurrentDetail(null);
        }}
        open={detailVisible}
        extra={
          currentDetail && (
            <Space>
              {!currentDetail.is_paid && (
                <Button type="primary" size="small" onClick={() => openPaymentModal(currentDetail)}>
                  记录还款
                </Button>
              )}
              <Button size="small" onClick={openCompletion}>
                后补明细
              </Button>
              <Button size="small" onClick={() => openCorrectModal(currentDetail)}>
                更正版本
              </Button>
              <Popconfirm
                title="确定彻底删除该账单吗？"
                description="将删除该账单及关联的所有版本和还款流水，操作不可恢复。"
                onConfirm={() => handleDeleteStatement(currentDetail.id)}
                okText="删除"
                okButtonProps={{ danger: true }}
                cancelText="取消"
              >
                <Button danger size="small">
                  删除账单
                </Button>
              </Popconfirm>
            </Space>
          )
        }
      >
        {currentDetail && (
          <div>
            <Row gutter={16} style={{ marginBottom: 20 }}>
              <Col span={8}>
                <Statistic
                  title="本期应还"
                  value={centsToYuanString(currentDetail.amount_minor)}
                  prefix={currentDetail.currency === 'CNY' ? '¥' : '$'}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="已有效还款"
                  value={centsToYuanString(currentDetail.total_paid_minor)}
                  prefix={currentDetail.currency === 'CNY' ? '¥' : '$'}
                  valueStyle={{ color: '#52c41a' }}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="剩余应还"
                  value={centsToYuanString(currentDetail.remaining_minor)}
                  prefix={currentDetail.currency === 'CNY' ? '¥' : '$'}
                  valueStyle={{ color: currentDetail.remaining_minor > 0 ? '#ff4d4f' : '#52c41a' }}
                />
              </Col>
            </Row>

            <Paragraph>
              <Text strong>银行账户: </Text>
              {formatBankHolderTails(currentDetail.bank, currentDetail.holder, currentDetail.card_tails)}{(() => {
                const cleaned = cleanAccountAlias(currentDetail.account_alias, currentDetail.bank, currentDetail.holder);
                return cleaned ? ` (${cleaned})` : '';
              })()}
              <Divider type="vertical" />
              <Text strong>账单日: </Text>
              {currentDetail.statement_date}
              <Divider type="vertical" />
              <Text strong>到期还款日: </Text>
              {currentDetail.due_date}
            </Paragraph>

            {currentDetail.associated_draft && (
              <Card size="small" title="关联提取草稿信息" style={{ marginBottom: 16, background: '#fafafa' }}>
                <Paragraph style={{ margin: 0 }}>
                  <Text type="secondary">草稿 ID: </Text>
                  <Text code>{currentDetail.associated_draft.draft_id}</Text>
                  <br />
                  <Text type="secondary">解析器: </Text>
                  <Tag>{currentDetail.associated_draft.extractor_name}</Tag>
                </Paragraph>
              </Card>
            )}

            <Divider orientation="left">当前版本交易明细</Divider>
            <Paragraph type="secondary">
              覆盖状态：{currentDetail.detail_status === 'complete' ? (currentDetail.expected_transaction_count ? '已核对笔数并人工确认完整' : '历史完整标记（缺少笔数证明，请复核）') : currentDetail.detail_status === 'partial' ? '部分明细' : '无明细'}。
              识别 {currentDetail.recognized_transaction_count ?? '未记录'} 笔，
              确认 {currentDetail.confirmed_transaction_count ?? '未记录'} 笔，
              异常 {currentDetail.flagged_transaction_count ?? '未记录'} 笔，
              来源预期 {currentDetail.expected_transaction_count ?? '未知'} 笔。
              交易明细仅供核对，不代表还款流水。
            </Paragraph>
            <Table size="small" rowKey="id" pagination={{ pageSize: 10 }}
              dataSource={currentDetail.transactions || []}
              columns={[
                { title: '序号', dataIndex: 'sequence', width: 60 },
                { title: '交易日', dataIndex: 'transaction_date', render: (v: string | null) => v || '-' },
                { title: '描述', dataIndex: 'description', render: (v: string | null) => v || '-' },
                { title: '尾号', dataIndex: 'card_tail', render: (v: string | null) => v || '-' },
                { title: '金额', render: (_: unknown, tx: StatementDetailData['transactions'][number]) =>
                  tx.amount_minor == null ? '-' : <CurrencyAmount cents={tx.amount_minor} currency={tx.currency || currentDetail.currency} /> },
              ]}
              locale={{ emptyText: '当前版本没有已确认交易明细' }} />

            <Divider orientation="left">明细快照历史（只读）</Divider>
            {(currentDetail.detail_history || []).length ? (
              <Timeline items={(currentDetail.detail_history || []).map((snapshot) => ({
                children: (
                  <Space wrap>
                    <Text>快照 #{snapshot.revision} · {snapshot.detail_status === 'complete' ? '完整' : snapshot.detail_status === 'partial' ? '部分' : '无明细'} · {new Date(snapshot.confirmed_at).toLocaleString()}</Text>
                    <Text type="secondary">账单版本：{snapshot.statement_version_id.slice(0, 8)} · 来源草稿：{snapshot.source_draft_id?.slice(0, 8) || '无'}</Text>
                    <Button size="small" loading={historyLoading} onClick={() => showDetailHistory(snapshot.id, snapshot.revision)}>查看明细</Button>
                  </Space>
                ),
              }))} />
            ) : <Text type="secondary">暂无独立明细快照；上方展示原账单版本内的明细。</Text>}

            <Divider orientation="left">还款记录列表</Divider>
            {currentDetail.payments && currentDetail.payments.length > 0 ? (
              <Table
                size="small"
                rowKey="id"
                pagination={false}
                dataSource={currentDetail.payments}
                columns={[
                  {
                    title: '还款时间',
                    dataIndex: 'recorded_at',
                    render: (t) => new Date(t).toLocaleString(),
                  },
                  {
                    title: '金额',
                    render: (_, r) => (
                      <CurrencyAmount
                        cents={r.amount_minor}
                        currency={r.currency}
                        style={{
                          textDecoration: r.revoked_at ? 'line-through' : undefined,
                          color: r.revoked_at ? '#8c8c8c' : '#52c41a',
                        }}
                      />
                    ),
                  },
                  {
                    title: '备注',
                    dataIndex: 'note',
                    render: (note, r) => (
                      <span>
                        {note || '-'}
                        {r.revoked_at && (
                          <div style={{ color: '#ff4d4f', fontSize: 12 }}>
                            已撤销: {r.revoke_reason || '无原因'} ({new Date(r.revoked_at).toLocaleString()})
                          </div>
                        )}
                      </span>
                    ),
                  },
                  {
                    title: '状态',
                    render: (_, r) =>
                      r.revoked_at ? (
                        <Tag color="error">已撤销</Tag>
                      ) : (
                        <Tag color="success">有效</Tag>
                      ),
                  },
                  {
                    title: '操作',
                    render: (_, r) => (
                      <Space size="small">
                        {!r.revoked_at && (
                          <Button
                            type="link"
                            danger
                            size="small"
                            onClick={() => {
                              setRevokePaymentId(r.id);
                              setRevokeReason('');
                              setRevokeModalVisible(true);
                            }}
                          >
                            撤销还款
                          </Button>
                        )}
                        <Popconfirm
                          title="确定删除此还款流水？"
                          description="删除后账单剩余应还金额将重新计算，操作不可恢复。"
                          onConfirm={() => handleDeletePayment(r.id)}
                          okText="删除"
                          okButtonProps={{ danger: true }}
                          cancelText="取消"
                        >
                          <Button type="link" danger size="small">
                            删除
                          </Button>
                        </Popconfirm>
                      </Space>
                    ),
                  },
                ]}
              />
            ) : (
              <Text type="secondary">暂无还款记录</Text>
            )}

            <Divider orientation="left" style={{ marginTop: 24 }}>
              历史更正版本链
            </Divider>
            <Timeline
              items={(currentDetail.versions || []).map((v) => ({
                color: v.id === currentDetail.current_version_id ? 'green' : 'gray',
                children: (
                  <div>
                    <Space>
                      <Text strong>版本 v{v.version_number}</Text>
                      {v.id === currentDetail.current_version_id && <Tag color="green">当前生效版本</Tag>}
                      <Tag>{v.source}</Tag>
                    </Space>
                    <div>
                      应还金额: <CurrencyAmount cents={v.amount_minor} currency={currentDetail.currency} />
                      {v.minimum_minor != null && (
                        <span style={{ marginLeft: 12, color: '#8c8c8c' }}>
                          最低: <CurrencyAmount cents={v.minimum_minor} currency={currentDetail.currency} />
                        </span>
                      )}
                    </div>
                    {v.reason && (
                      <div style={{ color: '#595959', fontSize: 13 }}>变更原因: {v.reason}</div>
                    )}
                    <div style={{ color: '#8c8c8c', fontSize: 12 }}>
                      确认时间: {new Date(v.created_at).toLocaleString()}
                      {v.confirmed_by && ` (${v.confirmed_by})`}
                    </div>
                  </div>
                ),
              }))}
            />
          </div>
        )}
      </Drawer>

      {/* 记录还款弹窗 */}
      <Modal
        title="记录还款"
        open={paymentModalVisible}
        onOk={handlePaymentSubmit}
        onCancel={() => setPaymentModalVisible(false)}
        confirmLoading={paymentLoading}
        okText="确认还款"
        cancelText="取消"
      >
        {paymentTarget && (
          <Form form={paymentForm} layout="vertical">
            <Paragraph>
              正在为 <Text strong>{formatBankHolderTails(paymentTarget.bank, paymentTarget.holder, paymentTarget.card_tails)}</Text> 账单记录还款。当前剩余应还金额:{' '}
              <CurrencyAmount
                cents={paymentTarget.remaining_minor}
                currency={paymentTarget.currency}
                style={{ color: '#ff4d4f', fontWeight: 700 }}
              />
            </Paragraph>
            <Form.Item
              name="amount_yuan"
              label="还款金额 (元)"
              rules={[
                { required: true, message: '请输入还款金额' },
                {
                  validator: async (_, val) => {
                    const cents = yuanStringToCents(val);
                    if (cents <= 0) throw new Error('还款金额必须大于0');
                    if (cents > paymentTarget.remaining_minor) {
                      throw new Error('还款金额不能大于剩余应还总额');
                    }
                  },
                },
              ]}
            >
              <Input placeholder="0.00" addonBefore={paymentTarget.currency === 'CNY' ? '¥' : '$'} />
            </Form.Item>
            <Form.Item name="note" label="还款备注 (可选)">
              <Input placeholder="例如: 手机银行转账全额结清" />
            </Form.Item>
          </Form>
        )}
      </Modal>

      {/* 纯明细后补：草稿选择与逐笔人工核对 */}
      <Modal
        title="后补账单交易明细"
        open={completionVisible}
        width={880}
        onCancel={() => setCompletionVisible(false)}
        onOk={submitCompletion}
        okText={replaceDetails ? '确认全量替换并保存快照' : '确认追加并保存快照'}
        okButtonProps={{ disabled: !completionDraft || selectedDetailRows.length === 0 }}
        confirmLoading={completionLoading}
        destroyOnClose
      >
        {currentDetail && <>
          <Paragraph type="secondary">仅更新交易明细快照，不修改账单应还金额、版本或还款记录。请与原始来源逐项核对；缺失字段不要猜测。</Paragraph>
          <Paragraph>目标：{formatBankHolderTails(currentDetail.bank, currentDetail.holder, currentDetail.card_tails)} · {currentDetail.statement_date} · {currentDetail.currency} · 本期 <CurrencyAmount cents={currentDetail.amount_minor} currency={currentDetail.currency} />；当前已确认 {currentDetail.transactions.length} 笔，明细修订 #{currentDetail.detail_revision ?? 0}。</Paragraph>
          <Form layout="vertical">
            <Form.Item label="待审核明细草稿（仅列出同银行、账期、币种的候选；最终仍由后台验证归属）">
              <Select
                placeholder="选择草稿后核对汇总、卡片与来源"
                value={completionDraft?.id}
                loading={completionLoading}
                onChange={selectCompletionDraft}
                options={candidateDrafts.map(draft => ({ value: draft.id, label: `草稿 ${draft.id.slice(0, 8)} · ${draft.bank || '银行未知'} · ${draft.card_tails.join('、') || '尾号未知'} · ${draft.amount_minor == null ? '金额未知' : centsToYuanString(draft.amount_minor)} ${draft.currency || ''}` }))}
              />
            </Form.Item>
            <Form.Item label="草稿不在候选列表时，输入其完整 ID 核对">
              <Input.Search value={manualDraftId} onChange={e => setManualDraftId(e.target.value)}
                enterButton="加载草稿" loading={completionLoading}
                onSearch={() => { if (manualDraftId.trim()) selectCompletionDraft(manualDraftId.trim()); }}
                placeholder="从草稿审核页复制草稿 ID" />
            </Form.Item>
          </Form>
          {completionDraft && <>
            <Paragraph>草稿：{completionDraft.bank || '银行未知'} · {completionDraft.statement_date} · 到期 {completionDraft.due_date || '未知'} · 卡尾号 {completionDraft.card_tails.join('、') || '未记录'} · 草稿修订 #{completionDraft.revision}</Paragraph>
            <Paragraph type="secondary">来源范围：{completionDraft.source_manifest?.entries?.map(e => e.filename || e.kind).join('、') || '未记录'}；{completionDraft.source_manifest?.has_unsupported ? '含不支持来源，不能标记完整' : '请核对是否有遗漏或截断'}。</Paragraph>
            <Table
              size="small" rowKey="id" pagination={{ pageSize: 10 }}
              dataSource={completionDraft.transactions || []}
              rowSelection={{
                selectedRowKeys: selectedDetailRows,
                onChange: keys => { setSelectedDetailRows(keys.map(String)); setMarkDetailsComplete(false); },
                getCheckboxProps: tx => ({ disabled: !!tx.review_flags?.length || tx.amount_minor == null || tx.amount_minor === 0 || tx.currency !== currentDetail.currency || (!!tx.card_tail && !currentDetail.card_tails?.includes(tx.card_tail)) }),
              }}
              columns={[
                { title: '序号', dataIndex: 'sequence', width: 65 },
                { title: '交易日', dataIndex: 'transaction_date', render: (v: string | null) => v || '待核对' },
                { title: '描述', dataIndex: 'description', render: (v: string | null) => v || '待核对' },
                { title: '尾号', dataIndex: 'card_tail', render: (v: string | null) => v || '-' },
                { title: '金额', render: (_: unknown, tx: TransactionDetail) => tx.amount_minor == null ? '待核对' : <CurrencyAmount cents={tx.amount_minor} currency={tx.currency || currentDetail.currency} /> },
                { title: '状态', render: (_: unknown, tx: TransactionDetail) => tx.review_flags?.length ? <Tag color="orange">{tx.review_flags.join('、')}</Tag> : <Tag color="green">可核对</Tag> },
              ]}
              locale={{ emptyText: '草稿无可核对交易明细' }}
            />
            <div style={{ marginTop: 16 }}>
              <label>保存方式：{' '}
                <Select style={{ width: 220 }} value={replaceDetails ? 'replace' : 'append'} onChange={value => { setReplaceDetails(value === 'replace'); setMarkDetailsComplete(false); }} options={[{ value: 'append', label: '追加（始终视为部分明细）' }, { value: 'replace', label: '全量替换当前明细' }]} />
              </label>
              {replaceDetails && <Paragraph type="warning" style={{ marginTop: 8 }}>全量替换会将本次勾选的交易作为当前全部明细；旧快照仍可在历史中查看。请确认原有 {currentDetail.transactions.length} 笔已在新来源中核对。</Paragraph>}
            </div>
            <div style={{ marginTop: 12 }}><label>原始来源可核对的本账期交易总笔数（未知请留空）：{' '}
              <Input style={{ width: 120 }} value={expectedDetailCount} onChange={e => { setExpectedDetailCount(e.target.value); setMarkDetailsComplete(false); }} placeholder="来源笔数" />
            </label></div>
            <label style={{ display: 'block', marginTop: 12 }}>
              <input type="checkbox" checked={markDetailsComplete}
                disabled={!replaceDetails || !selectedDetailRows.length || selectedDetailRows.length !== completionDraft.transactions.length ||
                  Number(expectedDetailCount) !== selectedDetailRows.length || !completionDraft.source_manifest?.entries?.length ||
                  !!completionDraft.source_manifest?.has_unsupported || completionDraft.source_manifest?.entries?.some(e => e.truncated || e.notes === 'file_adapter_required' || e.notes === 'unsupported_type')}
                onChange={e => setMarkDetailsComplete(e.target.checked)} />{' '}我已对照完整来源逐项核对，确认本账期明细无遗漏
            </label>
            <Paragraph type="secondary" style={{ marginTop: 8 }}>本次勾选 {selectedDetailRows.length} 笔；保存后预计 {selectedDetailRows.length + (replaceDetails ? 0 : currentDetail.transactions.length)} 笔。未标记完整时仅保存为部分明细。提交后如数据已变化，需刷新重新核对。</Paragraph>
          </>}
        </>}
      </Modal>

      <Modal title={historyTitle} open={historyVisible} width={800} footer={null} onCancel={() => setHistoryVisible(false)}>
        <Table size="small" rowKey="id" pagination={{ pageSize: 10 }} dataSource={historyRows}
          columns={[
            { title: '序号', dataIndex: 'sequence', width: 65 },
            { title: '交易日', dataIndex: 'transaction_date', render: (v: string | null) => v || '-' },
            { title: '描述', dataIndex: 'description', render: (v: string | null) => v || '-' },
            { title: '尾号', dataIndex: 'card_tail', render: (v: string | null) => v || '-' },
            { title: '金额', render: (_: unknown, tx: TransactionDetail) => tx.amount_minor == null ? '-' : <CurrencyAmount cents={tx.amount_minor} currency={tx.currency || currentDetail?.currency || 'CNY'} /> },
          ]}
          locale={{ emptyText: '该快照没有交易明细' }} />
      </Modal>

      {/* 版本更正弹窗 */}
      <Modal
        title="账单版本更正"
        open={correctModalVisible}
        onOk={handleCorrectSubmit}
        onCancel={() => setCorrectModalVisible(false)}
        confirmLoading={correctLoading}
        okText="提交更正版本"
        cancelText="取消"
      >
        {correctTarget && (
          <Form form={correctForm} layout="vertical">
            <Paragraph type="secondary">
              更正账单将生成新的不可变版本记录，已有效还款为{' '}
              <CurrencyAmount cents={correctTarget.total_paid_minor} currency={correctTarget.currency} />。
              新金额不得低于该已还金额。
            </Paragraph>
            <Form.Item
              name="amount_yuan"
              label="更正后总金额 (元)"
              rules={[
                { required: true, message: '请输入更正后金额' },
                {
                  validator: async (_, val) => {
                    const cents = yuanStringToCents(val);
                    if (cents < correctTarget.total_paid_minor) {
                      throw new Error('更正后金额不得低于已有效还款额');
                    }
                  },
                },
              ]}
            >
              <Input placeholder="0.00" addonBefore={correctTarget.currency === 'CNY' ? '¥' : '$'} />
            </Form.Item>
            <Form.Item name="minimum_yuan" label="更正后最低还款额 (元，可选)">
              <Input placeholder="留空保持为空" addonBefore={correctTarget.currency === 'CNY' ? '¥' : '$'} />
            </Form.Item>
            <Form.Item
              name="reason"
              label="更正原因 (必填，3-200字)"
              rules={[
                { required: true, message: '请填写更正原因' },
                { min: 3, message: '原因描述至少3个字符' },
                { max: 200, message: '原因描述不得超过200个字符' },
              ]}
            >
              <Input.TextArea rows={3} placeholder="说明更正背景，例如：银行出具补正说明或邮件复核更正" />
            </Form.Item>
          </Form>
        )}
      </Modal>

      {/* 撤销还款弹窗 */}
      <Modal
        title="撤销还款记录"
        open={revokeModalVisible}
        onOk={handleRevokePayment}
        onCancel={() => {
          setRevokeModalVisible(false);
          setRevokeReason('');
          setRevokePaymentId(null);
        }}
        confirmLoading={revokeLoading}
        okText="确认撤销"
        okButtonProps={{ danger: true }}
        cancelText="取消"
      >
        <Paragraph type="danger">
          撤销还款后，该笔还款将被标记为无效，账单的已还金额和剩余待还金额将重新计算。
        </Paragraph>
        <Form layout="vertical">
          <Form.Item label="撤销原因 (必填)" required>
            <Input.TextArea
              rows={3}
              value={revokeReason}
              onChange={(e) => setRevokeReason(e.target.value)}
              placeholder="请输入撤销原因，如：银行扣款冲正或录入错误"
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};
