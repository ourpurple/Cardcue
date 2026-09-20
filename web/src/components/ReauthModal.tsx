import React, { useState, useEffect } from 'react';
import { Modal, Form, Input, message } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { authApi } from '../api';
import { registerReauthHandler } from '../api/client';

export const ReauthModal: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();
  const [resolver, setResolver] = useState<((val: boolean) => void) | null>(null);

  useEffect(() => {
    registerReauthHandler(() => {
      return new Promise<boolean>((resolve) => {
        setResolver(() => resolve);
        setOpen(true);
      });
    });
  }, []);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      await authApi.verifyPassword(values.password);
      message.success('身份重新验证成功');
      setOpen(false);
      form.resetFields();
      if (resolver) resolver(true);
    } catch (err: any) {
      if (resolver) resolver(false);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    setOpen(false);
    form.resetFields();
    if (resolver) resolver(false);
  };

  return (
    <Modal
      title="安全敏感操作 - 请重新验证管理员密码"
      open={open}
      onOk={handleOk}
      onCancel={handleCancel}
      confirmLoading={loading}
      okText="验证密码"
      cancelText="取消"
      destroyOnClose
    >
      <p style={{ color: '#666', fontSize: 13, marginBottom: 16 }}>
        您正在执行关键配置或凭据操作，为保障系统公网安全性，请输入当前管理员密码进行二次确认（10分钟内有效）。
      </p>
      <Form form={form} layout="vertical">
        <Form.Item
          name="password"
          label="管理员密码"
          rules={[{ required: true, message: '请输入管理员密码' }]}
        >
          <Input.Password
            prefix={<LockOutlined />}
            placeholder="请输入管理员密码"
            autoFocus
            onPressEnter={handleOk}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
};
