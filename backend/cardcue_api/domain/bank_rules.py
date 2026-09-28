"""Canonical bank identifier registry and default billing rules.

This module is the **single source of truth** for:
- Normalised bank identifiers (short names used as canonical keys)
- Full-name / alias mappings
- Default billing mode per bank (per_card vs consolidated)
- Bank metadata served to frontend and used in model prompts

Business rules from PARSING_V2_PLAN §3.1:
- per_card: 每张卡独立还款，账单及明细识别到卡
- consolidated: 持卡人合并还款，交易保留有依据的卡片信息
- None (unknown): 未配置银行或无法确定，人工确认后再入账
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

BillingMode = Literal["per_card", "consolidated"]
BillingModeSource = Literal["bank_default", "manual_override"]

# ---------------------------------------------------------------------------
# Bank definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BankDefinition:
    """Immutable definition of a known bank."""

    # Canonical short name used as the system-wide key (e.g. "建行")
    short_name: str

    # Official / common full names (first entry is the "primary" full name)
    full_names: tuple[str, ...]

    # ISO-style English abbreviation used in logs & API, never shown to users
    code: str

    # Default billing mode; None means "unknown, must be confirmed manually"
    default_billing_mode: BillingMode | None = None

    # All searchable aliases (including short_name and full_names)
    @property
    def all_aliases(self) -> tuple[str, ...]:
        seen: list[str] = [self.short_name]
        for name in self.full_names:
            if name not in seen:
                seen.append(name)
        return tuple(seen)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Per-card billing banks (独立还款)
_PER_CARD_BANKS: list[BankDefinition] = [
    BankDefinition(
        short_name="农行",
        full_names=("中国农业银行", "农业银行"),
        code="ABC",
        default_billing_mode="per_card",
    ),
    BankDefinition(
        short_name="建行",
        full_names=("中国建设银行", "建设银行"),
        code="CCB",
        default_billing_mode="per_card",
    ),
    BankDefinition(
        short_name="中行",
        full_names=("中国银行",),
        code="BOC",
        default_billing_mode="per_card",
    ),
    BankDefinition(
        short_name="中信",
        full_names=("中信银行",),
        code="CITIC",
        default_billing_mode="per_card",
    ),
    BankDefinition(
        short_name="邮储",
        full_names=("中国邮政储蓄银行", "邮储银行"),
        code="PSBC",
        default_billing_mode="per_card",
    ),
    BankDefinition(
        short_name="工行",
        full_names=("中国工商银行", "工商银行"),
        code="ICBC",
        default_billing_mode="per_card",
    ),
    BankDefinition(
        short_name="交行",
        full_names=("交通银行",),
        code="BCOM",
        default_billing_mode="per_card",
    ),
    BankDefinition(
        short_name="兴业",
        full_names=("兴业银行",),
        code="CIB",
        default_billing_mode="per_card",
    ),
    BankDefinition(
        short_name="广发",
        full_names=("广发银行",),
        code="GDB",
        default_billing_mode="per_card",
    ),
]

# Consolidated billing banks (合并还款)
_CONSOLIDATED_BANKS: list[BankDefinition] = [
    BankDefinition(
        short_name="浦发",
        full_names=("上海浦东发展银行", "浦发银行"),
        code="SPDB",
        default_billing_mode="consolidated",
    ),
    BankDefinition(
        short_name="华夏",
        full_names=("华夏银行",),
        code="HXB",
        default_billing_mode="consolidated",
    ),
    BankDefinition(
        short_name="招商",
        full_names=("招商银行",),
        code="CMB",
        default_billing_mode="consolidated",
    ),
    BankDefinition(
        short_name="民生",
        full_names=("民生银行",),
        code="CMBC",
        default_billing_mode="consolidated",
    ),
]

# Additional known banks (no default billing mode yet)
_OTHER_BANKS: list[BankDefinition] = [
    BankDefinition(
        short_name="光大",
        full_names=("中国光大银行", "光大银行"),
        code="CEB",
        default_billing_mode=None,
    ),
    BankDefinition(
        short_name="平安",
        full_names=("平安银行",),
        code="PAB",
        default_billing_mode=None,
    ),
    BankDefinition(
        short_name="北京",
        full_names=("北京银行",),
        code="BOB",
        default_billing_mode=None,
    ),
    BankDefinition(
        short_name="上海",
        full_names=("上海银行",),
        code="SHBANK",
        default_billing_mode=None,
    ),
]

ALL_BANKS: tuple[BankDefinition, ...] = tuple(
    _PER_CARD_BANKS + _CONSOLIDATED_BANKS + _OTHER_BANKS
)

# ---------------------------------------------------------------------------
# Lookup indices (built once at import time)
# ---------------------------------------------------------------------------

# short_name -> BankDefinition
_BY_SHORT: dict[str, BankDefinition] = {b.short_name: b for b in ALL_BANKS}

# code -> BankDefinition
_BY_CODE: dict[str, BankDefinition] = {b.code: b for b in ALL_BANKS}

# any alias -> BankDefinition (case-sensitive Chinese matching)
_BY_ALIAS: dict[str, BankDefinition] = {}
for _b in ALL_BANKS:
    for _alias in _b.all_aliases:
        _BY_ALIAS[_alias] = _b


def lookup_bank(name: str) -> BankDefinition | None:
    """Resolve a bank name/alias/code to its canonical definition.

    Tries exact match first, then substring containment for partial names
    like "交通银行信用卡中心".  Returns None for unknown banks.
    """
    name = name.strip()
    if not name:
        return None

    # 1. Exact match on any alias or code
    if name in _BY_ALIAS:
        return _BY_ALIAS[name]
    if name in _BY_CODE:
        return _BY_CODE[name]

    # 2. Substring match: "中国农业银行信用卡中心" -> 农行
    for b in ALL_BANKS:
        for alias in b.all_aliases:
            if alias in name or name in alias:
                return b

    return None


def get_default_billing_mode(bank_name: str) -> BillingMode | None:
    """Return the default billing mode for a bank, or None if unknown."""
    defn = lookup_bank(bank_name)
    return defn.default_billing_mode if defn else None


def normalise_bank_name(bank_name: str) -> str:
    """Return the canonical short name for a bank, or the original string if unknown."""
    defn = lookup_bank(bank_name)
    return defn.short_name if defn else bank_name.strip()


def get_bank_rules_for_api() -> list[dict]:
    """Return bank rules as a list of dicts suitable for API responses.

    Frontend consumes this instead of maintaining its own copy.
    """
    return [
        {
            "short_name": b.short_name,
            "full_names": list(b.full_names),
            "code": b.code,
            "default_billing_mode": b.default_billing_mode,
        }
        for b in ALL_BANKS
    ]
