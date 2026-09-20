import React, { useState, useEffect } from 'react';
import { Layout, Menu, Button, Typography, Space, Dropdown, Avatar, Modal, Form, Input, message } from 'antd';
import {
  DashboardOutlined,
  CreditCardOutlined,
  FileTextOutlined,
  AuditOutlined,
  MailOutlined,
  SettingOutlined,
  RobotOutlined,
  UnorderedListOutlined,
  MobileOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
  LogoutOutlined,
  KeyOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { authApi, draftsApi } from '../api';
import { ReauthModal } from './ReauthModal';

const { Header, Content, Sider } = Layout;
const { Text } = Typography;

export const AppLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [username, setUsername] = useState<string>('Admin');
  const [pendingDrafts, setPendingDrafts] = useState<number>(0);
  const [pwdModalOpen, setPwdModalOpen] = useState<boolean>(false);
  const [pwdLoading, setPwdLoading] = useState<boolean>(false);
  const [pwdForm] = Form.useForm();

  useEffect(() => {
    const cachedUser = sessionStorage.getItem('cardcue_user');
    if (cachedUser) {
      setUsername(cachedUser);
    }
    // Fetch pending drafts count for badge
    draftsApi.listDrafts({ status: 'pending', size: 1 }).then((res) => {
      if (res.data && typeof res.data.total === 'number') {
        setPendingDrafts(res.data.total);
      }
    }).catch(() => {});
  }, [location.pathname]);

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch (_) {}
    sessionStorage.removeItem('cardcue_csrf');
    sessionStorage.removeItem('cardcue_user');
    message.success('已安全退出登录');
    navigate('/login');
  };

  const handleChangePassword = async () => {
    try {
      const values = await pwdForm.validateFields();
      setPwdLoading(true);
      await authApi.changePassword({ new_password: values.new_password });
      message.success('密码修改成功，所有活跃会话已失效，请重新登录');
      setPwdModalOpen(false);
      sessionStorage.clear();
      navigate('/login');
    } catch (err) {
    } finally {
      setPwdLoading(false);
    }
  };

  const menuItems = [
    {
      key: '/',
      icon: <DashboardOutlined />,
      label: '总览看板',
    },
    {
      key: '/accounts',
      icon: <CreditCardOutlined />,
      label: '账户与卡片',
    },
    {
      key: '/statements',
      icon: <FileTextOutlined />,
      label: '账单与还款',
    },
    {
      key: '/drafts',
      icon: <AuditOutlined />,
      label: (
        <span>
          草稿审核
          {pendingDrafts > 0 && (
            <span
              style={{
                marginLeft: 8,
                backgroundColor: '#ff4d4f',
                color: '#fff',
                borderRadius: 10,
                padding: '0 6px',
                fontSize: 11,
              }}
            >
              {pendingDrafts}
            </span>
          )}
        </span>
      ),
    },
    {
      key: '/emails',
      icon: <MailOutlined />,
      label: '邮件中心',
    },
    {
      key: '/mailboxes',
      icon: <SettingOutlined />,
      label: '邮箱配置',
    },
    {
      key: '/models',
      icon: <RobotOutlined />,
      label: '模型配置',
    },
    {
      key: '/jobs',
      icon: <UnorderedListOutlined />,
      label: '任务队列',
    },
    {
      key: '/devices',
      icon: <MobileOutlined />,
      label: '设备安全',
    },
    {
      key: '/audit',
      icon: <SafetyCertificateOutlined />,
      label: '系统与审计',
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={(value) => setCollapsed(value)}
        theme="dark"
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
          zIndex: 100,
        }}
      >
        <div
          style={{
            height: 48,
            margin: 12,
            background: 'rgba(255, 255, 255, 0.12)',
            borderRadius: 6,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontWeight: 700,
            fontSize: collapsed ? 14 : 16,
            letterSpacing: 1,
            userSelect: 'none',
          }}
        >
          {collapsed ? 'CC' : 'CardCue Web'}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>

      <Layout style={{ marginLeft: collapsed ? 80 : 200, transition: 'margin-left 0.2s' }}>
        <Header
          style={{
            padding: '0 24px',
            background: '#fff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #f0f0f0',
            position: 'sticky',
            top: 0,
            zIndex: 99,
          }}
        >
          <Text strong style={{ fontSize: 16 }}>
            {menuItems.find((m) => m.key === location.pathname)?.label || '管理后台'}
          </Text>

          <Space size="middle">
            <Dropdown
              menu={{
                items: [
                  {
                    key: 'pwd',
                    icon: <KeyOutlined />,
                    label: '修改密码',
                    onClick: () => setPwdModalOpen(true),
                  },
                  {
                    type: 'divider',
                  },
                  {
                    key: 'logout',
                    icon: <LogoutOutlined />,
                    label: '安全退出',
                    danger: true,
                    onClick: handleLogout,
                  },
                ],
              }}
            >
              <Button type="text" style={{ display: 'flex', alignItems: 'center' }}>
                <Avatar size="small" icon={<UserOutlined />} style={{ marginRight: 8, backgroundColor: '#1890ff' }} />
                <span>{username}</span>
              </Button>
            </Dropdown>
          </Space>
        </Header>

        <Content style={{ margin: '20px', minHeight: 280 }}>
          <Outlet />
        </Content>

        <ReauthModal />

        <Modal
          title="修改管理员密码"
          open={pwdModalOpen}
          onOk={handleChangePassword}
          onCancel={() => {
            setPwdModalOpen(false);
            pwdForm.resetFields();
          }}
          confirmLoading={pwdLoading}
          okText="确认修改"
          cancelText="取消"
        >
          <Form form={pwdForm} layout="vertical">
            <Form.Item
              name="new_password"
              label="新密码（建议包含大小写字母、数字，长度不少于14位）"
              rules={[
                { required: true, message: '请输入新密码' },
                { min: 14, message: '密码长度至少需14位字符' },
              ]}
            >
              <Input.Password placeholder="输入新管理员密码" />
            </Form.Item>
          </Form>
        </Modal>
      </Layout>
    </Layout>
  );
};
