import axios, { AxiosError, AxiosRequestConfig } from 'axios';
import { message } from 'antd';

export const apiClient = axios.create({
  baseURL: '/v1',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

let reauthCallback: (() => Promise<boolean>) | null = null;

export function registerReauthHandler(handler: () => Promise<boolean>) {
  reauthCallback = handler;
}

// Request interceptor: attach CSRF token if present in sessionStorage
apiClient.interceptors.request.use((config) => {
  const csrfToken = sessionStorage.getItem('cardcue_csrf');
  if (csrfToken && config.headers) {
    config.headers['x-csrf-token'] = csrfToken;
  }
  return config;
});

// Response interceptor: handle 401, 403, and extract error messages
apiClient.interceptors.response.use(
  (response) => {
    // If response returns a csrf_token, keep it updated
    if (response.data && response.data.csrf_token) {
      sessionStorage.setItem('cardcue_csrf', response.data.csrf_token);
    }
    return response;
  },
  async (error: AxiosError<any>) => {
    if (error.response) {
      const { status, data } = error.response;
      const errorMsg = data?.detail || data?.message || error.message || '请求处理失败';

      if (status === 401) {
        sessionStorage.removeItem('cardcue_csrf');
        sessionStorage.removeItem('cardcue_user');
        if (window.location.pathname !== '/login') {
          message.warning('登录会话已过期，请重新登录');
          window.location.href = '/login';
        }
      } else if (status === 403) {
        if (typeof errorMsg === 'string' && errorMsg.includes('重新验证密码') && reauthCallback) {
          const ok = await reauthCallback();
          if (ok && error.config) {
            return apiClient.request(error.config);
          }
        }
        message.error(typeof errorMsg === 'string' ? errorMsg : '权限受限或安全校验失败');
      } else if (status === 429) {
        message.error(typeof errorMsg === 'string' ? errorMsg : '请求过于频繁，请稍后再试');
      } else {
        message.error(typeof errorMsg === 'string' ? errorMsg : '操作失败，请重试');
      }
    } else {
      message.error('网络通信异常，请检查网络或后端服务连接');
    }
    return Promise.reject(error);
  }
);
