/** Bank full name -> abbreviation mapping */
export const BANK_SHORT: Record<string, string> = {
  '交通银行': '交行',
  '交行': '交行',
  '华夏银行': '华夏',
  '华夏': '华夏',
  '招商银行': '招商',
  '招商': '招商',
  '民生银行': '民生',
  '民生': '民生',
  '浦发银行': '浦发',
  '上海浦东发展银行': '浦发',
  '浦发': '浦发',
  '广发银行': '广发',
  '广发': '广发',
  '中信银行': '中信',
  '中信': '中信',
  '农业银行': '农行',
  '中国农业银行': '农行',
  '农行': '农行',
  '建设银行': '建行',
  '中国建设银行': '建行',
  '建行': '建行',
  '中国银行': '中行',
  '中行': '中行',
  '邮储银行': '邮储',
  '中国邮政储蓄银行': '邮储',
  '邮储': '邮储',
  '工商银行': '工行',
  '中国工商银行': '工行',
  '工行': '工行',
  '兴业银行': '兴业',
  '兴业': '兴业',
  '光大银行': '光大',
  '中国光大银行': '光大',
  '光大': '光大',
  '平安银行': '平安',
  '平安': '平安',
  '北京银行': '北京',
  '上海银行': '上海',
};

/**
 * Banks where a single holder may have MULTIPLE separate billing accounts.
 * E.g. 广发、中信、交行、农行、建行、中行、邮储、工行、兴业
 * Each account is shown as its own row (never merged).
 */
export const MULTI_ACCOUNT_BANKS = new Set([
  '广发', '中信', '交行', '农行', '建行', '中行', '邮储', '工行', '兴业',
]);

/**
 * Banks where a single holder typically has only ONE billing account.
 * E.g. 浦发、华夏、招商、民生
 * All accounts/cards for the same (bank, holder) are merged into a single row.
 */
export const SINGLE_ACCOUNT_BANKS = new Set([
  '浦发', '华夏', '招商', '民生',
]);

export function getBankShort(bank: string | null | undefined): string {
  if (!bank) return '';
  const trimmed = bank.trim();
  if (BANK_SHORT[trimmed]) return BANK_SHORT[trimmed];
  // Try partial match
  for (const [full, short] of Object.entries(BANK_SHORT)) {
    if (trimmed.includes(full) || trimmed.includes(short)) return short;
  }
  // Fallback: return first 2 chars
  return trimmed.length > 4 ? trimmed.slice(0, 2) : trimmed;
}

/** Check whether a bank belongs to the multi-account group */
export function isMultiAccountBank(bank: string | null | undefined): boolean {
  return MULTI_ACCOUNT_BANKS.has(getBankShort(bank));
}

/** Check whether a bank belongs to the single-account group */
export function isSingleAccountBank(bank: string | null | undefined): boolean {
  return SINGLE_ACCOUNT_BANKS.has(getBankShort(bank));
}

/**
 * Uniformly formats the primary title: "银行缩写 持卡人 卡号后四位"
 * e.g. "交行 牛鋆辉 8369"
 * If single-account bank with multiple cards: "招商 杨小宾 9166 / 8727 / 9999"
 */
export function formatBankHolderTails(
  bank: string | null | undefined,
  holder: string | null | undefined,
  tails: string | string[] | null | undefined
): string {
  const bankShort = getBankShort(bank);
  const h = holder?.trim() || '';

  let tailStr = '';
  if (Array.isArray(tails)) {
    const cleanTails = tails.map(t => t?.trim()).filter(Boolean) as string[];
    tailStr = cleanTails.join(' / ');
  } else if (tails) {
    tailStr = tails.trim();
  }

  const parts = [bankShort, h, tailStr].filter(Boolean);
  return parts.join(' ') || bank || '';
}

/**
 * Filter out auto-generated generic display names such as "交通银行 (8369)" or "交行 (8369)"
 */
export function getCustomDisplayName(displayName: string | null | undefined, bank: string, tail?: string): string | undefined {
  if (!displayName) return undefined;
  const trimmed = displayName.trim();
  if (!trimmed) return undefined;
  if (trimmed === bank || trimmed === getBankShort(bank)) return undefined;
  if (tail && (trimmed === tail || trimmed === `尾号 ${tail}` || trimmed === `尾号${tail}`)) return undefined;
  if (tail && bank && (trimmed === `${bank} (${tail})` || trimmed === `${bank}(${tail})`)) return undefined;
  const bs = getBankShort(bank);
  if (tail && bs && (trimmed === `${bs} (${tail})` || trimmed === `${bs}(${tail})`)) return undefined;
  return trimmed;
}

/**
 * Filter out auto-generated generic account aliases such as "广发银行信用卡 (牛鋆辉)"
 */
export function cleanAccountAlias(alias: string | null | undefined, bank?: string | null, holder?: string | null): string | undefined {
  if (!alias) return undefined;
  let trimmed = alias.trim();
  if (!trimmed) return undefined;

  const bankShort = getBankShort(bank);
  const h = (holder || '').trim();

  if (h) {
    trimmed = trimmed.replace(new RegExp('[(（]\\s*' + h + '\\s*[)）]', 'g'), '').trim();
  }

  trimmed = trimmed.replace(/^(中国|上海)?(交通|华夏|招商|民生|浦东发展|浦发|广发|中信|农业|农行|建设|建行|中国银行|中行|邮政储蓄|邮储|工商|工行|兴业|光大|平安|北京|上海)?(银行)?/g, '').trim();

  const full = (bank || '').trim();
  if (full && trimmed.startsWith(full)) trimmed = trimmed.slice(full.length).trim();
  if (bankShort && trimmed.startsWith(bankShort)) trimmed = trimmed.slice(bankShort.length).trim();

  trimmed = trimmed.replace(/^[-_\s:：()（）]+|[-_\s:：()（）]+$/g, '').trim();

  const genericWords = new Set(['', '信用卡', '卡', '个人卡', '贷记卡', '联名卡', '主卡', '牡丹卡', '金穗信用卡', '金穗卡']);
  if (genericWords.has(trimmed)) {
    return undefined;
  }
  return trimmed;
}

export interface AccountCardOption {
  value: string;
  accountId: string;
  cardId?: string;
  bank: string;
  bankShort: string;
  holder: string;
  tail?: string;
  displayName?: string | null;
  alias?: string | null;
  /** Primary label: strictly "银行缩写 持卡人 卡号后四位" (e.g. "交行 牛鋆辉 8369") */
  label: string;
  /** Extra detail for display/subtext (e.g. "车主卡" or "白金卡") */
  extraText?: string;
  /** Full label for searching: e.g. "交行 牛鋆辉 8369 (车主卡)" */
  fullLabel: string;
  /** Searchable text containing bank full name, abbreviation, holder, tail, etc. */
  filterText: string;
  isAccountOnly?: boolean;
}

export function buildAccountCardOptions(
  candidateAccounts: Array<{
    id: string;
    bank: string;
    alias?: string | null;
    holder?: string | null;
    reference?: string | null;
    cards?: Array<{
      id: string;
      tail: string;
      display_name?: string | null;
      status?: string;
    }>;
  }>
): AccountCardOption[] {
  const options: AccountCardOption[] = [];

  for (const acct of candidateAccounts) {
    const bank = acct.bank || '';
    const bankShort = getBankShort(bank);
    const holder = (acct.holder || '').trim();
    const cleanAlias = cleanAccountAlias(acct.alias, bank, holder);
    const activeCards = (acct.cards || []).filter(c => !c.status || c.status === 'active');

    if (activeCards.length === 0) {
      const baseTitle = [bankShort, holder, '(无卡片)'].filter(Boolean).join(' ');
      const fullLabel = cleanAlias ? `${baseTitle} (${cleanAlias})` : baseTitle;
      const filterText = `${baseTitle} ${bank} ${bankShort} ${holder} ${cleanAlias || ''} ${acct.alias || ''}`;
      options.push({
        value: `${acct.id}__none`,
        accountId: acct.id,
        cardId: undefined,
        bank,
        bankShort,
        holder,
        alias: cleanAlias,
        extraText: cleanAlias,
        label: baseTitle,
        fullLabel,
        filterText,
        isAccountOnly: true,
      });
    } else {
      for (const card of activeCards) {
        // Primary label: "银行缩写 持卡人 卡号后四位"
        const baseTitle = [bankShort, holder, card.tail].filter(Boolean).join(' ');
        const customName = getCustomDisplayName(card.display_name, bank, card.tail);
        const extraDesc = customName || cleanAlias;
        const fullLabel = extraDesc && !baseTitle.includes(extraDesc)
          ? `${baseTitle} (${extraDesc})`
          : baseTitle;
        const filterText = `${baseTitle} ${bank} ${bankShort} ${holder} ${card.tail} ${extraDesc || ''} ${acct.alias || ''} ${card.display_name || ''}`;

        options.push({
          value: `${acct.id}__${card.id}`,
          accountId: acct.id,
          cardId: card.id,
          bank,
          bankShort,
          holder,
          tail: card.tail,
          displayName: customName,
          alias: cleanAlias,
          extraText: extraDesc,
          label: baseTitle,
          fullLabel,
          filterText,
          isAccountOnly: false,
        });
      }

      // For single-account banks with multiple cards, offer merged account option
      if (activeCards.length > 1 && isSingleAccountBank(bankShort)) {
        const baseTitle = [bankShort, holder, '(整户合并还款)'].filter(Boolean).join(' ');
        const fullLabel = cleanAlias && !baseTitle.includes(cleanAlias)
          ? `${baseTitle} (${cleanAlias})`
          : baseTitle;
        const allTails = activeCards.map(c => c.tail).join(' ');
        const filterText = `${baseTitle} ${bank} ${bankShort} ${holder} ${allTails} ${cleanAlias || ''}`;
        options.push({
          value: `${acct.id}__all`,
          accountId: acct.id,
          cardId: undefined,
          bank,
          bankShort,
          holder,
          alias: cleanAlias,
          extraText: cleanAlias || '整户合并',
          label: baseTitle,
          fullLabel,
          filterText,
          isAccountOnly: true,
        });
      }
    }
  }

  return options;
}
