import React, { useEffect, useState } from 'react';
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
  Row,
  Col,
  Alert,
  Divider,
  Descriptions,
  Popconfirm,
} from 'antd';
import {
  AuditOutlined,
  CheckOutlined,
  CloseOutlined,
  SaveOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  DeleteOutlined,
  ClearOutlined,
} from '@ant-design/icons';
import { draftsApi, accountsApi } from '../api';
import { CurrencyAmount, centsToYuanString, yuanStringToCents } from '../components/CurrencyAmount';
import { StatementDraftItem, StatementDraftDetail, BankAccount } from '../types';

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

export const DraftReview: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [drafts, setDrafts] = useState<StatementDraftItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [statusFilter, setStatusFilter] = useState<string>('pending_review');

  // Multi-select & Batch / Clear state
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [clearLoading, setClearLoading] = useState(false);

  // Review Drawer state
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [currentDraft, setCurrentDraft] = useState<StatementDraftDetail | null>(null);
  const [candidateCards, setCandidateCards] = useState<Array<{ id: string; tail: string; display_name: string | null }>>([]);

  const [form] = Form.useForm();
  const [actionLoading, setActionLoading] = useState(false);

  // Reject modal
  const [rejectModalVisible, setRejectModalVisible] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  const statusLabelMap: Record<string, string> = {
    pending_review: '待人工审核',
    confirmed: '已确认入账',
    rejected: '已驳回',
    all: '全部状态',
  };

  const fetchDrafts = async () => {
    setLoading(true);
    try {
      const res = await draftsApi.listDrafts({
        page,
        size: pageSize,
        status: statusFilter,
      });
      setDrafts(res.data?.items || []);
      setTotal(res.data?.total || 0);
    } catch (_) {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDrafts();
  }, [page, pageSize, statusFilter]);

  const handleDeleteDraft = async (draftId: string) => {
    try {
      await draftsApi.deleteDraft(draftId);
      message.success('草稿已删除');
      setSelectedRowKeys((prev) => prev.filter((k) => k !== draftId));
      fetchDrafts();
    } catch (err: any) {
      const msg = err.response?.data?.detail || '删除草稿失败';
      message.error(msg);
    }
  };

  const handleBatchDelete = async () => {
    if (selectedRowKeys.length === 0) return;
    setBatchDeleting(true);
    try {
      const res = await draftsApi.batchDeleteDrafts(selectedRowKeys as string[]);
      const deletedCount = res.data?.deleted_count ?? selectedRowKeys.length;
      message.success(`已成功删除 ${deletedCount} 个草稿`);
      setSelectedRowKeys([]);
      fetchDrafts();
    } catch (err: any) {
      const msg = err.response?.data?.detail || '批量删除草稿失败';
      message.error(msg);
    } finally {
      setBatchDeleting(false);
    }
  };

  const handleClearDrafts = async () => {
    setClearLoading(true);
    try {
      const res = await draftsApi.clearDrafts({ status: statusFilter });
      const count = res.data?.deleted_count ?? 0;
      message.success(count > 0 ? `已成功清空 ${count} 个草稿` : '当前无可清空的草稿');
      setSelectedRowKeys([]);
      fetchDrafts();
    } catch (err: any) {
      const msg = err.response?.data?.detail || '一键清空草稿失败';
      message.error(msg);
    } finally {
      setClearLoading(false);
    }
  };

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => setSelectedRowKeys(keys),
  };

  const openReviewDrawer = async (draftId: string) => {
    setDrawerLoading(true);
    setDrawerVisible(true);
    try {
      const res = await draftsApi.getDraft(draftId);
      const detail: StatementDraftDetail = res.data;
      setCurrentDraft(detail);
      setCandidateCards(detail.candidate_cards || []);

      form.setFieldsValue({
        account_id: detail.matched_account_id || undefined,
        card_id: detail.matched_card_id || undefined,
        bank: detail.bank || '',
        currency: detail.currency || 'CNY',
        amount_yuan: detail.amount_minor != null ? (detail.amount_minor / 100).toFixed(2) : '',
        minimum_yuan: detail.minimum_minor != null ? (detail.minimum_minor / 100).toFixed(2) : '',
        statement_date: detail.statement_date || '',
        due_date: detail.due_date || '',
      });
    } catch (_) {
      setDrawerVisible(false);
    } finally {
      setDrawerLoading(false);
    }
  };

  const handleAccountChange = async (accountId: string) => {
    form.setFieldValue('card_id', undefined);
    if (!accountId) {
      setCandidateCards([]);
      return;
    }
    try {
      const res = await accountsApi.listCards(accountId);
      setCandidateCards(res.data || []);
    } catch (_) {
      setCandidateCards([]);
    }
  };

  const handleSaveDraft = async () => {
    if (!currentDraft) return;
    try {
      const values = await form.validateFields();
      setActionLoading(true);
      const amountMinor = values.amount_yuan ? yuanStringToCents(values.amount_yuan) : null;
      const minMinor = values.minimum_yuan ? yuanStringToCents(values.minimum_yuan) : null;

      await draftsApi.updateDraft(currentDraft.id, {
        expected_revision: currentDraft.revision,
        bank: values.bank || null,
        currency: values.currency || null,
        amount_minor: amountMinor,
        minimum_minor: minMinor,
        statement_date: values.statement_date || null,
        due_date: values.due_date || null,
        matched_account_id: values.account_id || null,
        matched_card_id: values.card_id || null,
      });

      message.success('草稿内容已暂存');
      openReviewDrawer(currentDraft.id);
      fetchDrafts();
    } catch (_) {
    } finally {
      setActionLoading(false);
    }
  };

  const handleConfirmDraft = async () => {
    if (!currentDraft) return;
    try {
      const values = await form.validateFields();
      if (!values.account_id) {
        message.error('请在确认前选择归属银行账户');
        return;
      }
      if (!values.statement_date || !values.due_date) {
        message.error('账单日与到期还款日不能为空');
        return;
      }
      const amountMinor = yuanStringToCents(values.amount_yuan);
      if (amountMinor < 0) {
        message.error('账单金额不能为负数');
        return;
      }

      setActionLoading(true);
      const minMinor = values.minimum_yuan ? yuanStringToCents(values.minimum_yuan) : null;

      await draftsApi.confirmDraft(currentDraft.id, {
        request_id: generateUUID(),
        expected_revision: currentDraft.revision,
        account_id: values.account_id,
        card_id: values.card_id || null,
        currency: values.currency || 'CNY',
        amount_minor: amountMinor,
        minimum_minor: minMinor,
        statement_date: values.statement_date,
        due_date: values.due_date,
      });

      message.success('草稿已通过并生成正式账单与待还款项');
      setDrawerVisible(false);
      fetchDrafts();
    } catch (_) {
    } finally {
      setActionLoading(false);
    }
  };

  const handleRejectDraft = async () => {
    if (!currentDraft || !rejectReason.trim()) {
      message.error('请填写驳回原因');
      return;
    }
    setActionLoading(true);
    try {
      await draftsApi.rejectDraft(currentDraft.id, rejectReason.trim());
      message.success('已驳回该草稿');
      setRejectModalVisible(false);
      setRejectReason('');
      setDrawerVisible(false);
      fetchDrafts();
    } catch (_) {
    } finally {
      setActionLoading(false);
    }
  };

  const columns = [
    {
      title: '银行与卡号',
      key: 'bank',
      render: (_: any, record: StatementDraftItem) => (
        <div>
          <Text strong>{record.bank || '未知银行'}</Text>
          <div>
            {record.card_tails && record.card_tails.length > 0 ? (
              record.card_tails.map((t) => <Tag key={t}>尾号 {t}</Tag>)
            ) : (
              <Text type="secondary" style={{ fontSize: 12 }}>
                未识别尾号
              </Text>
            )}
          </div>
        </div>
      ),
    },
    {
      title: '识别账单金额',
      key: 'amount_minor',
      render: (_: any, record: StatementDraftItem) => (
        <div>
          <CurrencyAmount cents={record.amount_minor} currency={record.currency || 'CNY'} style={{ fontWeight: 600 }} />
          {record.minimum_minor != null && (
            <div style={{ fontSize: 12, color: '#8c8c8c' }}>
              最低: <CurrencyAmount cents={record.minimum_minor} currency={record.currency || 'CNY'} />
            </div>
          )}
        </div>
      ),
    },
    {
      title: '关键日期',
      key: 'dates',
      render: (_: any, record: StatementDraftItem) => (
        <div style={{ fontSize: 13 }}>
          <div>账单日: {record.statement_date || '-'}</div>
          <div>还款日: {record.due_date || '-'}</div>
        </div>
      ),
    },
    {
      title: '匹配账户',
      key: 'matched',
      render: (_: any, record: StatementDraftItem) => (
        <div>
          {record.matched_account_name ? (
            <Tag color="blue">{record.matched_account_name}</Tag>
          ) : (
            <Tag color="default">未匹配</Tag>
          )}
          {record.matched_card_tail && <Tag>尾号 {record.matched_card_tail}</Tag>}
        </div>
      ),
    },
    {
      title: '审核状态',
      key: 'status',
      width: 110,
      render: (_: any, record: StatementDraftItem) => {
        if (record.status === 'confirmed') return <Tag color="success">已确认入账</Tag>;
        if (record.status === 'rejected') return <Tag color="error">已驳回</Tag>;
        return <Tag color="processing">待人工审核</Tag>;
      },
    },
    {
      title: '解析来源',
      dataIndex: 'extractor_name',
      key: 'extractor_name',
      width: 140,
      render: (name: string) => <Tag>{name || '模型解析'}</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_: any, record: StatementDraftItem) => (
        <Space size="small">
          <Button
            type={record.status === 'pending_review' ? 'primary' : 'default'}
            size="small"
            onClick={() => openReviewDrawer(record.id)}
          >
            {record.status === 'pending_review' ? '审核入账' : '查看详情'}
          </Button>
          <Popconfirm
            title="确定删除此账单草稿吗？"
            description="删除后草稿将被清除，关联邮件将恢复待解析。"
            onConfirm={() => handleDeleteDraft(record.id)}
            okText="确定删除"
            okButtonProps={{ danger: true }}
            cancelText="取消"
          >
            <Button type="link" danger size="small" icon={<DeleteOutlined />}>
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
            <AuditOutlined />
            <span>账单草稿审核中心</span>
          </Space>
        }
        extra={
          <Space>
            <Select
              style={{ width: 140 }}
              value={statusFilter}
              onChange={(v) => {
                setStatusFilter(v);
                setSelectedRowKeys([]);
                setPage(1);
              }}
              options={[
                { label: '待人工审核', value: 'pending_review' },
                { label: '已确认入账', value: 'confirmed' },
                { label: '已驳回', value: 'rejected' },
                { label: '全部状态', value: 'all' },
              ]}
            />
            <Button onClick={fetchDrafts}>刷新</Button>
            <Popconfirm
              title={`确定一键清空${statusFilter === 'all' ? '所有' : `所有【${statusLabelMap[statusFilter] || statusFilter}】`}账单草稿吗？`}
              description="清空后所有符合条件的草稿将被永久删除，关联邮件将恢复待解析。正式入账账单不受影响。此操作不可恢复！"
              onConfirm={handleClearDrafts}
              okText="确定清空"
              okButtonProps={{ danger: true }}
              cancelText="取消"
            >
              <Button danger icon={<ClearOutlined />} loading={clearLoading}>
                一键清空
              </Button>
            </Popconfirm>
          </Space>
        }
      >
        {selectedRowKeys.length > 0 && (
          <div
            style={{
              marginBottom: 12,
              padding: '8px 16px',
              background: '#fff1f0',
              border: '1px solid #ffa39e',
              borderRadius: 6,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span>
              已选择 <Text strong style={{ color: '#cf1322' }}>{selectedRowKeys.length}</Text> 个草稿
            </span>
            <Space>
              <Button size="small" onClick={() => setSelectedRowKeys([])}>
                取消勾选
              </Button>
              <Popconfirm
                title={`确定批量删除选中的 ${selectedRowKeys.length} 个草稿吗？`}
                description="删除后草稿将被清除，关联邮件将恢复待解析。"
                onConfirm={handleBatchDelete}
                okText="确定删除"
                okButtonProps={{ danger: true }}
                cancelText="取消"
              >
                <Button size="small" type="primary" danger icon={<DeleteOutlined />} loading={batchDeleting}>
                  批量删除选中项
                </Button>
              </Popconfirm>
            </Space>
          </div>
        )}
        <Table
          rowSelection={rowSelection}
          rowKey="id"
          columns={columns}
          dataSource={drafts}
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
        />
      </Card>

      {/* 证据核对与人工审核抽屉 */}
      <Drawer
        title="草稿证据核对与人工审核"
        placement="right"
        width={960}
        open={drawerVisible}
        onClose={() => {
          setDrawerVisible(false);
          setCurrentDraft(null);
        }}
        extra={
          currentDraft && (
            <Space>
              <Popconfirm
                title="确定删除此账单草稿吗？"
                description="删除后草稿将被清除，关联邮件将恢复待解析。"
                onConfirm={async () => {
                  await handleDeleteDraft(currentDraft.id);
                  setDrawerVisible(false);
                }}
                okText="确定删除"
                okButtonProps={{ danger: true }}
                cancelText="取消"
              >
                <Button danger icon={<DeleteOutlined />}>
                  删除草稿
                </Button>
              </Popconfirm>
              {currentDraft.status === 'pending_review' && (
                <>
                  <Button
                    danger
                    icon={<CloseOutlined />}
                    onClick={() => setRejectModalVisible(true)}
                    loading={actionLoading}
                  >
                    驳回草稿
                  </Button>
                  <Button icon={<SaveOutlined />} onClick={handleSaveDraft} loading={actionLoading}>
                    暂存修改
                  </Button>
                  <Button
                    type="primary"
                    icon={<CheckOutlined />}
                    onClick={handleConfirmDraft}
                    loading={actionLoading}
                  >
                    确认入账
                  </Button>
                </>
              )}
            </Space>
          )
        }
      >
        {currentDraft && (
          <div>
            {currentDraft.review_reasons && currentDraft.review_reasons.length > 0 && (
              <Alert
                type="warning"
                showIcon
                message="需重点人工核对原因"
                description={
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {currentDraft.review_reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                }
                style={{ marginBottom: 16 }}
              />
            )}

            {currentDraft.status === 'confirmed' && (
              <Alert
                type="success"
                showIcon
                message="该草稿已成功确认入账为正式账单"
                style={{ marginBottom: 16 }}
              />
            )}

            {currentDraft.status === 'rejected' && (
              <Alert
                type="error"
                showIcon
                message="该草稿已被人工拒绝"
                description={currentDraft.rejection_reason || '无驳回原因'}
                style={{ marginBottom: 16 }}
              />
            )}

            <Row gutter={24}>
              {/* 左侧：模型提取证据与源邮件原文 */}
              <Col span={12} style={{ borderRight: '1px solid #f0f0f0', paddingRight: 20 }}>
                <Title level={5}>
                  <FileTextOutlined style={{ marginRight: 6 }} />
                  提取上下文与证据片段
                </Title>

                {currentDraft.source_email && (
                  <Descriptions size="small" column={1} bordered style={{ marginBottom: 16 }}>
                    <Descriptions.Item label="来源邮件主题">
                      <Text strong>{currentDraft.source_email.subject}</Text>
                    </Descriptions.Item>
                    <Descriptions.Item label="发件人">
                      {currentDraft.source_email.sender}
                    </Descriptions.Item>
                    <Descriptions.Item label="邮件时间">
                      {new Date(currentDraft.source_email.email_date).toLocaleString()}
                    </Descriptions.Item>
                  </Descriptions>
                )}

                <div style={{ marginBottom: 16 }}>
                  <Text type="secondary">解析处理器: </Text>
                  <Tag color="geekblue">{currentDraft.extractor_name}</Tag>
                  <Text type="secondary" style={{ marginLeft: 12 }}>
                    版本 Revision: #{currentDraft.revision}
                  </Text>
                </div>

                <Divider orientation="left" style={{ margin: '12px 0' }}>
                  模型高置信度证据片段
                </Divider>

                {currentDraft.evidence && currentDraft.evidence.length > 0 ? (
                  <div>
                    {currentDraft.evidence.map((ev: any, idx: number) => (
                      <Card
                        key={idx}
                        size="small"
                        style={{ marginBottom: 10, background: '#fafafa' }}
                        title={
                          <Space>
                            <Tag color="cyan">{ev.field || '字段'}</Tag>
                            <Text code>{ev.raw_value || ev.value || '-'}</Text>
                          </Space>
                        }
                      >
                        {ev.snippet ? (
                          <Paragraph
                            style={{
                              fontFamily: 'monospace',
                              fontSize: 12,
                              background: '#fff',
                              padding: 8,
                              borderRadius: 4,
                              margin: 0,
                              whiteSpace: 'pre-wrap',
                              border: '1px solid #e8e8e8',
                            }}
                          >
                            {ev.snippet}
                          </Paragraph>
                        ) : (
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {JSON.stringify(ev)}
                          </Text>
                        )}
                      </Card>
                    ))}
                  </div>
                ) : (
                  <Paragraph type="secondary">暂无结构化证据片段记录</Paragraph>
                )}
              </Col>

              {/* 右侧：人工确认与修正表单 */}
              <Col span={12} style={{ paddingLeft: 20 }}>
                <Title level={5}>
                  <AuditOutlined style={{ marginRight: 6 }} />
                  正式账单核对表单
                </Title>

                <Form
                  form={form}
                  layout="vertical"
                  disabled={currentDraft.status !== 'pending_review'}
                >
                  <Form.Item
                    name="account_id"
                    label="归属银行账户 (必填)"
                    rules={[{ required: true, message: '请选择归属银行账户' }]}
                  >
                    <Select
                      placeholder="请选择归属银行账户"
                      onChange={handleAccountChange}
                      options={(currentDraft.candidate_accounts || []).map((a) => ({
                        label: a.alias ? `${a.bank} (${a.alias})` : a.bank,
                        value: a.id,
                      }))}
                    />
                  </Form.Item>

                  <Form.Item name="card_id" label="归属卡片 (可选)">
                    <Select
                      placeholder="选择具体卡片"
                      allowClear
                      options={candidateCards.map((c) => ({
                        label: c.display_name ? `尾号 ${c.tail} (${c.display_name})` : `尾号 ${c.tail}`,
                        value: c.id,
                      }))}
                    />
                  </Form.Item>

                  <Row gutter={12}>
                    <Col span={14}>
                      <Form.Item
                        name="bank"
                        label="识别银行名称"
                        rules={[{ required: true, message: '请输入银行名称' }]}
                      >
                        <Input />
                      </Form.Item>
                    </Col>
                    <Col span={10}>
                      <Form.Item
                        name="currency"
                        label="币种"
                        rules={[{ required: true, message: '请选择币种' }]}
                      >
                        <Select
                          options={[
                            { label: 'CNY (人民币)', value: 'CNY' },
                            { label: 'USD (美元)', value: 'USD' },
                          ]}
                        />
                      </Form.Item>
                    </Col>
                  </Row>

                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item
                        name="amount_yuan"
                        label="账单应还总额 (元)"
                        rules={[{ required: true, message: '请输入应还总额' }]}
                      >
                        <Input placeholder="0.00" />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item name="minimum_yuan" label="最低还款额 (元，可选)">
                        <Input placeholder="0.00" />
                      </Form.Item>
                    </Col>
                  </Row>

                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item
                        name="statement_date"
                        label="账单日"
                        rules={[{ required: true, message: '请填写账单日 (YYYY-MM-DD)' }]}
                      >
                        <Input placeholder="YYYY-MM-DD" />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        name="due_date"
                        label="到期还款日"
                        rules={[{ required: true, message: '请填写到期还款日 (YYYY-MM-DD)' }]}
                      >
                        <Input placeholder="YYYY-MM-DD" />
                      </Form.Item>
                    </Col>
                  </Row>
                </Form>
              </Col>
            </Row>
          </div>
        )}
      </Drawer>

      {/* 驳回草稿弹窗 */}
      <Modal
        title="驳回账单草稿"
        open={rejectModalVisible}
        onOk={handleRejectDraft}
        onCancel={() => {
          setRejectModalVisible(false);
          setRejectReason('');
        }}
        confirmLoading={actionLoading}
        okText="确认驳回"
        okButtonProps={{ danger: true }}
        cancelText="取消"
      >
        <Paragraph type="danger">
          驳回后该草稿将被标记为已拒绝，不会生成正式账单。请填写驳回原因便于后续模型调优与排查。
        </Paragraph>
        <Form layout="vertical">
          <Form.Item label="驳回原因 (必填)" required>
            <Input.TextArea
              rows={3}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="例如: 邮件为营销推文非真实账单，或识别金额严重失真"
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};
