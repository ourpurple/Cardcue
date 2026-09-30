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
  Alert,
  Statistic,
  Divider,
} from 'antd';
import {
  MobileOutlined,
  KeyOutlined,
  StopOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  QrcodeOutlined,
  DeleteOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { systemApi, authApi } from '../api';
import { DeviceItem } from '../types';

const { Text, Title, Paragraph } = Typography;
const { Countdown } = Statistic;
const isRevoked = (device: DeviceItem) => device.status === 'revoked' || device.revoked_at != null;
const isActive = (device: DeviceItem) => device.status === 'active' && !isRevoked(device);
const formatDate = (value: string | null) => {
  if (!value) return '未知';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '未知' : date.toLocaleString();
};

export const Devices: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [clearing, setClearing] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const clearingRef = useRef(false);
  const revokedCount = devices.filter(isRevoked).length;
  const [pairingModalVisible, setPairingModalVisible] = useState(false);
  const [pairingLoading, setPairingLoading] = useState(false);
  const [pairingCode, setPairingCode] = useState<string>('');
  const [deadline, setDeadline] = useState<number>(0);

  const fetchDevices = async () => {
    setLoading(true);
    try {
      const res = await systemApi.listDevices();
      setDevices(res.data || []);
      setLoadFailed(false);
    } catch (_) {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDevices();
  }, []);

  const handleCreatePairingCode = async () => {
    setPairingLoading(true);
    try {
      const res = await authApi.createPairingCode();
      const code = res.data.code;
      const expiresInSec = res.data.expires_in_seconds || 600;
      setPairingCode(code);
      setDeadline(Date.now() + expiresInSec * 1000);
      setPairingModalVisible(true);
    } catch (_) {
    } finally {
      setPairingLoading(false);
    }
  };

  const handleRevokeDevice = async (id: string) => {
    try {
      await systemApi.revokeDevice(id);
      message.success('已撤销该移动设备的授权访问');
      fetchDevices();
    } catch (_) {}
  };

  const handleClearRevokedDevices = async () => {
    if (clearingRef.current || loading || loadFailed || revokedCount === 0) return;
    clearingRef.current = true;
    setClearing(true);
    try {
      const res = await systemApi.clearRevokedDevices();
      message.success(res.data.deleted_count > 0
        ? `已清除 ${res.data.deleted_count} 台已吊销设备`
        : '没有需要清除的已吊销设备');
      await fetchDevices();
    } catch (_) {
      // Shared API handler displays errors; keep the current list on failure.
    } finally {
      clearingRef.current = false;
      setClearing(false);
    }
  };

  const columns = [
    {
      title: '设备名称 / 标识',
      key: 'name',
      render: (_: any, d: DeviceItem) => (
        <div>
          <Space>
            <MobileOutlined style={{ fontSize: 16, color: '#1890ff' }} />
            <Text strong>{d.name || 'CardCue 移动端'}</Text>
          </Space>
          <div style={{ fontSize: 12, color: '#8c8c8c' }}>{d.id}</div>
        </div>
      ),
    },
    {
      title: '设备型号 / 系统',
      key: 'device_model',
      render: () => '未提供',
    },
    {
      title: '授权状态',
      key: 'status',
      width: 120,
      render: (_: any, d: DeviceItem) =>
        isRevoked(d) ? (
          <Tag color="error">已吊销</Tag>
        ) : isActive(d) ? (
          <Tag color="success">已授权</Tag>
        ) : (
          <Tag>未知状态</Tag>
        ),
    },
    {
      title: '最近访问时间',
      dataIndex: 'last_seen_at',
      key: 'last_seen_at',
      render: (t: string | null) => (t ? formatDate(t) : '尚未访问'),
    },
    {
      title: '首次授权绑定时间',
      dataIndex: 'paired_at',
      key: 'paired_at',
      render: formatDate,
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_: any, d: DeviceItem) =>
        isActive(d) && (
          <Popconfirm
            disabled={clearing || loading}
            title="确定吊销该设备的访问授权吗？"
            description="吊销后该设备将无法通过 API 同步账单与数据"
            onConfirm={() => handleRevokeDevice(d.id)}
          >
            <Button size="small" danger icon={<StopOutlined />} disabled={clearing || loading}>
              吊销授权
            </Button>
          </Popconfirm>
        ),
    },
  ];

  return (
    <div>
      <Card
        title={
          <Space>
            <MobileOutlined />
            <span>移动端设备与配对安全</span>
          </Space>
        }
        extra={
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={fetchDevices} disabled={loading || clearing}>
              刷新设备
            </Button>
            <Popconfirm
              title="确定清除所有已吊销设备吗？"
              description="仅删除已吊销设备记录，不影响已授权设备、账单和还款记录；已有审计记录保留。此操作不可撤销。"
              okText="清除已吊销设备"
              cancelText="取消"
              okButtonProps={{ danger: true, loading: clearing }}
              onConfirm={handleClearRevokedDevices}
              disabled={loading || loadFailed || clearing || revokedCount === 0}
            >
              <Button danger icon={<DeleteOutlined />} loading={clearing}
                disabled={loading || loadFailed || clearing || revokedCount === 0}>
                清除已吊销设备{revokedCount > 0 ? `（${revokedCount}）` : ''}
              </Button>
            </Popconfirm>
            <Button
              type="primary"
              icon={<KeyOutlined />}
              onClick={handleCreatePairingCode}
              loading={pairingLoading}
            >
              生成 Android 设备配对码
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          message="公网安全接入机制"
          description="CardCue 手机端初次连接 VPS 服务端时，必须使用在此生成的 10 分钟一次性高强度配对码进行双向握手与密钥交换。握手成功后自动生成专属设备长期密钥凭据，杜绝未授权设备公网探测与越权。"
          style={{ marginBottom: 16 }}
        />
        {loadFailed && (
          <Alert type="warning" showIcon message="设备列表加载失败，请刷新后再清理" style={{ marginBottom: 16 }} />
        )}
        <Table
          rowKey="id"
          columns={columns}
          dataSource={devices}
          loading={loading}
          pagination={false}
        />
      </Card>

      {/* 配对码展示弹窗 */}
      <Modal
        title="Android 客户端一次性配对码"
        open={pairingModalVisible}
        onCancel={() => setPairingModalVisible(false)}
        footer={[
          <Button key="close" type="primary" onClick={() => setPairingModalVisible(false)}>
            已完成配对
          </Button>,
        ]}
        width={540}
      >
        <div style={{ textAlign: 'center', padding: '16px 0' }}>
          <Paragraph type="secondary">
            请打开手机 CardCue Android 原生应用，在【连接云端】中填入以下配对码完成互信认证：
          </Paragraph>

          <div
            style={{
              background: '#f6ffed',
              border: '1px solid #b7eb8f',
              padding: '16px 24px',
              borderRadius: 8,
              margin: '20px auto',
              display: 'inline-block',
            }}
          >
            <Text
              copyable
              style={{
                fontSize: 22,
                fontFamily: 'monospace',
                fontWeight: 700,
                letterSpacing: 2,
                color: '#52c41a',
              }}
            >
              {pairingCode}
            </Text>
          </div>

          <div style={{ margin: '12px 0' }}>
            <Countdown
              title="配对码有效倒计时 (10分钟)"
              value={deadline}
              onFinish={() => message.warning('配对码已过期，请重新生成')}
            />
          </div>

          <Paragraph type="secondary" style={{ fontSize: 12 }}>
            注：该配对码为一次性凭据，仅允许绑定单台设备；倒计时结束后自动作废。
          </Paragraph>
        </div>
      </Modal>
    </div>
  );
};
