"""Tests for bank rules registry (P0-01)."""

import pytest
from cardcue_api.domain.bank_rules import (
    ALL_BANKS,
    BankDefinition,
    get_bank_rules_for_api,
    get_default_billing_mode,
    lookup_bank,
    normalise_bank_name,
)


class TestBankLookup:
    """Exact match, alias, substring, and unknown bank scenarios."""

    def test_lookup_by_short_name(self):
        defn = lookup_bank("建行")
        assert defn is not None
        assert defn.short_name == "建行"
        assert defn.code == "CCB"

    def test_lookup_by_full_name(self):
        defn = lookup_bank("中国建设银行")
        assert defn is not None
        assert defn.short_name == "建行"

    def test_lookup_by_code(self):
        defn = lookup_bank("CCB")
        assert defn is not None
        assert defn.short_name == "建行"

    def test_lookup_by_substring(self):
        """Bank email senders often include extra words."""
        defn = lookup_bank("中国农业银行信用卡中心")
        assert defn is not None
        assert defn.short_name == "农行"

    def test_lookup_unknown_returns_none(self):
        assert lookup_bank("花旗银行") is None
        assert lookup_bank("") is None

    @pytest.mark.parametrize("name,expected_short", [
        ("交通银行", "交行"),
        ("浦发银行", "浦发"),
        ("上海浦东发展银行", "浦发"),
        ("中信银行", "中信"),
        ("邮储银行", "邮储"),
        ("中国邮政储蓄银行", "邮储"),
        ("工商银行", "工行"),
        ("中国工商银行", "工行"),
        ("兴业银行", "兴业"),
        ("广发银行", "广发"),
        ("华夏银行", "华夏"),
        ("招商银行", "招商"),
        ("民生银行", "民生"),
        ("中国银行", "中行"),
    ])
    def test_lookup_all_known_banks(self, name, expected_short):
        defn = lookup_bank(name)
        assert defn is not None, f"Failed to find {name}"
        assert defn.short_name == expected_short


class TestBillingMode:
    """Verify per_card / consolidated / None defaults."""

    @pytest.mark.parametrize("bank,expected_mode", [
        ("农行", "per_card"),
        ("建行", "per_card"),
        ("中行", "per_card"),
        ("中信", "per_card"),
        ("邮储", "per_card"),
        ("工行", "per_card"),
        ("交行", "per_card"),
        ("兴业", "per_card"),
        ("广发", "per_card"),
    ])
    def test_per_card_banks(self, bank, expected_mode):
        assert get_default_billing_mode(bank) == expected_mode

    @pytest.mark.parametrize("bank,expected_mode", [
        ("浦发", "consolidated"),
        ("华夏", "consolidated"),
        ("招商", "consolidated"),
        ("民生", "consolidated"),
    ])
    def test_consolidated_banks(self, bank, expected_mode):
        assert get_default_billing_mode(bank) == expected_mode

    def test_unknown_bank_returns_none(self):
        assert get_default_billing_mode("花旗银行") is None
        assert get_default_billing_mode("光大") is None

    def test_other_known_banks_have_no_default_mode(self):
        """光大、平安 etc. are known but have no billing mode set."""
        assert get_default_billing_mode("光大") is None
        assert get_default_billing_mode("平安") is None


class TestNormaliseBankName:
    def test_normalise_known(self):
        assert normalise_bank_name("中国建设银行") == "建行"
        assert normalise_bank_name("浦发银行") == "浦发"

    def test_normalise_unknown_returns_stripped(self):
        assert normalise_bank_name("  花旗银行  ") == "花旗银行"


class TestBankRulesAPI:
    def test_api_returns_list(self):
        rules = get_bank_rules_for_api()
        assert isinstance(rules, list)
        assert len(rules) == len(ALL_BANKS)

    def test_api_structure(self):
        rules = get_bank_rules_for_api()
        ccb = next(r for r in rules if r["code"] == "CCB")
        assert ccb["short_name"] == "建行"
        assert ccb["default_billing_mode"] == "per_card"
        assert "中国建设银行" in ccb["full_names"]


class TestRegistryIntegrity:
    """Ensure no duplicate short_names, codes, or aliases."""

    def test_unique_short_names(self):
        shorts = [b.short_name for b in ALL_BANKS]
        assert len(shorts) == len(set(shorts)), f"Duplicate short names: {shorts}"

    def test_unique_codes(self):
        codes = [b.code for b in ALL_BANKS]
        assert len(codes) == len(set(codes)), f"Duplicate codes: {codes}"

    def test_no_empty_full_names(self):
        for b in ALL_BANKS:
            assert len(b.full_names) > 0, f"{b.short_name} has no full names"
            for name in b.full_names:
                assert name.strip(), f"{b.short_name} has empty full name"
