import React, { useEffect, useRef, useState } from 'react';
import {
  Table,
  Button,
  Space,
  Tag,
  Modal,
  Typography,
  message,
  Card,
  Popconfirm,
  Badge,
  Descriptions,
} from 'antd';
import {
  UnorderedListOutlined,
  SyncOutlined,
  StopOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { jobsApi } from '../api';
import { AdminJobItem } from '../types';

const { Text, Paragraph } = Typography;

export const Jobs: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [clearing, setClearing] = useState(false);
  const fetchSequence = useRef(0);
  const [jobs, setJobs] = useState<AdminJobItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // Detail Modal
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedJob, setSelectedJob] = useState<AdminJobItem | null>(null);

  const fetchJobs = async () => {
    const sequence = ++fetchSequence.current;
    setLoading(true);
    try {
      const res = await jobsApi.listJobs({ page, size: pageSize });
      if (sequence === fetchSequence.current) {
        setJobs(res.data?.items || []);
        setTotal(res.data?.total || 0);
      }
    } catch (_) {
    } finally {
      if (sequence === fetchSequence.current) setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, [page, pageSize]);

  const handleCancel = async (id: string) => {
    try {
      await jobsApi.cancelJob(id);
      message.success('已请求取消该任务');
      fetchJobs();
    } catch (_) {}
  };

  const handleClear = async () => {
    setClearing(true);
    try {
      const res = await jobsApi.clearJobs();
      // Ignore older list responses so deleted tasks cannot reappear locally.
      ++fetchSequence.current;
      setJobs([]);
      setTotal(0);
      setDetailModalVisible(false);
      setSelectedJob(null);
      message.success(`已清除 ${res.data.deleted_count} 个任务`);
      if (page !== 1) {
        setPage(1);
      } else {
        await fetchJobs();
      }
    } catch (_) {
      // The shared API client displays the server or network error.
    } finally {
      setClearing(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
      case 'success':
        return <Tag color="success" icon={<CheckCircleOutlined />}>成功完成</Tag>;
      case 'running':
        return <Tag color="processing" icon={<SyncOutlined spin />}>执行中</Tag>;
      case 'failed':
        return <Tag color="error" icon={<CloseCircleOutlined />}>执行失败</Tag>;
      case 'cancelled':
        return <Tag color="default">已取消</Tag>;
      case 'queued':
      case 'pending':
      default:
        return <Tag color="warning" icon={<ClockCircleOutlined />}>排队等待</Tag>;
    }
  };

  const columns = [
    {
      title: '任务 ID',
      dataIndex: 'id',
      key: 'id',
      width: 140,
      render: (id: string) => <Text code>{id.slice(0, 8)}...</Text>,
    },
    {
      title: '任务类型',
      dataIndex: 'kind',
      key: 'kind',
      width: 130,
      render: (k: string) => (
        <Tag color={k === 'sync' ? 'blue' : 'purple'}>
          {k === 'sync' ? '邮箱邮件同步' : '账单模型解析'}
        </Tag>
      ),
    },
    {
      title: '目标对象 ID',
      dataIndex: 'target_id',
      key: 'target_id',
      width: 140,
      render: (t: string) => <Text code>{t ? t.slice(0, 8) + '...' : '-'}</Text>,
    },
    {
      title: '状态',
      key: 'status',
      width: 130,
      render: (_: any, r: AdminJobItem) => getStatusBadge(r.status),
    },
    {
      title: '重试次数',
      dataIndex: 'attempts',
      key: 'attempts',
      width: 100,
      render: (a: number) => a || 0,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (t: string) => new Date(t).toLocaleString(),
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_: any, record: AdminJobItem) => (
        <Space size="small">
          <Button
            size="small"
            type="link"
            disabled={clearing}
            onClick={() => {
              setSelectedJob(record);
              setDetailModalVisible(true);
            }}
          >
            详情
          </Button>
          {(record.status === 'queued' || record.status === 'running') && (
            <Popconfirm
              title="确定取消该任务吗？"
              onConfirm={() => handleCancel(record.id)}
            >
              <Button size="small" type="text" danger disabled={clearing} icon={<StopOutlined />}>
                取消
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
            <UnorderedListOutlined />
            <span>异步任务与调度队列</span>
          </Space>
        }
        extra={
          <Space>
            <Popconfirm
              title="确定清除所有任务队列吗？"
              description={
                <div>
                  将删除所有分页中的排队任务和历史任务记录，此操作不可撤销。<br />
                  不会删除邮件、草稿、账单或还款记录。<br />
                  执行中的任务需先取消并等待结束；定时调度仍可能产生新任务。
                </div>
              }
              onConfirm={handleClear}
              okText="清除所有任务"
              cancelText="取消"
              okButtonProps={{ danger: true, loading: clearing }}
              disabled={loading || clearing || total === 0}
            >
              <Button
                danger
                icon={<DeleteOutlined />}
                loading={clearing}
                disabled={loading || total === 0}
              >
                清除所有任务
              </Button>
            </Popconfirm>
            <Button icon={<SyncOutlined />} onClick={fetchJobs} disabled={clearing}>
              刷新队列
            </Button>
          </Space>
        }
      >
        <Table
          rowKey="id"
          columns={columns}
          dataSource={jobs}
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            disabled: clearing,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
        />
      </Card>

      {/* 任务详情弹窗 */}
      <Modal
        title="任务运行详情"
        open={detailModalVisible}
        onCancel={() => {
          setDetailModalVisible(false);
          setSelectedJob(null);
        }}
        footer={[
          <Button key="close" onClick={() => setDetailModalVisible(false)}>
            关闭
          </Button>,
        ]}
        width={650}
      >
        {selectedJob && (
          <div>
            <Descriptions size="small" bordered column={1} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="任务 ID">
                <Text code copyable>{selectedJob.id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="任务类型">
                <Tag>{selectedJob.kind}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="目标对象 ID">
                <Text code copyable>{selectedJob.target_id || '-'}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="当前状态">
                {getStatusBadge(selectedJob.status)}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {new Date(selectedJob.created_at).toLocaleString()}
              </Descriptions.Item>
              <Descriptions.Item label="开始执行时间">
                {selectedJob.started_at ? new Date(selectedJob.started_at).toLocaleString() : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="完成时间">
                {selectedJob.finished_at ? new Date(selectedJob.finished_at).toLocaleString() : '-'}
              </Descriptions.Item>
              {selectedJob.error_code && (
                <Descriptions.Item label="错误代码">
                  <Text type="danger">{selectedJob.error_code}</Text>
                </Descriptions.Item>
              )}
            </Descriptions>

            {selectedJob.result && (
              <div>
                <Text strong>执行结果详情:</Text>
                <pre
                  style={{
                    background: '#f5f5f5',
                    padding: 12,
                    borderRadius: 4,
                    marginTop: 6,
                    fontSize: 12,
                    maxHeight: 220,
                    overflowY: 'auto',
                  }}
                >
                  {JSON.stringify(selectedJob.result, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};
