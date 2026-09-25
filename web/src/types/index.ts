export interface AdminUserSession {
  username: string;
  csrf_token: string;
  expires_at: string;
}

export interface OverviewData {
  currency_balances: {
    currency: string;
    total_due_cents: number;
    statement_count: number;
  }[];
  upcoming_bills: {
    id: string;
    account_name: string;
    bank_name: string;
    currency: string;
    remaining_cents: number;
    payment_due_date: string;
    days_left: number;
  }[];
  pending_drafts_count: number;
  job_stats: {
    pending: number;
    running: number;
    failed_last_24h: number;
  };
  latest_mail_sync: {
    at: string | null;
    status: string | null;
    mailbox_name: string | null;
  } | null;
}

export interface AccountCard {
  id: string;
  account_id: string;
  card_last4?: string;
  tail?: string;
  card_type?: string;
  card_alias?: string;
  display_name?: string | null;
  status: string;
  is_active?: boolean;
  revision: number;
  created_at: string;
}

export interface BankAccount {
  id: string;
  bank?: string;
  bank_name?: string;
  account_name?: string;
  alias?: string | null;
  holder?: string | null;
  reference?: string | null;
  currency?: string;
  credit_limit_cents?: number;
  statement_day?: number;
  payment_due_day_offset?: number;
  status: 'active' | 'archived';
  revision: number;
  cards?: AccountCard[];
  current_due_cents?: number;
  created_at: string;
}

export interface StatementVersion {
  id: string;
  version_number: number;
  amount_minor: number;
  minimum_minor: number | null;
  source: string;
  reason: string | null;
  confirmed_at: string | null;
  confirmed_by: string | null;
  created_at: string;
}

export interface PaymentRecord {
  id: string;
  statement_id: string;
  amount_minor: number;
  currency: string;
  note: string | null;
  recorded_at: string;
  revoked_at: string | null;
  revoke_reason: string | null;
}

export interface StatementListItem {
  id: string;
  account_id: string;
  bank: string;
  account_alias: string | null;
  holder?: string | null;
  card_tails?: string[];
  currency: string;
  statement_date: string;
  due_date: string;
  current_version_id: string | null;
  amount_minor: number;
  minimum_minor: number | null;
  total_paid_minor: number;
  remaining_minor: number;
  is_paid: boolean;
  created_at: string;
}

export interface StatementDetailData extends StatementListItem {
  versions: StatementVersion[];
  payments: PaymentRecord[];
  associated_draft: {
    draft_id: string;
    source_id: string | null;
    extractor_name: string;
    evidence: any;
  } | null;
  updated_at: string;
}

export interface StatementDraftItem {
  id: string;
  email_source_id: string | null;
  status: 'pending_review' | 'confirmed' | 'rejected' | string;
  bank: string | null;
  currency: string | null;
  amount_minor: number | null;
  minimum_minor: number | null;
  statement_date: string | null;
  due_date: string | null;
  account_reference: string | null;
  card_tails: string[];
  review_reasons: string[];
  matched_account_id: string | null;
  matched_account_name: string | null;
  matched_card_id: string | null;
  matched_card_tail: string | null;
  extractor_name: string;
  revision: number;
  created_at: string;
}

export interface StatementDraftDetail extends StatementDraftItem {
  evidence: any[];
  confirmed_version_id: string | null;
  rejection_reason: string | null;
  matched_account: {
    id: string;
    bank: string;
    alias: string | null;
  } | null;
  matched_card: {
    id: string;
    tail: string;
    display_name: string | null;
  } | null;
  candidate_accounts: {
    id: string;
    bank: string;
    alias: string | null;
    reference: string | null;
  }[];
  candidate_cards: {
    id: string;
    tail: string;
    display_name: string | null;
  }[];
  source_email: {
    id: string;
    subject: string;
    sender: string;
    email_date: string;
  } | null;
  updated_at: string;
}

export interface EmailAttachment {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface EmailSourceItem {
  id: string;
  mailbox_id: string;
  mailbox_address: string;
  subject: string;
  sender: string;
  recipient: string;
  email_date: string;
  has_attachments: boolean;
  is_statement_candidate: boolean;
  parse_status: string;
  error_message: string | null;
  created_at: string;
}

export interface EmailDetail extends EmailSourceItem {
  folder: string;
  uid: number;
  message_id: string | null;
  body_preview: string;
  attachments: EmailAttachment[];
  drafts: Array<{
    id: string;
    status: string;
    bank: string | null;
    amount_minor: number | null;
    currency: string | null;
    extractor_name: string;
    created_at: string;
  }>;
  jobs: Array<{
    id: string;
    status: string;
    kind: string;
    error_code: string | null;
    created_at: string;
  }>;
}

export interface MailboxItem {
  id: string;
  revision: number;
  email_address: string;
  imap_host: string;
  imap_port: number;
  use_ssl: boolean;
  check_interval_minutes: number;
  is_active: boolean;
  status: string;
  last_checked_at: string | null;
  last_attempt_at: string | null;
  error_message: string | null;
  has_secret: boolean;
  has_pending: boolean;
  tested_revision: number | null;
  name?: string;
  username?: string;
  folder?: string;
  since_days?: number;
  max_messages?: number;
  max_attachment_mb?: number;
  sender_filter?: string;
  subject_filter?: string;
  keep_non_candidates?: boolean;
  auto_parse?: boolean;
}

export interface ModelRevisionItem {
  id: string;
  number: number;
  parameters: {
    base_url: string;
    model: string;
    temperature: number;
    max_tokens: number;
    timeout_seconds: number;
    max_retries: number;
    input_limit: number;
    json_mode: boolean;
    daily_limit: number;
  };
  has_secret: boolean;
  tested_at: string | null;
  test_error: string | null;
  revoked: boolean;
  active: boolean;
  created_at: string;
}

export interface ModelProfileItem {
  id: string;
  name: string;
  revisions: ModelRevisionItem[];
}

export interface AdminJobItem {
  id: string;
  kind: 'sync' | 'parse';
  target_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | string;
  attempts: number;
  cancel_requested: boolean;
  result: any;
  error_code: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface DeviceItem {
  id: string;
  device_name: string;
  device_model: string;
  last_sync_at: string | null;
  is_active: boolean;
  created_at: string;
}

export interface AuditLogItem {
  id: string;
  actor: string;
  action: string;
  target: string | null;
  detail: Record<string, any>;
  created_at: string;
}

export interface SystemStatusData {
  api: {
    status: string;
    version: string;
    environment: string;
    server_time: string;
  };
  database: {
    connected: boolean;
    latency_ms: number;
  };
  storage: {
    storage_dir: string;
    exists: boolean;
    file_count: number;
    size_bytes: number;
  };
  mailboxes: {
    total: number;
    active: number;
  };
  jobs: {
    active: number;
    failed: number;
  };
}
