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

export type BillingMode = 'per_card' | 'consolidated';
export type BillingModeSource = 'bank_default' | 'manual_override';

export interface BankRule {
  short_name: string;
  full_names: string[];
  code: string;
  default_billing_mode: BillingMode | null;
}

export interface BankAccount {
  id: string;
  bank?: string;
  bank_name?: string;
  account_name?: string;
  alias?: string | null;
  holder?: string | null;
  reference?: string | null;
  billing_mode?: BillingMode | null;
  billing_mode_source?: BillingModeSource | null;
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

export interface HistoricalOwnershipPreview {
  read_only: true;
  account: { id: string; bank: string; alias: string | null; holder: string | null; reference: string | null; billing_mode: BillingMode | null; bank_default_mode_hint: BillingMode | null; revision: number };
  cards: { id: string; account_id: string; tail: string; display_name: string | null; status: string; revision: number }[];
  peer_account_ids: string[];
  statements: { id: string; account_id: string; currency: string; statement_date: string; current_version_id: string | null; version_count: number; version_ids: string[]; payment_count: number; active_payment_count: number; confirmed_transaction_count: number; observed_card_tails: string[]; proposed_account_id: null; risks: string[] }[];
  counts: { cards: number; statements: number; versions: number; payments: number; confirmed_transactions: number; linked_drafts: number };
  linked_drafts: { id: string; status: string; revision: number; matched_account_id: string | null; matched_card_id: string | null }[];
  risks: string[];
  next_step: string;
}
export interface HistoricalOwnershipPreflightResult {
  read_only: true;
  can_execute: false;
  valid_mapping: boolean;
  issues: string[];
  decisions: { statement_id: string; original_account_id: string; target_account_id: string; target_card_id: string | null; version_count: number; payment_count: number; issues: string[] }[];
  notice: string;
}
export interface TransactionDetail {
  id: string;
  sequence: number;
  transaction_date: string | null;
  posting_date: string | null;
  description: string | null;
  amount_minor: number | null;
  currency: string | null;
  card_tail: string | null;
  transaction_type: string | null;
  evidence?: { field: string; excerpt: string }[];
  review_flags?: string[];
}

export interface SourceManifest {
  entries: { kind: string; filename?: string | null; notes?: string | null; truncated?: boolean }[];
  has_unsupported: boolean;
  unsupported_files: string[];
}

export interface StatementVersion {
  id: string;
  version_number: number;
  detail_status?: 'none' | 'partial' | 'complete';
  expected_transaction_count?: number | null;
  recognized_transaction_count?: number;
  confirmed_transaction_count?: number;
  flagged_transaction_count?: number;
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

export interface DetailSetSummary {
  id: string;
  statement_version_id: string;
  revision: number;
  detail_status: 'none' | 'partial' | 'complete';
  source_draft_id: string | null;
  confirmed_at: string;
}

export interface StatementDetailData extends StatementListItem {
  detail_set_id?: string | null;
  detail_revision?: number;
  detail_history?: DetailSetSummary[];
  detail_status: 'none' | 'partial' | 'complete';
  expected_transaction_count?: number | null;
  recognized_transaction_count?: number;
  confirmed_transaction_count?: number;
  flagged_transaction_count?: number;
  transactions: TransactionDetail[];
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
  detail_status?: 'none' | 'partial' | 'complete';
  source_manifest?: SourceManifest | null;
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
  matched_account_bank?: string | null;
  matched_account_holder?: string | null;
  matched_card_id: string | null;
  matched_card_tail: string | null;
  extractor_name: string;
  revision: number;
  created_at: string;
}

export interface StatementDraftDetail extends StatementDraftItem {
  transactions: TransactionDetail[];
  evidence: any[];
  confirmed_version_id: string | null;
  rejection_reason: string | null;
  matched_account: {
    id: string;
    bank: string;
    alias: string | null;
    holder?: string | null;
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
    holder?: string | null;
    reference: string | null;
    billing_mode: BillingMode | null;
    billing_mode_source: BillingModeSource | null;
    revision: number;
    cards?: Array<{
      id: string;
      tail: string;
      display_name: string | null;
      status?: string;
    }>;
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
  name: string;
  status: string;
  paired_at: string | null;
  last_seen_at: string | null;
  revoked_at: string | null;
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
