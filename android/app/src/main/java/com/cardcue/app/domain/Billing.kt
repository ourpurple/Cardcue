package com.cardcue.app.domain

import java.math.BigDecimal
import java.text.NumberFormat
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import java.util.Locale

/** All money is represented in minor units. This MVP supports CNY and USD (2 decimals). */
object Money {
    private val pattern = Regex("^[0-9]{1,10}(\\.[0-9]{1,2})?$")
    fun parse(text: String): Long? {
        val normalized = text.trim()
        if (!pattern.matches(normalized)) return null
        return runCatching { BigDecimal(normalized).movePointRight(2).longValueExact() }
            .getOrNull()?.takeIf { it > 0 }
    }
    fun input(minor: Long): String = BigDecimal.valueOf(minor, 2).toPlainString()
    fun display(minor: Long, currency: String): String {
        val number = NumberFormat.getNumberInstance(Locale.CHINA).apply {
            minimumFractionDigits = 2
            maximumFractionDigits = 2
        }.format(BigDecimal.valueOf(minor, 2))
        return "${if (currency == "CNY") "¥" else if (currency == "USD") "US$" else "$currency "}$number"
    }
}

object BillingRules {
    fun remaining(due: Long, payments: List<Long>): Long {
        require(due >= 0) { "账单金额不能为负" }
        val paid = payments.fold(0L) { sum, amount ->
            require(amount > 0) { "还款金额必须大于 0" }
            Math.addExact(sum, amount)
        }
        require(paid <= due) { "已记录还款不能超过账单金额" }
        return due - paid
    }
    fun validatePayment(amount: Long, remaining: Long) {
        require(amount > 0) { "请输入大于 0 的金额" }
        require(amount <= remaining) { "记录金额不能超过待还金额" }
    }
    fun daysUntil(date: LocalDate, today: LocalDate): Long = ChronoUnit.DAYS.between(today, date)
    fun dueLabel(date: LocalDate, today: LocalDate, settled: Boolean): String {
        if (settled) return "已记录还清"
        val days = daysUntil(date, today)
        return when {
            days < 0 -> "逾期 ${-days} 天"
            days == 0L -> "今天到期"
            days == 1L -> "明天到期"
            else -> "$days 天后到期"
        }
    }
}
