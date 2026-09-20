import React, { useEffect, useState } from 'react';
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
} from '@ant-design/icons';
import { systemApi, authApi } from '../api';
import { DeviceItem } from '../types';

const { Text, Title, Paragraph } = Typography;
const { Countdown } = Statistic;

export const Devices: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [pairingModalVisible, setPairingModalVisible] = useState(false);
  const [pairingLoading, setPairingLoading] = useState(false);
  const [pairingCode, setPairingCode] = useState<string>('');
  const [deadline, setDeadline] = useState<number>(0);

  const fetchDevices = async () => {
    setLoading(true);
    try {
      const res = await systemApi.listDevices();
      setDevices(res.data || []);
    } catch (_) {
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

  const columns = [
    {
      title: '设备名称 / 标识',
      key: 'name',
      render: (_: any, d: DeviceItem) => (
        <div>
          <Space>
            <MobileOutlined style={{ fontSize: 16, color: '#1890ff' }} />
            <Text strong>{d.device_name || 'CardCue 移动端'}</Text>
          </Space>
          <div style={{ fontSize: 12, color: '#8c8c8c' }}>{d.id}</div>
        </div>
      ),
    },
    {
      title: '设备型号 / 系统',
      dataIndex: 'device_model',
      key: 'device_model',
      render: (m: string) => m || 'Android Device',
    },
    {
      title: '授权状态',
      key: 'status',
      width: 120,
      render: (_: any, d: DeviceItem) =>
        d.is_active ? (
          <Tag color="success">已授权</Tag>
        ) : (
          <Tag color="error">已吊销</Tag>
        ),
    },
    {
      title: '最近数据同步时间',
      dataIndex: 'last_sync_at',
      key: 'last_sync_at',
      render: (t: string | null) => (t ? new Date(t).toLocaleString() : '尚未同步'),
    },
    {
      title: '首次授权绑定时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (t: string) => new Date(t).toLocaleString(),
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_: any, d: DeviceItem) =>
        d.is_active && (
          <Popconfirm
            title="确定吊销该设备的访问授权吗？"
            description="吊销后该设备将无法通过 API 同步账单与数据"
            onConfirm={() => handleRevokeDevice(d.id)}
          >
            <Button size="small" danger icon={<StopOutlined />}>
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
          <Button
            type="primary"
            icon={<KeyOutlined />}
            onClick={handleCreatePairingCode}
            loading={pairingLoading}
          >
            生成 Android 设备配对码
          </Button>
        }
      >
        <Alert
          type="info"
          showIcon
          message="公网安全接入机制"
          description="CardCue 手机端初次连接 VPS 服务端时，必须使用在此生成的 10 分钟一次性高强度配对码进行双向握手与密钥交换。握手成功后自动生成专属设备长期密钥凭据，杜绝未授权设备公网探测与越权。"
          style={{ marginBottom: 16 }}
        />
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
