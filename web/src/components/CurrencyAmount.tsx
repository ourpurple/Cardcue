import React from 'react';

export function centsToYuanString(cents: number | null | undefined): string {
  if (cents === null || cents === undefined || isNaN(cents)) {
    return '0.00';
  }
  const isNegative = cents < 0;
  const abs = Math.abs(Math.round(cents));
  const yuan = Math.floor(abs / 100);
  const fen = abs % 100;
  const fenStr = fen < 10 ? '0' + fen : fen.toString();
  const yuanWithCommas = yuan.toLocaleString('en-US');
  return (isNegative ? '-' : '') + yuanWithCommas + '.' + fenStr;
}

export function yuanStringToCents(yuanStr: string | number): number {
  if (typeof yuanStr === 'number') {
    return Math.round(yuanStr * 100);
  }
  if (!yuanStr || typeof yuanStr !== 'string') {
    return 0;
  }
  const clean = yuanStr.replace(/,/g, '').trim();
  if (!clean) return 0;

  const parts = clean.split('.');
  const isNegative = parts[0].startsWith('-');
  const wholePart = Math.abs(parseInt(parts[0], 10) || 0);
  let fracPart = 0;
  if (parts.length > 1) {
    const fracStr = parts[1].padEnd(2, '0').slice(0, 2);
    fracPart = parseInt(fracStr, 10) || 0;
  }
  const total = wholePart * 100 + fracPart;
  return isNegative ? -total : total;
}

interface Props {
  cents: number | null | undefined;
  currency?: string;
  style?: React.CSSProperties;
  className?: string;
}

export const CurrencyAmount: React.FC<Props> = ({ cents, currency = 'CNY', style, className }) => {
  const symbol = currency === 'CNY' ? '¥' : currency === 'USD' ? '$' : currency + ' ';
  const formatted = centsToYuanString(cents);
  return (
    <span style={{ fontFamily: 'monospace', fontWeight: 500, ...style }} className={className}>
      <span style={{ fontSize: '0.85em', marginRight: 2 }}>{symbol}</span>
      {formatted}
    </span>
  );
};
