package com.cardcue.app.ui

import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import com.cardcue.app.MainActivity
import com.cardcue.app.testing.TestDatabaseRule
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain

class PaymentFlowTest {
    private val database = TestDatabaseRule()
    private val compose = createAndroidComposeRule<MainActivity>()
    @get:Rule val rules: RuleChain = RuleChain.outerRule(database).around(compose)

    private fun openBill() {
        compose.waitUntil(15_000) { compose.onAllNodesWithTag("home-bill-demo-bcm").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("home-bill-demo-bcm").performClick()
        compose.onNodeWithTag("detail-pay").assertIsDisplayed()
    }

    private fun bill() = runBlocking { database.repository.bills.first().first { it.statement.id == "demo-bcm" } }

    private fun awaitBalance(text: String) {
        compose.waitUntil(15_000) {
            compose.onAllNodes(hasTestTag("detail-remaining") and hasText(text)).fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithTag("bill-detail-list").performScrollToNode(hasTestTag("detail-remaining"))
        compose.onNodeWithTag("detail-remaining").assertTextEquals(text).assertIsDisplayed()
    }

    @Test fun partialPaymentAndVoidRestoreBalanceAndKeepOriginalRecord() {
        openBill()
        compose.onNodeWithTag("detail-pay").performClick()
        compose.onNodeWithTag("payment-amount").performTextReplacement("100.00")
        compose.onNodeWithTag("payment-save").performClick()
        awaitBalance("¥2,083.29")
        val paymentId = bill().activePayments.single().id
        compose.onNodeWithTag("bill-detail-list").performScrollToNode(hasTestTag("payment-void-$paymentId"))
        compose.onNodeWithTag("payment-void-$paymentId").performClick()
        compose.onNodeWithTag("void-confirm").performClick()
        compose.waitUntil(15_000) { compose.onAllNodesWithTag("payment-voided-$paymentId").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("payment-voided-$paymentId").assertExists()
        awaitBalance("¥2,183.29")
        assertEquals(1, bill().payments.size)
        assertNotNull(bill().payments.single().voidedAt)
    }

    @Test fun fullPaymentSettlesAndDisablesAnotherPayment() {
        openBill()
        compose.onNodeWithTag("detail-pay").performClick()
        compose.onNodeWithTag("payment-save").performClick()
        awaitBalance("¥0.00")
        compose.onNodeWithTag("detail-pay").assertIsNotEnabled()
        assertEquals(218329L, bill().activePayments.single().amountMinor)
    }

    @Test fun invalidAmountsCannotSaveAndCancelDoesNotWrite() {
        openBill()
        compose.onNodeWithTag("detail-pay").performClick()
        listOf("0", "-1", "1.001", "1e3", "2183.30", "").forEach { value ->
            compose.onNodeWithTag("payment-amount").performTextReplacement(value)
            compose.onNodeWithTag("payment-save").assertIsNotEnabled()
        }
        compose.onNodeWithTag("payment-amount").performTextReplacement("0.01")
        compose.onNodeWithTag("payment-save").assertIsEnabled()
        compose.onNodeWithTag("payment-cancel").performClick()
        awaitBalance("¥2,183.29")
        assertTrue(bill().payments.isEmpty())
    }

    @Test fun repeatedSaveDuringSameUiFrameWritesOnlyOnce() {
        openBill()
        compose.onNodeWithTag("detail-pay").performClick()
        compose.onNodeWithTag("payment-amount").performTextReplacement("100.00")
        compose.onNodeWithTag("payment-save").performSemanticsAction(SemanticsActions.OnClick) { click ->
            click()
            click()
        }
        awaitBalance("¥2,083.29")
        assertEquals(1, bill().activePayments.size)
    }

    @Test fun activityRecreationKeepsDialogDraftAndHistoryNavigationWorks() {
        openBill()
        compose.onNodeWithTag("detail-pay").performClick()
        compose.onNodeWithTag("payment-amount").performTextReplacement("12.34")
        compose.activityRule.scenario.recreate()
        compose.onNodeWithTag("payment-amount").assertTextContains("12.34")
        compose.onNodeWithTag("payment-cancel").performClick()
        compose.onNodeWithContentDescription("返回").performClick()
        compose.onNodeWithTag("tab-1").performClick()
        compose.onNodeWithTag("history-filter-2").performClick()
        compose.waitUntil(15_000) {
            compose.onAllNodesWithTag("history-bill-demo-old-bcm").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithTag("history-bill-demo-old-bcm").assertIsDisplayed().performClick()
        awaitBalance("¥0.00")
        compose.onNodeWithContentDescription("返回").performClick()
        compose.onNodeWithTag("history-filter-2").assertIsSelected()
        compose.onNodeWithTag("history-filter-1").performClick()
        compose.waitUntil(15_000) {
            compose.onAllNodesWithTag("history-bill-demo-old-bcm").fetchSemanticsNodes().isEmpty()
        }
        compose.onNodeWithTag("history-bill-demo-old-bcm").assertDoesNotExist()
        assertTrue(bill().payments.isEmpty())
    }
}
