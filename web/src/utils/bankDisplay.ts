/** Bank full name -> abbreviation mapping */
export const BANK_SHORT: Record<string, string> = {
  '交通银行': '交行',
  '华夏银行': '华夏',
  '招商银行': '招商',
  '民生银行': '民生',
  '浦发银行': '浦发',
  '广发银行': '广发',
  '中信银行': '中信',
  '农业银行': '农行',
  '建设银行': '建行',
  '中国银行': '中行',
  '邮储银行': '邮储',
  '中国邮政储蓄银行': '邮储',
  '工商银行': '工行',
  '兴业银行': '兴业',
  '光大银行': '光大',
  '平安银行': '平安',
  '北京银行': '北京',
  '上海银行': '上海',
};

/**
 * Banks where a single holder may have MULTIPLE separate billing accounts.
 * Each account is shown as its own row (never merged).
 */
export const MULTI_ACCOUNT_BANKS = new Set([
  '广发', '中信', '交行', '农行', '建行', '中行', '邮储', '工行', '兴业',
]);

/**
 * Banks where a single holder typically has only ONE billing account.
 * All accounts for the same (bank, holder) are merged into a single row.
 */
export const SINGLE_ACCOUNT_BANKS = new Set([
  '浦发', '华夏', '招商', '民生',
]);

export function getBankShort(bank: string | undefined): string {
  if (!bank) return '';
  if (BANK_SHORT[bank]) return BANK_SHORT[bank];
  // Try partial match
  for (const [full, short] of Object.entries(BANK_SHORT)) {
    if (bank.includes(full) || bank.includes(short)) return short;
  }
  // Fallback: return first 2 chars
  return bank.length > 4 ? bank.slice(0, 2) : bank;
}

/** Check whether a bank abbreviation belongs to the multi-account group */
export function isMultiAccountBank(bankShort: string): boolean {
  return MULTI_ACCOUNT_BANKS.has(bankShort);
}

/** Check whether a bank abbreviation belongs to the single-account group */
export function isSingleAccountBank(bankShort: string): boolean {
  return SINGLE_ACCOUNT_BANKS.has(bankShort);
}
