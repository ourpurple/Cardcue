package com.cardcue.app.data

import androidx.room.withTransaction
import com.cardcue.app.domain.BillingRules
import com.cardcue.app.sync.SyncManager
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.util.UUID

data class Bill(val statement: Statement, val payments: List<Payment>) {
    val activePayments: List<Payment> get() = payments.filter { it.voidedAt == null }
    val remaining: Long get() = BillingRules.remaining(statement.amountMinor, activePayments.map { it.amountMinor })
    val settled: Boolean get() = remaining == 0L
}

class BillRepository(
    private val db: CardCueDatabase,
    val syncManager: SyncManager? = null,
) {
    private val dao = db.dao()

    private val demoBillsFlow: Flow<List<Bill>> = combine(dao.observeStatements(), dao.observePayments()) { statements, payments ->
        val grouped = payments.groupBy { it.statementId }
        statements.map { Bill(it, grouped[it.id].orEmpty()) }
    }

    private val syncedBillsFlow: Flow<List<Bill>> = combine(
        dao.observeSyncedStatements(),
        dao.observeSyncedAccounts(),
        dao.observeSyncedCards(),
        dao.observeSyncedStatementVersions(),
        dao.observeSyncedPayments()
    ) { statements, accounts, cards, versions, payments ->
        val accountMap = accounts.associateBy { it.id }
        val cardsByAccount = cards.groupBy { it.accountId }
        val versionMap = versions.associateBy { it.id }
        val paymentsByStatement = payments.groupBy { it.statementId }

        statements.map { s ->
            val account = accountMap[s.accountId]
            val acctCards = cardsByAccount[s.accountId].orEmpty()
            val version = s.currentVersionId?.let { versionMap[it] }
            val stPayments = paymentsByStatement[s.id].orEmpty()

            val bankName = account?.bank ?: "信用卡账户"
            val bankMark = bankMark(bankName)
            val color = bankColor(bankName)
            val tails = if (acctCards.isNotEmpty()) {
                acctCards.map { it.tail }.sorted().joinToString(" · ")
            } else {
                account?.reference?.takeLast(4) ?: "----"
            }
            val amountMinor = version?.amountMinor ?: (s.totalPaidMinor + s.remainingMinor)
            val minimumMinor = version?.minimumMinor ?: 0L
            val cycle = s.statementDate.take(7)

            val statement = Statement(
                id = s.id,
                accountKey = s.accountId,
                bank = bankName,
                bankMark = bankMark,
                color = color,
                cardTails = tails,
                cycle = cycle,
                currency = s.currency,
                amountMinor = amountMinor,
                minimumMinor = minimumMinor,
                statementDate = s.statementDate,
                dueDate = s.dueDate,
                source = version?.source ?: "后台同步",
                isDemo = false
            )

            val mappedPayments = stPayments.map { p ->
                Payment(
                    id = p.id,
                    statementId = p.statementId,
                    amountMinor = p.amountMinor,
                    recordedAt = parseIsoToMillis(p.recordedAt),
                    note = p.note ?: "",
                    voidedAt = if (p.revokedAt != null) 1L else null
                )
            }

            Bill(statement, mappedPayments)
        }
    }

    /**
     * R1-03: Dual-track bill display logic.
     *
     * When a sync cursor exists AND synced bills are present, show only synced bills
     * (official mode). When the sync cursor exists but synced bills are empty (first
     * empty backend or sync just completed with no data), fall back to demo bills so
     * old local records are never silently erased. When no cursor exists at all, prefer
     * synced bills if any, otherwise demo bills.
     */
    val bills: Flow<List<Bill>> = combine(syncedBillsFlow, demoBillsFlow, dao.observeSyncMeta()) { syncedBills, demoBills, meta ->
        val hasSynced = meta.any { it.key == "sync_cursor" }
        if (hasSynced && syncedBills.isNotEmpty()) {
            // Official mode: backend-confirmed bills only.
            syncedBills
        } else if (hasSynced && syncedBills.isEmpty()) {
            // R1-03: sync cursor exists but backend returned no data.
            // Preserve old local records instead of showing nothing.
            demoBills
        } else {
            // Never synced: show synced if present, else demo.
            if (syncedBills.isNotEmpty()) syncedBills else demoBills
        }
    }

    val syncedAccounts: Flow<List<SyncedAccount>> = dao.observeSyncedAccounts()
    val syncedCards: Flow<List<SyncedCard>> = dao.observeSyncedCards()

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

    suspend fun recordPayment(statementId: String, amount: Long, note: String) {
        require(note.length <= 120) { "备注最多 120 字" }
        val demoBill = dao.statement(statementId)
        if (demoBill != null) {
            db.withTransaction {
                val remaining = BillingRules.remaining(demoBill.amountMinor, dao.activePayments(statementId).map { it.amountMinor })
                BillingRules.validatePayment(amount, remaining)
                dao.insertPayment(Payment(UUID.randomUUID().toString(), statementId, amount, System.currentTimeMillis(), note.trim()))
            }
        } else {
            val syncedStatement = dao.getSyncedStatement(statementId)
                ?: throw IllegalArgumentException("账单不存在")
            val sync = syncManager ?: throw IllegalStateException("同步管理器未初始化")
            sync.recordPaymentOnline(
                statementId = statementId,
                amountMinor = amount,
                currency = syncedStatement.currency,
                note = note.trim()
            )
        }
    }

    suspend fun voidPayment(id: String) {
        val demoPayment = dao.payment(id)
        if (demoPayment != null) {
            db.withTransaction {
                require(dao.voidPayment(id, System.currentTimeMillis()) == 1) { "该记录已经撤销" }
            }
        } else {
            val syncedPayment = dao.getSyncedPayment(id)
                ?: throw IllegalArgumentException("还款记录不存在")
            if (syncedPayment.revokedAt != null) {
                throw IllegalArgumentException("该记录已经撤销")
            }
            val sync = syncManager ?: throw IllegalStateException("同步管理器未初始化")
            sync.revokePaymentOnline(id, "用户撤销还款")
        }
    }

    companion object {
        fun bankColor(bank: String): Long = when {
            bank.contains("交通") -> 0xFF3476C3
            bank.contains("农业") -> 0xFF208979
            bank.contains("招商") -> 0xFFC25259
            bank.contains("中信") -> 0xFF8F627B
            bank.contains("工商") -> 0xFFC72828
            bank.contains("建设") -> 0xFF005BAC
            bank.contains("中国银行") -> 0xFFB61B1F
            bank.contains("浦发") -> 0xFF0A3B7A
            bank.contains("民生") -> 0xFF007552
            bank.contains("光大") -> 0xFF651C7E
            bank.contains("广发") -> 0xFFBE141E
            bank.contains("平安") -> 0xFFEA5504
            bank.contains("兴业") -> 0xFF004098
            bank.contains("华夏") -> 0xFFCC0000
            bank.contains("邮储") -> 0xFF007D34
            else -> 0xFF4A6572
        }

        fun bankMark(bank: String): String = when {
            bank.contains("交通") -> "交"
            bank.contains("农业") -> "农"
            bank.contains("招商") -> "招"
            bank.contains("中信") -> "信"
            bank.contains("工商") -> "工"
            bank.contains("建设") -> "建"
            bank.contains("中国银行") -> "中"
            bank.contains("浦发") -> "浦"
            bank.contains("民生") -> "民"
            bank.contains("光大") -> "光"
            bank.contains("广发") -> "广"
            bank.contains("平安") -> "平"
            bank.contains("兴业") -> "兴"
            bank.contains("华夏") -> "华"
            bank.contains("邮储") -> "邮"
            else -> bank.take(1)
        }

        fun parseIsoToMillis(iso: String): Long {
            if (iso.isBlank()) return System.currentTimeMillis()
            return try {
                Instant.parse(iso).toEpochMilli()
            } catch (_: Exception) {
                try {
                    java.time.OffsetDateTime.parse(iso).toInstant().toEpochMilli()
                } catch (_: Exception) {
                    try {
                        java.time.LocalDateTime.parse(iso).atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
                    } catch (_: Exception) {
                        System.currentTimeMillis()
                    }
                }
            }
        }
    }
}
