import React, { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Space,
  Tag,
  Modal,
  Typography,
  Card,
  Row,
  Col,
  Statistic,
  Input,
  Select,
  Badge,
  Divider,
} from 'antd';
import {
  SafetyCertificateOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  CloudServerOutlined,
  FolderOpenOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { systemApi } from '../api';
import { AuditLogItem, SystemStatusData } from '../types';

const { Text, Paragraph } = Typography;

export const AuditLogs: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [actionFilter, setActionFilter] = useState<string>('');
  const [actorFilter, setActorFilter] = useState<string>('');

  // Status
  const [statusLoading, setStatusLoading] = useState(false);
  const [systemStatus, setSystemStatus] = useState<SystemStatusData | null>(null);

  // Detail modal
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedLog, setSelectedLog] = useState<AuditLogItem | null>(null);

  const fetchStatus = async () => {
    setStatusLoading(true);
    try {
      const res = await systemApi.getStatus();
      setSystemStatus(res.data);
    } catch (_) {
    } finally {
      setStatusLoading(false);
    }
  };

  const fetchAudit = async () => {
    setLoading(true);
    try {
      const params: any = { page, size: pageSize };
      if (actionFilter.trim()) params.action = actionFilter.trim();
      if (actorFilter.trim()) params.actor = actorFilter.trim();

      const res = await systemApi.listAudit(params);
      setLogs(res.data?.items || []);
      setTotal(res.data?.total || 0);
    } catch (_) {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    fetchAudit();
  }, [page, pageSize]);

  const formatFileSize = (bytes: number): string => {
    if (!bytes) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  const columns = [
    {
      title: '发生时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (t: string) => new Date(t).toLocaleString(),
    },
    {
      title: '操作者',
      dataIndex: 'actor',
      key: 'actor',
      width: 140,
      render: (a: string) => <Tag color="blue">{a}</Tag>,
    },
    {
      title: '审计事件动作',
      dataIndex: 'action',
      key: 'action',
      width: 180,
      render: (act: string) => <Text code strong>{act}</Text>,
    },
    {
      title: '操作目标对象',
      dataIndex: 'target',
      key: 'target',
      width: 180,
      render: (t: string | null) => (t ? <Text code>{t}</Text> : '-'),
    },
    {
      title: '明细概要',
      key: 'detail',
      render: (_: any, r: AuditLogItem) => {
        const detailStr = r.detail ? JSON.stringify(r.detail) : '{}';
        return (
          <Space>
            <Text ellipsis style={{ maxWidth: 300 }} type="secondary">
              {detailStr}
            </Text>
            <Button
              type="link"
              size="small"
              onClick={() => {
                setSelectedLog(r);
                setDetailModalVisible(true);
              }}
            >
              展开完整
            </Button>
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      {/* 顶部系统健康探针卡片 */}
      <Card
        title={
          <Space>
            <DashboardOutlined />
            <span>服务端运行环境与健康探针</span>
          </Space>
        }
        extra={
          <Button icon={<SyncOutlined />} onClick={fetchStatus} loading={statusLoading}>
            刷新探针
          </Button>
        }
        style={{ marginBottom: 20 }}
      >
        {systemStatus ? (
          <Row gutter={16}>
            <Col span={6}>
              <Card size="small" bordered={false} style={{ background: '#f6ffed' }}>
                <Statistic
                  title="API 服务与版本"
                  value={systemStatus.api.version}
                  prefix={<CloudServerOutlined style={{ color: '#52c41a' }} />}
                />
                <div style={{ fontSize: 12, color: '#52c41a', marginTop: 4 }}>
                  状态: 正常在线 (Env: {systemStatus.api.environment})
                </div>
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" bordered={false} style={{ background: '#e6f7ff' }}>
                <Statistic
                  title="PostgreSQL 响应延迟"
                  value={systemStatus.database.latency_ms}
                  suffix="ms"
                  prefix={<DatabaseOutlined style={{ color: '#1890ff' }} />}
                />
                <div style={{ fontSize: 12, color: '#1890ff', marginTop: 4 }}>
                  数据库连接池状态健康
                </div>
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" bordered={false} style={{ background: '#f9f0ff' }}>
                <Statistic
                  title="受控邮件存储"
                  value={formatFileSize(systemStatus.storage.size_bytes)}
                  prefix={<FolderOpenOutlined style={{ color: '#722ed1' }} />}
                />
                <div style={{ fontSize: 12, color: '#722ed1', marginTop: 4 }}>
                  已归档文件数: {systemStatus.storage.file_count} 个
                </div>
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" bordered={false} style={{ background: '#fffbe6' }}>
                <Statistic
                  title="活跃邮箱 / 调度任务"
                  value={`${systemStatus.mailboxes.active}/${systemStatus.mailboxes.total}`}
                  prefix={<SafetyCertificateOutlined style={{ color: '#faad14' }} />}
                />
                <div style={{ fontSize: 12, color: '#faad14', marginTop: 4 }}>
                  执行中任务: {systemStatus.jobs.active}，失败: {systemStatus.jobs.failed}
                </div>
              </Card>
            </Col>
          </Row>
        ) : (
          <Text type="secondary">正在加载健康探针...</Text>
        )}
      </Card>

      {/* 审计日志审计事件流 */}
      <Card
        title={
          <Space>
            <SafetyCertificateOutlined />
            <span>系统安全审计流水 (不可变记录)</span>
          </Space>
        }
        extra={
          <Space>
            <Input
              placeholder="按动作过滤 (例如: login)"
              style={{ width: 180 }}
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              onPressEnter={() => {
                setPage(1);
                fetchAudit();
              }}
              allowClear
            />
            <Input
              placeholder="按操作者过滤"
              style={{ width: 150 }}
              value={actorFilter}
              onChange={(e) => setActorFilter(e.target.value)}
              onPressEnter={() => {
                setPage(1);
                fetchAudit();
              }}
              allowClear
            />
            <Button
              type="primary"
              onClick={() => {
                setPage(1);
                fetchAudit();
              }}
            >
              查询
            </Button>
          </Space>
        }
      >
        <Table
          rowKey="id"
          columns={columns}
          dataSource={logs}
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

      {/* 审计日志完整明细弹窗 */}
      <Modal
        title="审计事件完整记录"
        open={detailModalVisible}
        onCancel={() => {
          setDetailModalVisible(false);
          setSelectedLog(null);
        }}
        footer={[
          <Button key="close" onClick={() => setDetailModalVisible(false)}>
            关闭
          </Button>,
        ]}
        width={600}
      >
        {selectedLog && (
          <div>
            <Paragraph>
              <Text strong>事件 ID: </Text>
              <Text code>{selectedLog.id}</Text>
            </Paragraph>
            <Paragraph>
              <Text strong>操作者: </Text>
              <Tag color="blue">{selectedLog.actor}</Tag>
              <Text strong style={{ marginLeft: 16 }}>
                动作:
              </Text>
              <Text code>{selectedLog.action}</Text>
            </Paragraph>
            <Paragraph>
              <Text strong>目标: </Text>
              <Text code>{selectedLog.target || '无'}</Text>
            </Paragraph>
            <Paragraph>
              <Text strong>发生时间: </Text>
              {new Date(selectedLog.created_at).toLocaleString()}
            </Paragraph>
            <Divider orientation="left" style={{ margin: '12px 0' }}>
              载荷详情 Payload (脱敏后)
            </Divider>
            <pre
              style={{
                background: '#f5f5f5',
                padding: 12,
                borderRadius: 4,
                fontSize: 12,
                maxHeight: 260,
                overflowY: 'auto',
              }}
            >
              {JSON.stringify(selectedLog.detail, null, 2)}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  );
};
