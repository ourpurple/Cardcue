package com.cardcue.app.data

import androidx.room.withTransaction
import com.cardcue.app.domain.BillingRules
import kotlinx.coroutines.flow.combine
import java.time.LocalDate
import java.util.UUID

data class Bill(val statement: Statement, val payments: List<Payment>) {
    val activePayments: List<Payment> get() = payments.filter { it.voidedAt == null }
    val remaining: Long get() = BillingRules.remaining(statement.amountMinor, activePayments.map { it.amountMinor })
    val settled: Boolean get() = remaining == 0L
}

class BillRepository(private val db: CardCueDatabase) {
    private val dao = db.dao()
    val bills = combine(dao.observeStatements(), dao.observePayments()) { statements, payments ->
        val grouped = payments.groupBy { it.statementId }
        statements.map { Bill(it, grouped[it.id].orEmpty()) }
    }

    suspend fun seedIfNeeded(today: LocalDate = LocalDate.now()) = db.withTransaction {
        if (dao.meta("demo_seed_v1") != null) return@withTransaction
        fun sample(id: String, bank: String, mark: String, color: Long, tails: String, amount: Long, days: Long, currency: String = "CNY", previous: Boolean = false): Statement {
            val due = if (previous) today.minusMonths(1).withDayOfMonth(20) else today.plusDays(days)
            val issued = due.minusDays(20)
            return Statement(id, "demo-$mark", bank, mark, color, tails, issued.toString().take(7), currency, amount, amount / 10, issued.toString(), due.toString())
        }
        val samples = listOf(
            sample("demo-bcm", "交通银行", "交", 0xFF3476C3, "8369", 218329, 1),
            sample("demo-abc", "农业银行", "农", 0xFF208979, "8753", 108080, 5),
            sample("demo-cmb", "招商银行", "招", 0xFFC25259, "2090 · 9759", 356642, 12),
            sample("demo-citic", "中信银行", "信", 0xFF8F627B, "5791", 12650, 8, "USD"),
            sample("demo-old-bcm", "交通银行", "交", 0xFF3476C3, "8369", 165000, 0, previous = true),
        )
        dao.insertStatements(samples)
        dao.insertPayment(Payment("demo-old-payment", "demo-old-bcm", 165000, System.currentTimeMillis() - 30L * 86400000, "演示：上期已还清"))
        dao.insertMeta(AppMeta("demo_seed_v1", "done"))
    }

    suspend fun recordPayment(statementId: String, amount: Long, note: String) = db.withTransaction {
        val bill = requireNotNull(dao.statement(statementId)) { "账单不存在" }
        val remaining = BillingRules.remaining(bill.amountMinor, dao.activePayments(statementId).map { it.amountMinor })
        BillingRules.validatePayment(amount, remaining)
        require(note.length <= 120) { "备注最多 120 字" }
        dao.insertPayment(Payment(UUID.randomUUID().toString(), statementId, amount, System.currentTimeMillis(), note.trim()))
    }

    suspend fun voidPayment(id: String) = db.withTransaction {
        requireNotNull(dao.payment(id)) { "还款记录不存在" }
        require(dao.voidPayment(id, System.currentTimeMillis()) == 1) { "该记录已经撤销" }
    }
}
