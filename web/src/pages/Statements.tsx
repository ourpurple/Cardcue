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
import { statementsApi, accountsApi } from '../api';
import { CurrencyAmount, centsToYuanString, yuanStringToCents } from '../components/CurrencyAmount';
import { StatementListItem, StatementDetailData, BankAccount } from '../types';

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
      render: (_: any, record: StatementListItem) => (
        <div>
          <Text strong>{record.bank}</Text>
          {record.account_alias && (
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {record.account_alias}
              </Text>
            </div>
          )}
        </div>
      ),
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
              style={{ width: 160 }}
              placeholder="筛选银行账户"
              allowClear
              value={accountFilter}
              onChange={(val) => {
                setAccountFilter(val);
                setPage(1);
              }}
              options={accounts.map((a) => ({
                label: a.alias ? `${a.bank || a.bank_name} (${a.alias})` : a.bank || a.bank_name || a.id,
                value: a.id,
              }))}
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
              {currentDetail.bank} {currentDetail.account_alias && `(${currentDetail.account_alias})`}
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
              正在为 <Text strong>{paymentTarget.bank}</Text> 账单记录还款。当前剩余应还金额:{' '}
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
