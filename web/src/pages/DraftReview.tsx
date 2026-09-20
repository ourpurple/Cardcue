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
} from 'antd';
import {
  AuditOutlined,
  CheckOutlined,
  CloseOutlined,
  SaveOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
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
        message.error('入账前必须选择归属银行账户');
        return;
      }
      if (!values.statement_date || !values.due_date) {
        message.error('账单日与到期还款日不可为空');
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

      message.success('草稿审核通过，正式账单已生成入账');
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
      width: 140,
      render: (_: any, record: StatementDraftItem) => (
        <Button
          type={record.status === 'pending_review' ? 'primary' : 'default'}
          size="small"
          onClick={() => openReviewDrawer(record.id)}
        >
          {record.status === 'pending_review' ? '审核入账' : '查看详情'}
        </Button>
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
          </Space>
        }
      >
        <Table
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

      {/* 审核双栏证据比对与人工编辑抽屉 */}
      <Drawer
        title="草稿证据核对与人工入账"
        placement="right"
        width={960}
        open={drawerVisible}
        onClose={() => {
          setDrawerVisible(false);
          setCurrentDraft(null);
        }}
        extra={
          currentDraft &&
          currentDraft.status === 'pending_review' && (
            <Space>
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
                message="该草稿已被驳回拒绝"
                description={currentDraft.rejection_reason || '无驳回原因'}
                style={{ marginBottom: 16 }}
              />
            )}

            <Row gutter={24}>
              {/* 左侧：模型提取证据链与邮件原文 */}
              <Col span={12} style={{ borderRight: '1px solid #f0f0f0', paddingRight: 20 }}>
                <Title level={5}>
                  <FileTextOutlined style={{ marginRight: 6 }} />
                  提取依据与证据片段
                </Title>

                {currentDraft.source_email && (
                  <Descriptions size="small" column={1} bordered style={{ marginBottom: 16 }}>
                    <Descriptions.Item label="来源邮件主题">
                      <Text strong>{currentDraft.source_email.subject}</Text>
                    </Descriptions.Item>
                    <Descriptions.Item label="发件人">
                      {currentDraft.source_email.sender}
                    </Descriptions.Item>
                    <Descriptions.Item label="收信时间">
                      {new Date(currentDraft.source_email.email_date).toLocaleString()}
                    </Descriptions.Item>
                  </Descriptions>
                )}

                <div style={{ marginBottom: 16 }}>
                  <Text type="secondary">解析器架构: </Text>
                  <Tag color="geekblue">{currentDraft.extractor_name}</Tag>
                  <Text type="secondary" style={{ marginLeft: 12 }}>
                    版本 Revision: #{currentDraft.revision}
                  </Text>
                </div>

                <Divider orientation="left" style={{ margin: '12px 0' }}>
                  模型与规则定位的证据片段
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
                  正式账单入账参数
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
                      placeholder="请选择银行账户"
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
