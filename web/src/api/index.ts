import { apiClient } from './client';

// 1. Auth API
export const authApi = {
  login: (data: { username: string; password: string }) =>
    apiClient.post('/admin/auth/login', data),
  logout: () => apiClient.post('/admin/auth/logout'),
  getSession: () => apiClient.get('/admin/auth/session'),
  verifyPassword: (password: string) =>
    apiClient.post('/admin/auth/verify', { password }),
  changePassword: (data: { current_password?: string; new_password: string }) =>
    apiClient.post('/admin/auth/password', data),
  createPairingCode: () => apiClient.post('/admin/auth/pairing-codes'),
};

// 2. Overview API
export const overviewApi = {
  getOverview: () => apiClient.get('/admin/overview'),
};

// 3. Accounts & Cards API
export const accountsApi = {
  listAccounts: () => apiClient.get('/admin/accounts'),
  createAccount: (data: any) => apiClient.post('/admin/accounts', data),
  updateAccount: (id: string, data: any) => apiClient.put(`/admin/accounts/${id}`, data),
  deleteAccount: (id: string) => apiClient.delete(`/admin/accounts/${id}`),
  listCards: (accountId?: string) =>
    accountId
      ? apiClient.get(`/admin/accounts/${accountId}/cards`)
      : apiClient.get('/admin/cards'),
  createCard: (data: any) => apiClient.post('/admin/cards', data),
  updateCard: (id: string, data: any) => apiClient.put(`/admin/cards/${id}`, data),
  deleteCard: (id: string) => apiClient.delete(`/admin/cards/${id}`),
};

// 4. Statements & Payments API
export const statementsApi = {
  listStatements: (params?: any) => apiClient.get('/admin/statements', { params }),
  getStatement: (id: string) => apiClient.get(`/admin/statements/${id}`),
  correctStatement: (id: string, data: any) =>
    apiClient.post(`/admin/statements/${id}/correct`, data),
  recordPayment: (id: string, data: any) =>
    apiClient.post(`/admin/statements/${id}/payments`, data),
  revokePayment: (paymentId: string, reason: string) =>
    apiClient.post(`/admin/payments/${paymentId}/revoke`, { reason }),
  deleteStatement: (id: string) =>
    apiClient.delete(`/admin/statements/${id}`),
  deletePayment: (paymentId: string) =>
    apiClient.delete(`/admin/payments/${paymentId}`),
};

// 5. Emails API
export const emailsApi = {
  listEmails: (params?: any) => apiClient.get('/admin/emails', { params }),
  getEmail: (id: string) => apiClient.get(`/admin/emails/${id}`),
  actionEmail: (id: string, action: 'ignore' | 'restore') =>
    apiClient.post(`/admin/emails/${id}/action`, { action }),
  getAttachmentDownloadUrl: (attId: string) =>
    `/v1/admin/attachments/${attId}/download`,
};

// 6. Mailbox Config API
export const mailboxApi = {
  listMailboxes: () => apiClient.get('/admin/mailboxes'),
  createMailbox: (data: any) => apiClient.post('/admin/mailboxes', data),
  updateMailbox: (id: string, data: any) =>
    apiClient.put(`/admin/mailboxes/${id}`, data),
  testMailbox: (id: string, revision: number) =>
    apiClient.post(`/admin/mailboxes/${id}/test`, { expected_revision: revision }),
  enableMailbox: (id: string, revision: number) =>
    apiClient.post(`/admin/mailboxes/${id}/enable`, { expected_revision: revision }),
  disableMailbox: (id: string, revision: number) =>
    apiClient.post(`/admin/mailboxes/${id}/disable`, { expected_revision: revision }),
};

// 7. Model Config API
export const modelApi = {
  listModels: () => apiClient.get('/admin/models'),
  createModel: (data: any) => apiClient.post('/admin/models', data),
  updateModel: (id: string, data: any) =>
    apiClient.put(`/admin/models/${id}`, data),
  testRevision: (revisionId: string, sample: boolean = false) =>
    apiClient.post(`/admin/model-revisions/${revisionId}/test`, { sample }),
  activateRevision: (revisionId: string) =>
    apiClient.post(`/admin/model-revisions/${revisionId}/activate`),
  revokeRevision: (revisionId: string) =>
    apiClient.post(`/admin/model-revisions/${revisionId}/revoke`),
};

// 8. Drafts API
export const draftsApi = {
  listDrafts: (params?: any) => apiClient.get('/admin/drafts', { params }),
  getDraft: (id: string) => apiClient.get(`/admin/drafts/${id}`),
  updateDraft: (id: string, data: any) =>
    apiClient.put(`/admin/drafts/${id}`, data),
  confirmDraft: (id: string, data: any) =>
    apiClient.post(`/admin/drafts/${id}/confirm`, data),
  rejectDraft: (id: string, reason: string) =>
    apiClient.post(`/admin/drafts/${id}/reject`, { reason }),
};

// 9. Jobs API
export const jobsApi = {
  listJobs: (params?: any) => apiClient.get('/admin/jobs', { params }),
  createJob: (data: { kind: 'sync' | 'parse'; target_id: string; since_days?: number; allow_external?: boolean; force?: boolean }) =>
    apiClient.post('/admin/jobs', data),
  cancelJob: (id: string) => apiClient.post(`/admin/jobs/${id}/cancel`),
};

// 10. Devices, Audit & Status API
export const systemApi = {
  listDevices: () => apiClient.get('/admin/devices'),
  revokeDevice: (id: string) => apiClient.post(`/admin/devices/${id}/revoke`),
  listAudit: (params?: any) => apiClient.get('/admin/audit', { params }),
  getStatus: () => apiClient.get('/admin/status'),
};
