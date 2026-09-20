import React, { useEffect, useState } from 'react';
import { Row, Col, Card, Statistic, Table, Tag, Typography, Button, Space, Alert, Spin } from 'antd';
import {
  AuditOutlined,
  SyncOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { overviewApi, mailboxApi } from '../api';
import { CurrencyAmount } from '../components/CurrencyAmount';

const { Title, Text } = Typography;

export const Overview: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState<boolean>(true);
  const [data, setData] = useState<any>(null);
  const [syncing, setSyncing] = useState<boolean>(false);

  const fetchOverview = async () => {
    try {
      setLoading(true);
      const res = await overviewApi.getOverview();
      setData(res.data);
    } catch (_) {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOverview();
  }, []);

  const handleQuickSync = async () => {
    try {
      setSyncing(true);
      // Trigger sync for first active mailbox if present
      const mailboxesRes = await mailboxApi.listMailboxes();
      const mailboxes = mailboxesRes.data?.mailboxes || [];
      const enabled = mailboxes.find((m: any) => m.is_enabled);
      if (enabled) {
        await mailboxApi.updateMailbox(enabled.id, { sync_now: true });
      }
      await fetchOverview();
    } catch (_) {
    } finally {
      setSyncing(false);
    }
  };

  if (loading && !data) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" tip="正在加载系统总览..." />
      </div>
    );
  }

  const balances = data?.currency_balances || [];
  const upcomingBills = data?.upcoming_bills || [];
  const pendingDrafts = data?.pending_drafts_count || 0;
  const jobStats = data?.job_stats || { pending: 0, running: 0, failed_last_24h: 0 };
  const latestSync = data?.latest_mail_sync;

  const columns = [
    {
      title: '账户 / 银行',
      key: 'account',
      render: (_: any, r: any) => (
        <Space direction="vertical" size={0}>
          <Text strong>{r.account_name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{r.bank_name}</Text>
        </Space>
      ),
    },
    {
      title: '到期还款日',
      dataIndex: 'payment_due_date',
      key: 'payment_due_date',
      render: (val: string, r: any) => (
        <Space>
          <span>{val}</span>
          {r.days_left <= 3 ? (
            <Tag color="error">剩 {r.days_left} 天</Tag>
          ) : (
            <Tag color="warning">剩 {r.days_left} 天</Tag>
          )}
        </Space>
      ),
    },
    {
      title: '待还金额',
      key: 'remaining',
      render: (_: any, r: any) => (
        <CurrencyAmount cents={r.remaining_cents} currency={r.currency} style={{ fontSize: 15, color: '#cf1322' }} />
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, r: any) => (
        <Button type="link" size="small" onClick={() => navigate('/statements')}>
          查看账单
        </Button>
      ),
    },
  ];

  return (
    <div>
      {pendingDrafts > 0 && (
        <Alert
          message={
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>
                发现 <strong>{pendingDrafts}</strong> 封邮件已解析出账单草稿，等待您的人工审核与确认入账。
              </span>
              <Button type="primary" size="small" onClick={() => navigate('/drafts')}>
                立即审核
              </Button>
            </div>
          }
          type="info"
          showIcon
          icon={<AuditOutlined />}
          style={{ marginBottom: 20 }}
        />
      )}

      {/* Currency Balance Summary Cards */}
      <Title level={4} style={{ marginBottom: 16 }}>
        各币种未结清总额
      </Title>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {balances.length === 0 ? (
          <Col span={24}>
            <Card>
              <div style={{ textAlign: 'center', padding: '16px 0', color: '#999' }}>
                暂无待还账单，所有账单均已结清或尚未入账。
              </div>
            </Card>
          </Col>
        ) : (
          balances.map((b: any) => (
            <Col xs={24} sm={12} md={8} key={b.currency}>
              <Card hoverable style={{ borderLeft: '4px solid #1890ff' }}>
                <Statistic
                  title={<Text strong style={{ fontSize: 14 }}>{b.currency} 应还总额 ({b.statement_count} 笔有效账单)</Text>}
                  valueRender={() => (
                    <CurrencyAmount
                      cents={b.total_due_cents}
                      currency={b.currency}
                      style={{ fontSize: 26, color: b.total_due_cents > 0 ? '#f5222d' : '#52c41a' }}
                    />
                  )}
                />
              </Card>
            </Col>
          ))
        )}
      </Row>

      {/* Grid: 7-Day Due Bills & Queue/Sync Status */}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card
            title={
              <Space>
                <ClockCircleOutlined style={{ color: '#faad14' }} />
                <span>近 7 天内即将到期账单</span>
              </Space>
            }
            extra={
              <Button type="link" onClick={() => navigate('/statements')}>
                全部账单 <ArrowRightOutlined />
              </Button>
            }
            bodyStyle={{ padding: 0 }}
          >
            <Table
              dataSource={upcomingBills}
              columns={columns}
              rowKey="id"
              pagination={false}
              locale={{ emptyText: '未来 7 天内无即将到期的账单' }}
            />
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Card title="后台同步与任务状态" size="small">
              <div style={{ marginBottom: 16 }}>
                <Text type="secondary">最近收件同步：</Text>
                <div style={{ marginTop: 4 }}>
                  {latestSync?.at ? (
                    <Space>
                      {latestSync.status === 'success' ? (
                        <CheckCircleOutlined style={{ color: '#52c41a' }} />
                      ) : (
                        <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />
                      )}
                      <span>{latestSync.mailbox_name || '默认邮箱'}</span>
                      <Text type="secondary" style={{ fontSize: 12 }}>({latestSync.at})</Text>
                    </Space>
                  ) : (
                    <Text type="secondary">尚未执行收件任务</Text>
                  )}
                </div>
              </div>

              <div style={{ marginBottom: 16 }}>
                <Text type="secondary">任务队列概况：</Text>
                <div style={{ display: 'flex', gap: 12, marginTop: 6 }}>
                  <Tag color="blue">排队中: {jobStats.pending}</Tag>
                  <Tag color="processing">执行中: {jobStats.running}</Tag>
                  <Tag color={jobStats.failed_last_24h > 0 ? 'error' : 'default'}>
                    24h失败: {jobStats.failed_last_24h}
                  </Tag>
                </div>
              </div>

              <div style={{ display: 'flex', gap: 8 }}>
                <Button icon={<SyncOutlined spin={syncing} />} onClick={handleQuickSync} loading={syncing} block>
                  检查新邮件
                </Button>
                <Button onClick={() => navigate('/jobs')} block>
                  查看队列
                </Button>
              </div>
            </Card>

            <Card title="快捷入口" size="small">
              <Space wrap>
                <Button onClick={() => navigate('/accounts')}>管理银行卡</Button>
                <Button onClick={() => navigate('/mailboxes')}>配置邮箱</Button>
                <Button onClick={() => navigate('/models')}>模型设置</Button>
                <Button onClick={() => navigate('/devices')}>配对手机</Button>
              </Space>
            </Card>
          </Space>
        </Col>
      </Row>
    </div>
  );
};
