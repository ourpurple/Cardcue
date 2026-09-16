package com.cardcue.app.domain

import java.time.LocalDate

/** Dependency-free acceptance checks, shared by JUnit and the offline verification script. */
object BillingChecks {
    fun verifyAll(): Int {
        var count = 0
        fun case(name: String, assertion: () -> Unit) {
            try { assertion(); count++ } catch (e: Throwable) { throw AssertionError(name, e) }
        }
        fun rejects(action: () -> Unit) {
            check(runCatching(action).exceptionOrNull() is IllegalArgumentException)
        }
        case("decimal amounts are exact") { check(Money.parse("183.29") == 18329L); check(Money.parse("0.01") == 1L) }
        case("integer and one-decimal input") { check(Money.parse("10") == 1000L); check(Money.parse("10.8") == 1080L) }
        case("no zero or negative payments") { check(Money.parse("0") == null); check(Money.parse("-1") == null) }
        case("no ambiguous formats or precision loss") {
            listOf("1.001", "1e3", "1,000", "NaN", "Infinity", "", ".5", "1.").forEach { check(Money.parse(it) == null) }
        }
        case("oversized input cannot overflow") { check(Money.parse("999999999999999999999") == null) }
        case("large supported amount stays exact") { check(Money.parse("9999999999.99") == 999999999999L) }
        case("display and input preserve cents") { check(Money.input(1080L) == "10.80"); check(Money.display(18329L, "CNY") == "¥183.29") }
        case("currency labels distinguish dollars") { check(Money.display(12650L, "USD") == "US$126.50") }
        case("new bill preserves full balance") { check(BillingRules.remaining(18329L, emptyList()) == 18329L) }
        case("multiple partial payments") { check(BillingRules.remaining(18329L, listOf(10000L, 8000L)) == 329L) }
        case("exact full payment settles") { check(BillingRules.remaining(18329L, listOf(18000L, 329L)) == 0L) }
        case("reversed payment restores balance") {
            val payments = listOf(10000L, 8000L)
            check(BillingRules.remaining(18329L, payments.dropLast(1)) == 8329L)
        }
        case("reject overpayment") { rejects { BillingRules.validatePayment(18400L, 18329L) } }
        case("reject duplicate payment on settled bill") { rejects { BillingRules.validatePayment(18329L, 0L) } }
        case("reject zero and negative ledger entries") {
            rejects { BillingRules.validatePayment(0L, 100L) }
            rejects { BillingRules.remaining(100L, listOf(-1L)) }
        }
        case("reject inconsistent imported balance") { rejects { BillingRules.remaining(100L, listOf(101L)) } }
        val today = LocalDate.of(2026, 12, 31)
        case("year boundary") { check(BillingRules.daysUntil(LocalDate.of(2027, 1, 1), today) == 1L) }
        case("leap day") { check(BillingRules.daysUntil(LocalDate.of(2028, 3, 1), LocalDate.of(2028, 2, 28)) == 2L) }
        case("today and tomorrow labels") {
            check(BillingRules.dueLabel(today, today, false) == "今天到期")
            check(BillingRules.dueLabel(today.plusDays(1), today, false) == "明天到期")
        }
        case("overdue and settled labels") {
            check(BillingRules.dueLabel(today.minusDays(2), today, false) == "逾期 2 天")
            check(BillingRules.dueLabel(today.minusDays(2), today, true) == "已记录还清")
        }
        return count
    }
}

fun main() { println("PASS: ${BillingChecks.verifyAll()} money and billing acceptance checks") }
