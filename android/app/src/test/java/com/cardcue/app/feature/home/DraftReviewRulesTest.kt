package com.cardcue.app.feature.home

import com.cardcue.app.data.SyncedAccount
import com.cardcue.app.data.SyncedCard
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.assertNull
import org.junit.Assert.assertEquals
import org.junit.Test

class DraftReviewRulesTest {
    private fun account(mode: String?, status: String = "active") =
        SyncedAccount("account-id", "建设银行", null, null, status, "2026-09-28", billingMode = mode)

    private fun card(id: String, tail: String, status: String = "active") =
        SyncedCard(id, "account-id", "信用卡", tail, status)

    @Test fun unknownModeAndInactiveAccountCannotBeConfirmed() {
        assertFalse(canConfirmDraftAccount(null, emptyList(), emptyList()))
        assertFalse(canConfirmDraftAccount(account(null), listOf(card("one", "1234")), listOf("1234")))
        assertFalse(canConfirmDraftAccount(account("per_card", "archived"), listOf(card("one", "1234")), emptyList()))
    }

    @Test fun perCardRequiresExactlyOneActiveCardAndNoTailConflict() {
        val one = listOf(card("one", "1234"))
        assertFalse(canConfirmDraftAccount(account("per_card"), emptyList(), emptyList()))
        assertFalse(canConfirmDraftAccount(account("per_card"), one + card("two", "5678"), listOf("1234")))
        assertFalse(canConfirmDraftAccount(account("per_card"), one, listOf("1234", "5678")))
        assertFalse(canConfirmDraftAccount(account("per_card"), one, listOf("5678")))
        assertTrue(canConfirmDraftAccount(account("per_card"), one, listOf("1234")))
        assertTrue(canConfirmDraftAccount(account("per_card"), one + card("old", "5678", "archived"), emptyList()))
    }

    @Test fun unknownOrUnsupportedCurrencyIsNeverDefaultedToCny() {
        assertNull(supportedDraftCurrency(""))
        assertNull(supportedDraftCurrency("JPY"))
        assertEquals("USD", supportedDraftCurrency(" usd "))
        assertEquals("CNY", supportedDraftCurrency("CNY"))
    }

    @Test fun consolidatedAllowsMultipleCardsWithoutGuessingIndividualCard() {
        assertTrue(canConfirmDraftAccount(account("consolidated"),
            listOf(card("one", "1234"), card("two", "5678")), listOf("1234", "5678")))
    }
}
