import React, { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Space,
  Tag,
  Input,
  Select,
  Typography,
  message,
  Card,
  Drawer,
  Row,
  Col,
  Descriptions,
  Divider,
  Popconfirm,
  Badge,
} from 'antd';
import {
  MailOutlined,
  DownloadOutlined,
  SearchOutlined,
  PlayCircleOutlined,
  StopOutlined,
  UndoOutlined,
  PaperClipOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { emailsApi, mailboxApi, jobsApi } from '../api';
import { EmailSourceItem, EmailDetail, MailboxItem } from '../types';

const { Text, Paragraph, Title } = Typography;

export const EmailCenter: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [emails, setEmails] = useState<EmailSourceItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(15);

  // Filters
  const [mailboxFilter, setMailboxFilter] = useState<string | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [candidateOnly, setCandidateOnly] = useState<boolean>(false);
  const [searchKey, setSearchKey] = useState<string>('');

  const [mailboxes, setMailboxes] = useState<MailboxItem[]>([]);

  // Drawer detail state
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [currentEmail, setCurrentEmail] = useState<EmailDetail | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [batchLoading, setBatchLoading] = useState(false);

  const fetchMailboxes = async () => {
    try {
      const res = await mailboxApi.listMailboxes();
      setMailboxes(res.data || []);
    } catch (_) {}
  };

  const fetchEmails = async () => {
    setLoading(true);
    try {
      const params: any = {
        page,
        size: pageSize,
      };
      if (mailboxFilter) params.mailbox_id = mailboxFilter;
      if (statusFilter !== 'all') params.parse_status = statusFilter;
      if (candidateOnly) params.candidate_only = true;
      if (searchKey.trim()) params.search = searchKey.trim();

      const res = await emailsApi.listEmails(params);
      setEmails(res.data?.items || []);
      setTotal(res.data?.total || 0);
    } catch (_) {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMailboxes();
  }, []);

  useEffect(() => {
    fetchEmails();
  }, [page, pageSize, mailboxFilter, statusFilter, candidateOnly]);

  const loadDetail = async (id: string) => {
    setDrawerLoading(true);
    setDrawerVisible(true);
    try {
      const res = await emailsApi.getEmail(id);
      setCurrentEmail(res.data);
    } catch (_) {
      setDrawerVisible(false);
    } finally {
      setDrawerLoading(false);
    }
  };

  const handleAction = async (id: string, action: 'ignore' | 'restore') => {
    setActionLoading(true);
    try {
      await emailsApi.actionEmail(id, action);
      message.success(action === 'ignore' ? '已标记为忽略' : '已恢复为待解析');
      fetchEmails();
      if (currentEmail && currentEmail.id === id) {
        loadDetail(id);
      }
    } catch (_) {
    } finally {
      setActionLoading(false);
    }
  };

  const handleTriggerParse = async (emailId: string) => {
    setActionLoading(true);
    try {
      await jobsApi.createJob({
        kind: 'parse',
        target_id: emailId,
        allow_external: true,
      });
      message.success('已加入解析队列，正在由大模型和解析器处理');
      fetchEmails();
      if (currentEmail && currentEmail.id === emailId) {
        loadDetail(emailId);
      }
    } catch (_) {
    } finally {
      setActionLoading(false);
    }
  };

  const handleBatchParse = async (emailIds?: string[]) => {
    setBatchLoading(true);
    try {
      const payload: any = {
        include_failed: true,
      };
      if (emailIds && emailIds.length > 0) {
        payload.email_ids = emailIds;
      } else {
        if (mailboxFilter) payload.mailbox_id = mailboxFilter;
      }
      const res = await emailsApi.batchParse(payload);
      const enqueued = res.data?.enqueued ?? 0;
      if (enqueued === 0) {
        message.info('当前暂无可加入解析队列的待解析账单邮件');
      } else {
        message.success(`已将 ${enqueued} 封邮件成功加入大模型解析队列`);
      }
      setSelectedRowKeys([]);
      fetchEmails();
    } catch (err: any) {
      const msg = err.response?.data?.detail || '批量提交解析失败，请重试';
      message.error(msg);
    } finally {
      setBatchLoading(false);
    }
  };

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => setSelectedRowKeys(keys),
    getCheckboxProps: (record: EmailSourceItem) => ({
      disabled: record.parse_status === 'ignored',
    }),
  };

  const formatFileSize = (bytes: number): string => {
    if (!bytes) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  const columns = [
    {
      title: '邮件主题',
      key: 'subject',
      render: (_: any, record: EmailSourceItem) => (
        <div>
          <Text strong>{record.subject || '(无主题)'}</Text>
          {record.has_attachments && (
            <Tag color="cyan" style={{ marginLeft: 8 }}>
              <PaperClipOutlined /> 含附件
            </Tag>
          )}
          {record.is_statement_candidate && (
            <Tag color="gold" style={{ marginLeft: 4 }}>
              疑似账单
            </Tag>
          )}
        </div>
      ),
    },
    {
      title: '发件人',
      dataIndex: 'sender',
      key: 'sender',
      width: 220,
      render: (s: string) => (
        <Text ellipsis style={{ maxWidth: 210 }}>
          {s}
        </Text>
      ),
    },
    {
      title: '接收邮箱',
      dataIndex: 'mailbox_address',
      key: 'mailbox_address',
      width: 180,
    },
    {
      title: '收件时间',
      dataIndex: 'email_date',
      key: 'email_date',
      width: 170,
      render: (d: string) => new Date(d).toLocaleString(),
    },
    {
      title: '解析状态',
      key: 'parse_status',
      width: 110,
      render: (_: any, record: EmailSourceItem) => {
        const s = record.parse_status;
        if (s === 'parsed') return <Tag color="success">已解析</Tag>;
        if (s === 'failed') return <Tag color="error">解析失败</Tag>;
        if (s === 'ignored') return <Tag color="default">已忽略</Tag>;
        if (s === 'parsing') return <Tag color="processing">解析中</Tag>;
        return <Tag color="warning">待解析</Tag>;
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_: any, record: EmailSourceItem) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => loadDetail(record.id)}>
            查看详情
          </Button>
          {record.parse_status !== 'ignored' && record.parse_status !== 'parsed' && (
            <Button
              type="link"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={() => handleTriggerParse(record.id)}
            >
              解析
            </Button>
          )}
          {record.parse_status !== 'ignored' ? (
            <Popconfirm
              title="确定忽略此邮件吗？"
              description="忽略后该邮件将不再进入账单提取与候选列表"
              onConfirm={() => handleAction(record.id, 'ignore')}
            >
              <Button type="text" danger size="small">
                忽略
              </Button>
            </Popconfirm>
          ) : (
            <Button
              type="text"
              size="small"
              onClick={() => handleAction(record.id, 'restore')}
            >
              恢复
            </Button>
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
            <MailOutlined />
            <span>已收到邮件中心</span>
          </Space>
        }
        extra={
          <Space wrap>
            <Select
              style={{ width: 180 }}
              placeholder="筛选所属邮箱"
              allowClear
              value={mailboxFilter}
              onChange={(v) => {
                setMailboxFilter(v);
                setPage(1);
              }}
              options={mailboxes.map((m) => ({
                label: m.name ? `${m.name} (${m.email_address})` : m.email_address,
                value: m.id,
              }))}
            />
            <Select
              style={{ width: 130 }}
              value={statusFilter}
              onChange={(v) => {
                setStatusFilter(v);
                setPage(1);
              }}
              options={[
                { label: '全部状态', value: 'all' },
                { label: '待解析', value: 'pending' },
                { label: '已解析', value: 'parsed' },
                { label: '解析失败', value: 'failed' },
                { label: '已忽略', value: 'ignored' },
              ]}
            />
            <Select
              style={{ width: 130 }}
              value={candidateOnly ? 'candidate' : 'all'}
              onChange={(v) => {
                setCandidateOnly(v === 'candidate');
                setPage(1);
              }}
              options={[
                { label: '全部邮件', value: 'all' },
                { label: '仅疑似账单', value: 'candidate' },
              ]}
            />
            <Input.Search
              placeholder="搜索主题或发件人"
              style={{ width: 200 }}
              value={searchKey}
              onChange={(e) => setSearchKey(e.target.value)}
              onSearch={() => {
                setPage(1);
                fetchEmails();
              }}
              allowClear
            />
            <Button onClick={fetchEmails}>刷新</Button>
            <Popconfirm
              title={
                selectedRowKeys.length > 0
                  ? `确定批量解析选中的 ${selectedRowKeys.length} 封邮件吗？`
                  : '确定一键批量解析所有待解析账单邮件吗？'
              }
              description="系统将把符合条件的邮件加入大模型解析队列，自动提取账单并生成草稿。"
              onConfirm={() =>
                handleBatchParse(selectedRowKeys.length > 0 ? (selectedRowKeys as string[]) : undefined)
              }
              okText="立即解析"
              cancelText="取消"
            >
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={batchLoading}
              >
                {selectedRowKeys.length > 0
                  ? `批量解析选中 (${selectedRowKeys.length})`
                  : '一键批量解析待解析账单'}
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
              background: '#e6f7ff',
              border: '1px solid #91d5ff',
              borderRadius: 6,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span>
              已选择 <Text strong style={{ color: '#1677ff' }}>{selectedRowKeys.length}</Text> 封邮件
            </span>
            <Space>
              <Button size="small" onClick={() => setSelectedRowKeys([])}>
                取消勾选
              </Button>
              <Popconfirm
                title={`确定批量解析选中的 ${selectedRowKeys.length} 封邮件吗？`}
                description="选中的邮件将全部加入大模型解析队列"
                onConfirm={() => handleBatchParse(selectedRowKeys as string[])}
                okText="立即解析"
                cancelText="取消"
              >
                <Button size="small" type="primary" icon={<PlayCircleOutlined />} loading={batchLoading}>
                  批量解析选中项
                </Button>
              </Popconfirm>
            </Space>
          </div>
        )}
        <Table
          rowSelection={rowSelection}
          rowKey="id"
          columns={columns}
          dataSource={emails}
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

      {/* 邮件详情与安全预览抽屉 */}
      <Drawer
        title="邮件详情与正文安全预览"
        placement="right"
        width={780}
        open={drawerVisible}
        onClose={() => {
          setDrawerVisible(false);
          setCurrentEmail(null);
        }}
        extra={
          currentEmail && (
            <Space>
              {currentEmail.parse_status !== 'ignored' ? (
                <Button
                  danger
                  icon={<StopOutlined />}
                  onClick={() => handleAction(currentEmail.id, 'ignore')}
                  loading={actionLoading}
                >
                  设为忽略
                </Button>
              ) : (
                <Button
                  icon={<UndoOutlined />}
                  onClick={() => handleAction(currentEmail.id, 'restore')}
                  loading={actionLoading}
                >
                  恢复待解析
                </Button>
              )}
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={() => handleTriggerParse(currentEmail.id)}
                loading={actionLoading}
              >
                触发大模型解析
              </Button>
            </Space>
          )
        }
      >
        {currentEmail && (
          <div>
            <Descriptions size="small" bordered column={2} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="主题" span={2}>
                <Text strong>{currentEmail.subject}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="发件人">{currentEmail.sender}</Descriptions.Item>
              <Descriptions.Item label="收件人">{currentEmail.recipient}</Descriptions.Item>
              <Descriptions.Item label="所属邮箱">{currentEmail.mailbox_address}</Descriptions.Item>
              <Descriptions.Item label="收信时间">
                {new Date(currentEmail.email_date).toLocaleString()}
              </Descriptions.Item>
              <Descriptions.Item label="文件夹 / UID">
                {currentEmail.folder} / {currentEmail.uid}
              </Descriptions.Item>
              <Descriptions.Item label="疑似账单标记">
                {currentEmail.is_statement_candidate ? (
                  <Tag color="gold">是 (命中银行/账单特征)</Tag>
                ) : (
                  <Tag color="default">否</Tag>
                )}
              </Descriptions.Item>
              {currentEmail.error_message && (
                <Descriptions.Item label="解析错误" span={2}>
                  <Text type="danger">{currentEmail.error_message}</Text>
                </Descriptions.Item>
              )}
            </Descriptions>

            {currentEmail.attachments && currentEmail.attachments.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Divider orientation="left">附件清单 ({currentEmail.attachments.length})</Divider>
                <Table
                  size="small"
                  pagination={false}
                  rowKey="id"
                  dataSource={currentEmail.attachments}
                  columns={[
                    {
                      title: '文件名',
                      dataIndex: 'filename',
                      key: 'filename',
                      render: (f: string) => (
                        <Space>
                          <PaperClipOutlined />
                          <Text strong>{f}</Text>
                        </Space>
                      ),
                    },
                    {
                      title: '类型',
                      dataIndex: 'content_type',
                      key: 'content_type',
                      render: (t: string) => <Tag>{t}</Tag>,
                    },
                    {
                      title: '大小',
                      dataIndex: 'size_bytes',
                      key: 'size_bytes',
                      render: (b: number) => formatFileSize(b),
                    },
                    {
                      title: '操作',
                      key: 'action',
                      render: (_: any, att: any) => (
                        <Button
                          type="link"
                          size="small"
                          icon={<DownloadOutlined />}
                          href={emailsApi.getAttachmentDownloadUrl(att.id)}
                          target="_blank"
                        >
                          下载附件
                        </Button>
                      ),
                    },
                  ]}
                />
              </div>
            )}

            {currentEmail.drafts && currentEmail.drafts.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Divider orientation="left">关联生成的草稿 ({currentEmail.drafts.length})</Divider>
                <Table
                  size="small"
                  pagination={false}
                  rowKey="id"
                  dataSource={currentEmail.drafts}
                  columns={[
                    {
                      title: '草稿 ID',
                      dataIndex: 'id',
                      render: (id: string) => <Text code>{id.slice(0, 8)}...</Text>,
                    },
                    {
                      title: '银行',
                      dataIndex: 'bank',
                      render: (b: string) => b || '未知',
                    },
                    {
                      title: '状态',
                      dataIndex: 'status',
                      render: (s: string) =>
                        s === 'confirmed' ? (
                          <Tag color="success">已入账</Tag>
                        ) : s === 'rejected' ? (
                          <Tag color="error">已驳回</Tag>
                        ) : (
                          <Tag color="warning">待审核</Tag>
                        ),
                    },
                    {
                      title: '解析器',
                      dataIndex: 'extractor_name',
                    },
                  ]}
                />
              </div>
            )}

            <Divider orientation="left">正文安全纯文本预览</Divider>
            <div
              style={{
                backgroundColor: '#f5f5f5',
                padding: 16,
                borderRadius: 6,
                fontFamily: 'Consolas, Menlo, monospace',
                fontSize: 13,
                lineHeight: 1.6,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                maxHeight: 500,
                overflowY: 'auto',
                border: '1px solid #e8e8e8',
              }}
            >
              {currentEmail.body_preview || '(正文为空或已被安全过滤)'}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};
