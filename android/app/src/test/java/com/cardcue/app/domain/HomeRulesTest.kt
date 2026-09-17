package com.cardcue.app.domain

import com.cardcue.app.data.Bill
import com.cardcue.app.data.Payment
import com.cardcue.app.data.Statement
import org.junit.Assert.*
import org.junit.Test
import java.time.LocalDate

class HomeRulesTest {
    private val today = LocalDate.of(2026, 12, 31)
    private fun bill(id: String, amount: Long = 10000, days: Long = 1,
                     account: String = id, cycle: String = "2026-12", currency: String = "CNY",
                     tails: String = "1234", payments: List<Payment> = emptyList()): Bill =
        Bill(Statement(id, account, "示例银行", "例", 0, tails, cycle, currency, amount, 0,
            "2026-12-01", today.plusDays(days).toString()), payments)
    private fun payment(id: String, amount: Long, voided: Boolean = false) =
        Payment("pay-$id", id, amount, 1, "", if (voided) 2 else null)

    @Test fun sharedCardsCountOneStatementAndCurrenciesStaySeparate() {
        val overview = HomeRules.summarize(listOf(
            bill("shared", amount = 18329, tails = "1234 · 5678", account = "account"),
            bill("dollars", amount = 12650, account = "account", currency = "USD")), today)
        assertEquals(mapOf("CNY" to 18329L, "USD" to 12650L), overview.totals)
        assertEquals(2, overview.bills.size)
    }

    @Test fun sameTailOnDifferentAccountsDoesNotMerge() {
        val overview = HomeRules.summarize(listOf(bill("a"), bill("b", amount = 20000)), today)
        assertEquals(30000L, overview.totals["CNY"])
        assertEquals(2, overview.bills.size)
    }

    @Test fun oldUnpaidBillRemainsEvenWhenLatestBillIsSettled() {
        val old = bill("old", account = "account", cycle = "2026-11", days = -30)
        val latest = bill("latest", account = "account", payments = listOf(payment("latest", 10000)))
        val overview = HomeRules.summarize(listOf(latest, old), today)
        assertEquals(listOf("old", "latest"), overview.bills.map { it.statement.id })
        assertEquals(10000L, overview.totals["CNY"])
    }

    @Test fun oldSettledBillIsHiddenButLatestSettledBillRemains() {
        val old = bill("old", account = "account", cycle = "2026-11", days = -30,
            payments = listOf(payment("old", 10000)))
        val latest = bill("latest", account = "account", payments = listOf(payment("latest", 10000)))
        val overview = HomeRules.summarize(listOf(old, latest), today)
        assertEquals(listOf("latest"), overview.bills.map { it.statement.id })
        assertTrue(overview.totals.isEmpty())
        assertEquals(0, overview.dueSoonCount)
    }

    @Test fun latestSelectionIsPerCurrency() {
        val cny = bill("cny", account = "account", payments = listOf(payment("cny", 10000)))
        val usd = bill("usd", account = "account", currency = "USD", days = 9,
            payments = listOf(payment("usd", 10000)))
        assertEquals(2, HomeRules.summarize(listOf(cny, usd), today).bills.size)
    }

    @Test fun reversingFullPaymentRestoresTotalsAndOldBillVisibility() {
        val old = bill("old", account = "account", cycle = "2026-11", days = -30,
            payments = listOf(payment("old", 10000, voided = true)))
        val latest = bill("latest", account = "account", amount = 20000,
            payments = listOf(payment("latest", 3000)))
        val overview = HomeRules.summarize(listOf(old, latest), today)
        assertEquals(27000L, overview.totals["CNY"])
        assertEquals(2, overview.bills.size)
        assertEquals(1, old.payments.size)
    }

    @Test fun dueSoonIncludesTodayAndDaySixButNotOverdueDaySevenOrSettled() {
        val bills = listOf(bill("overdue", days = -1), bill("today", days = 0),
            bill("six", days = 6), bill("seven", days = 7),
            bill("settled", days = 1, payments = listOf(payment("settled", 10000))))
        assertEquals(2, HomeRules.summarize(bills, today).dueSoonCount)
    }

    @Test fun unpaidBillsSortByDueDateBeforeSettledBills() {
        val overview = HomeRules.summarize(listOf(bill("later", days = 6),
            bill("settled", days = -4, payments = listOf(payment("settled", 10000))),
            bill("earlier", days = -1)), today)
        assertEquals(listOf("earlier", "later", "settled"), overview.bills.map { it.statement.id })
    }

    @Test fun emptyAndZeroAmountBillsHaveNoPendingTotal() {
        assertEquals(HomeOverview(emptyList(), emptyMap(), 0), HomeRules.summarize(emptyList(), today))
        val overview = HomeRules.summarize(listOf(bill("zero", amount = 0)), today)
        assertEquals(1, overview.bills.size)
        assertTrue(overview.totals.isEmpty())
        assertEquals(0, overview.dueSoonCount)
    }

    @Test fun largestValidTotalIsExact() {
        val overview = HomeRules.summarize(listOf(bill("a", Long.MAX_VALUE - 1), bill("b", 1)), today)
        assertEquals(Long.MAX_VALUE, overview.totals["CNY"])
    }

    @Test(expected = ArithmeticException::class) fun overflowingTotalFailsExplicitly() {
        HomeRules.summarize(listOf(bill("a", Long.MAX_VALUE), bill("b", 1)), today)
    }

    @Test(expected = IllegalArgumentException::class) fun duplicateStatementCannotBecomeDoubleDebt() {
        val item = bill("a")
        HomeRules.summarize(listOf(item, item), today)
    }

    @Test(expected = IllegalArgumentException::class) fun conflictingAccountCycleRequiresResolution() {
        HomeRules.summarize(listOf(bill("a", account = "same"), bill("b", account = "same")), today)
    }
}
