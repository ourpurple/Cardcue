package com.cardcue.app.ui

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import com.cardcue.app.MainActivity
import org.junit.Rule
import org.junit.Test

/** Run against a fresh emulator/app install so the demo bill has no pre-existing payments. */
class PaymentFlowTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    @Test fun openBillRecordAndReversePartialPayment() {
        compose.waitUntil(60_000) { compose.onAllNodesWithText("交通银行").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText("交通银行").performClick()
        compose.onNodeWithText("账单详情").assertIsDisplayed()
        compose.onNodeWithText("记录还款").performClick()
        compose.onNodeWithText("已还金额").performTextReplacement("100.00")
        compose.onNodeWithText("保存记录").performClick()
        compose.waitUntil(60_000) { compose.onAllNodesWithText("¥2,083.29").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText("¥2,083.29").assertIsDisplayed()
        compose.onNodeWithTag("bill-detail-list").performScrollToNode(hasText("撤销"))
        compose.onNodeWithText("撤销").performClick()
        compose.onNodeWithText("撤销记录").performClick()
        compose.waitUntil(60_000) { compose.onAllNodesWithText("已撤销").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText("已撤销").assertExists()
    }
}
