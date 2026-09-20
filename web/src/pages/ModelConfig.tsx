import React, { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  InputNumber,
  Switch,
  Typography,
  message,
  Card,
  Drawer,
  Popconfirm,
  Alert,
  Divider,
  Descriptions,
} from 'antd';
import {
  RobotOutlined,
  PlusOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  HistoryOutlined,
  StopOutlined,
  StarOutlined,
  StarFilled,
  DeleteOutlined,
} from '@ant-design/icons';
import { modelApi } from '../api';
import { ModelProfileItem, ModelRevisionItem } from '../types';

const { Text, Paragraph, Title } = Typography;

export const ModelConfig: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [profiles, setProfiles] = useState<ModelProfileItem[]>([]);
  const [modalVisible, setModalVisible] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [editingProfile, setEditingProfile] = useState<ModelProfileItem | null>(null);
  const [form] = Form.useForm();

  // Revisions drawer
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [currentProfile, setCurrentProfile] = useState<ModelProfileItem | null>(null);

  // Test modal
  const [testModalVisible, setTestModalVisible] = useState(false);
  const [testingRevision, setTestingRevision] = useState<ModelRevisionItem | null>(null);
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);

  const fetchModels = async () => {
    setLoading(true);
    try {
      const res = await modelApi.listModels();
      setProfiles(res.data || []);
      // If drawer is open, keep current profile updated
      if (currentProfile) {
        const found = (res.data || []).find((p: ModelProfileItem) => p.id === currentProfile.id);
        if (found) setCurrentProfile(found);
      }
    } catch (_) {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchModels();
  }, []);

  const openAddModal = () => {
    setEditingProfile(null);
    form.resetFields();
    form.setFieldsValue({
      name: 'OpenAI 兼容模型',
      base_url: 'https://api.openai.com/v1',
      model: 'gpt-4o-mini',
      temperature: 0,
      max_tokens: 4096,
      timeout_seconds: 45,
      max_retries: 1,
      input_limit: 24000,
      json_mode: true,
      daily_limit: 100,
    });
    setModalVisible(true);
  };

  const openNewRevisionModal = (p: ModelProfileItem) => {
    setEditingProfile(p);
    form.resetFields();
    const latest = p.revisions && p.revisions.length > 0 ? p.revisions[0] : null;
    form.setFieldsValue({
      name: p.name,
      base_url: latest?.parameters?.base_url || 'https://api.openai.com/v1',
      model: latest?.parameters?.model || 'gpt-4o-mini',
      api_key: '',
      temperature: latest?.parameters?.temperature ?? 0,
      max_tokens: latest?.parameters?.max_tokens ?? 4096,
      timeout_seconds: latest?.parameters?.timeout_seconds ?? 45,
      max_retries: latest?.parameters?.max_retries ?? 1,
      input_limit: latest?.parameters?.input_limit ?? 24000,
      json_mode: latest?.parameters?.json_mode ?? true,
      daily_limit: latest?.parameters?.daily_limit ?? 100,
    });
    setModalVisible(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setModalLoading(true);

      const payload: any = {
        name: values.name,
        base_url: values.base_url.trim().replace(/\/+$/, ''),
        model: values.model.trim(),
        temperature: values.temperature,
        max_tokens: values.max_tokens,
        timeout_seconds: values.timeout_seconds,
        max_retries: values.max_retries,
        input_limit: values.input_limit,
        json_mode: values.json_mode,
        daily_limit: values.daily_limit,
      };

      if (values.api_key) {
        payload.api_key = values.api_key;
      }

      if (editingProfile) {
        const latest = editingProfile.revisions[0];
        payload.expected_revision = latest ? latest.number : 1;
        await modelApi.updateModel(editingProfile.id, payload);
        message.success('新模型配置版本已保存，请先测试连接后设为默认');
      } else {
        await modelApi.createModel(payload);
        message.success('模型配置创建成功，请测试连接后激活');
      }

      setModalVisible(false);
      fetchModels();
    } catch (_) {
    } finally {
      setModalLoading(false);
    }
  };

  const handleTestRevision = async (rev: ModelRevisionItem, sample: boolean = false) => {
    setTestingRevision(rev);
    setTestResult(null);
    setTestModalVisible(true);
    setTestLoading(true);
    try {
      const res = await modelApi.testRevision(rev.id, sample);
      setTestResult(res.data);
      message.success('模型连通性测试通过！');
      fetchModels();
    } catch (err: any) {
      setTestResult({
        error: true,
        message: err?.response?.data?.detail || '测试失败，请检查 Base URL、API Key 与模型支持状态',
      });
    } finally {
      setTestLoading(false);
    }
  };

  const handleDeleteProfile = async (p: ModelProfileItem) => {
    try {
      await modelApi.deleteModel(p.id);
      message.success(`模型配置方案【${p.name}】已成功删除`);
      fetchModels();
    } catch (err: any) {
      const msg = err.response?.data?.detail || '删除失败，请重试';
      message.error(msg);
    }
  };

  const handleActivate = async (revId: string) => {
    try {
      await modelApi.activateRevision(revId);
      message.success('已设为全局默认活跃解析模型！');
      fetchModels();
    } catch (_) {}
  };

  const handleRevoke = async (revId: string) => {
    try {
      await modelApi.revokeRevision(revId);
      message.success('配置版本已撤销');
      fetchModels();
    } catch (_) {}
  };

  const columns = [
    {
      title: '配置方案名称',
      key: 'name',
      render: (_: any, p: ModelProfileItem) => {
        const hasActive = p.revisions.some((r) => r.active);
        return (
          <Space>
            <Text strong>{p.name}</Text>
            {hasActive && (
              <Tag color="gold" icon={<StarFilled />}>
                全局默认模型
              </Tag>
            )}
          </Space>
        );
      },
    },
    {
      title: '当前版本信息',
      key: 'current',
      render: (_: any, p: ModelProfileItem) => {
        const activeRev = p.revisions.find((r) => r.active) || p.revisions[0];
        if (!activeRev) return <Text type="secondary">无版本记录</Text>;
        return (
          <div>
            <div>
              <Text code strong>{activeRev.parameters.model}</Text>
              <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                v{activeRev.number}
              </Text>
            </div>
            <div style={{ fontSize: 12, color: '#8c8c8c' }}>
              URL: {activeRev.parameters.base_url}
            </div>
          </div>
        );
      },
    },
    {
      title: '版本总数',
      key: 'revisions_count',
      width: 100,
      render: (_: any, p: ModelProfileItem) => <Tag>{p.revisions.length} 个版本</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 350,
      render: (_: any, p: ModelProfileItem) => {
        const activeRev = p.revisions.find((r) => r.active) || p.revisions[0];
        const hasActive = p.revisions.some((r) => r.active);
        return (
          <Space size="small">
            <Button size="small" icon={<PlusOutlined />} onClick={() => openNewRevisionModal(p)}>
              新版本
            </Button>
            <Button
              size="small"
              icon={<HistoryOutlined />}
              onClick={() => {
                setCurrentProfile(p);
                setDrawerVisible(true);
              }}
            >
              版本列表
            </Button>
            {activeRev && (
              <Button
                size="small"
                icon={<ThunderboltOutlined />}
                onClick={() => handleTestRevision(activeRev, false)}
              >
                连通测试
              </Button>
            )}
            {hasActive ? (
              <Popconfirm
                title="无法删除激活的模型方案"
                description="该方案当前处于全局激活状态。请先在其他方案中激活一个版本后再删除本方案。"
                okText="知道了"
                showCancel={false}
              >
                <Button size="small" danger disabled icon={<DeleteOutlined />}>
                  删除
                </Button>
              </Popconfirm>
            ) : (
              <Popconfirm
                title="确定删除此模型方案吗？"
                description="删除后该方案及其所有历史版本将被永久移除，此操作不可撤销。"
                okText="确认删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
                onConfirm={() => handleDeleteProfile(p)}
              >
                <Button size="small" danger icon={<DeleteOutlined />}>
                  删除
                </Button>
              </Popconfirm>
            )}
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      <Card
        title={
          <Space>
            <RobotOutlined />
            <span>大语言模型服务配置</span>
          </Space>
        }
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openAddModal}>
            新增模型方案
          </Button>
        }
      >
        <Alert
          type="info"
          showIcon
          message="多配置与单默认模型架构"
          description="系统支持保存多个大模型提供商配置方案并进行版本历史追踪，但同一时刻始终指定唯一一个默认模型版本用于账单结构化推理。所有 API 密钥均在后台安全加密存储。"
          style={{ marginBottom: 16 }}
        />
        <Table
          rowKey="id"
          columns={columns}
          dataSource={profiles}
          loading={loading}
          pagination={false}
        />
      </Card>

      {/* 新增/新版本模态框 */}
      <Modal
        title={editingProfile ? `为【${editingProfile.name}】添加新配置版本` : '新增大模型服务方案'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        confirmLoading={modalLoading}
        width={650}
        okText="保存配置版本"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="配置方案名称"
            rules={[{ required: true, message: '请输入方案名称' }]}
          >
            <Input placeholder="例如: OpenAI 主力方案 / DeepSeek 备用方案" />
          </Form.Item>

          <Form.Item
            name="base_url"
            label="API Base URL (OpenAI 兼容接口地址)"
            rules={[{ required: true, message: '请输入 Base URL' }]}
          >
            <Input placeholder="https://api.openai.com/v1 或兼容中转地址" />
          </Form.Item>

          <Form.Item
            name="model"
            label="模型识别名称 (Model Name)"
            rules={[{ required: true, message: '请输入 Model Name' }]}
          >
            <Input placeholder="gpt-4o-mini / deepseek-chat / qwen-plus 等" />
          </Form.Item>

          <Form.Item
            name="api_key"
            label={editingProfile ? 'API Key 密钥 (留空则沿用上一版本密钥)' : 'API Key 密钥 (必填)'}
            rules={editingProfile ? [] : [{ required: true, message: '请输入 API 密钥' }]}
          >
            <Input.Password placeholder="sk-..." />
          </Form.Item>

          <Divider orientation="left" style={{ margin: '16px 0' }}>
            推理超参数
          </Divider>

          <Space style={{ display: 'flex', width: '100%' }} size="large">
            <Form.Item
              name="temperature"
              label="Temperature (建议 0 保证账单稳定)"
              rules={[{ required: true }]}
              style={{ flex: 1 }}
            >
              <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} />
            </Form.Item>

            <Form.Item
              name="max_tokens"
              label="Max Tokens"
              rules={[{ required: true }]}
              style={{ flex: 1 }}
            >
              <InputNumber min={256} max={16384} style={{ width: '100%' }} />
            </Form.Item>

            <Form.Item
              name="timeout_seconds"
              label="超时秒数"
              rules={[{ required: true }]}
              style={{ flex: 1 }}
            >
              <InputNumber min={5} max={120} style={{ width: '100%' }} />
            </Form.Item>
          </Space>

          <Space style={{ display: 'flex', width: '100%' }} size="large">
            <Form.Item
              name="daily_limit"
              label="每日调用上限"
              rules={[{ required: true }]}
              style={{ flex: 1 }}
            >
              <InputNumber min={1} max={5000} style={{ width: '100%' }} />
            </Form.Item>

            <Form.Item
              name="json_mode"
              label="开启 JSON 模式"
              valuePropName="checked"
              style={{ flex: 1 }}
            >
              <Switch checkedChildren="开" unCheckedChildren="关" />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      {/* 版本历史抽屉 */}
      <Drawer
        title={currentProfile ? `【${currentProfile.name}】版本历史追踪` : '版本历史'}
        placement="right"
        width={720}
        open={drawerVisible}
        onClose={() => {
          setDrawerVisible(false);
          setCurrentProfile(null);
        }}
      >
        {currentProfile && (
          <div>
            <Table
              size="small"
              rowKey="id"
              pagination={false}
              dataSource={currentProfile.revisions}
              columns={[
                {
                  title: '版本号',
                  dataIndex: 'number',
                  key: 'number',
                  width: 80,
                  render: (n: number) => <Text strong>v{n}</Text>,
                },
                {
                  title: '模型与接口',
                  key: 'model',
                  render: (_: any, r: ModelRevisionItem) => (
                    <div>
                      <Text code>{r.parameters.model}</Text>
                      <div style={{ fontSize: 12, color: '#8c8c8c' }}>{r.parameters.base_url}</div>
                    </div>
                  ),
                },
                {
                  title: '测试状态',
                  key: 'tested',
                  width: 120,
                  render: (_: any, r: ModelRevisionItem) => {
                    if (r.revoked) return <Tag color="error">已撤销</Tag>;
                    if (r.tested_at) return <Tag color="success">已测试通过</Tag>;
                    return <Tag color="default">未测试</Tag>;
                  },
                },
                {
                  title: '当前生效',
                  key: 'active',
                  width: 110,
                  render: (_: any, r: ModelRevisionItem) => {
                    if (r.active) {
                      return <Tag color="gold"><StarFilled /> 默认</Tag>;
                    }
                    return null;
                  },
                },
                {
                  title: '操作',
                  key: 'actions',
                  width: 220,
                  render: (_: any, r: ModelRevisionItem) => (
                    <Space size="small">
                      <Button
                        size="small"
                        icon={<ThunderboltOutlined />}
                        disabled={r.revoked}
                        onClick={() => handleTestRevision(r, false)}
                      >
                        测试
                      </Button>
                      {!r.active && !r.revoked && (
                        <Button
                          size="small"
                          type="primary"
                          disabled={!r.tested_at}
                          onClick={() => handleActivate(r.id)}
                        >
                          设为默认
                        </Button>
                      )}
                      {!r.revoked && (
                        <Popconfirm
                          title="确认撤销此版本吗？"
                          description="撤销后该版本将无法再被选为默认模型"
                          onConfirm={() => handleRevoke(r.id)}
                        >
                          <Button size="small" danger icon={<StopOutlined />} />
                        </Popconfirm>
                      )}
                    </Space>
                  ),
                },
              ]}
            />
          </div>
        )}
      </Drawer>

      {/* 连通性测试结果弹窗 */}
      <Modal
        title="模型连通性与提取测试"
        open={testModalVisible}
        onCancel={() => setTestModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setTestModalVisible(false)}>
            关闭
          </Button>,
          <Button
            key="test_sample"
            type="primary"
            loading={testLoading}
            onClick={() => testingRevision && handleTestRevision(testingRevision, true)}
          >
            使用虚拟模拟账单进行结构化提取测试
          </Button>,
        ]}
        width={600}
      >
        {testingRevision && (
          <div>
            <Paragraph>
              正在测试模型版本 <Text strong>v{testingRevision.number}</Text> (
              <Text code>{testingRevision.parameters.model}</Text>) 连通性。
            </Paragraph>

            {testLoading && <Paragraph type="secondary">正在向模型服务发起测试请求，请稍候...</Paragraph>}

            {testResult && (
              <div>
                {testResult.error ? (
                  <Alert
                    type="error"
                    showIcon
                    message="测试失败"
                    description={testResult.message}
                  />
                ) : (
                  <div>
                    <Alert
                      type="success"
                      showIcon
                      message="测试成功！模型服务响应正常"
                      style={{ marginBottom: 12 }}
                    />
                    {testResult.usage && (
                      <Descriptions size="small" bordered column={2} style={{ marginBottom: 12 }}>
                        <Descriptions.Item label="Prompt Tokens">
                          {testResult.usage.prompt_tokens || '-'}
                        </Descriptions.Item>
                        <Descriptions.Item label="Completion Tokens">
                          {testResult.usage.completion_tokens || '-'}
                        </Descriptions.Item>
                      </Descriptions>
                    )}
                    {testResult.sample && (
                      <div>
                        <Text strong>模拟账单抽取结果:</Text>
                        <pre
                          style={{
                            background: '#f5f5f5',
                            padding: 12,
                            borderRadius: 4,
                            marginTop: 6,
                            fontSize: 12,
                            maxHeight: 200,
                            overflowY: 'auto',
                          }}
                        >
                          {JSON.stringify(testResult.sample, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};
