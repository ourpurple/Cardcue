package com.cardcue.app.data

import android.content.Context
import androidx.room.Room
import androidx.sqlite.db.framework.FrameworkSQLiteOpenHelperFactory
import androidx.sqlite.db.SupportSQLiteOpenHelper
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.cardcue.app.domain.BillingRules
import com.cardcue.app.sync.SyncManager
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.time.LocalDate

@RunWith(AndroidJUnit4::class)
class RepositoryTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()

    @Test fun seedIsIdempotentAndPaymentsCanBeReversed() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, CardCueDatabase::class.java).build()
        try {
            val repository = BillRepository(db)
            repository.seedIfNeeded(LocalDate.of(2026, 9, 16))
            repository.seedIfNeeded(LocalDate.of(2026, 9, 17))
            assertEquals(5, repository.bills.first().size)
            repository.recordPayment("demo-bcm", 10000L, "partial")
            var bill = repository.bills.first().first { it.statement.id == "demo-bcm" }
            assertEquals(208329L, bill.remaining)
            repository.voidPayment(bill.payments.single().id)
            bill = repository.bills.first().first { it.statement.id == "demo-bcm" }
            assertEquals(218329L, bill.remaining)
            assertNotNull(bill.payments.single().voidedAt)
        } finally { db.close() }
    }

    @Test fun simultaneousFullPaymentsCannotOverpay() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, CardCueDatabase::class.java).build()
        try {
            val repository = BillRepository(db)
            repository.seedIfNeeded()
            val results = List(2) { async { runCatching { repository.recordPayment("demo-bcm", 218329L, "concurrent") } } }.awaitAll()
            assertEquals(1, results.count { it.isSuccess })
            assertEquals(0L, repository.bills.first().first { it.statement.id == "demo-bcm" }.remaining)
        } finally { db.close() }
    }

    @Test fun committedRecordsSurviveDatabaseReopen() = runBlocking {
        val name = "cardcue-test-${System.nanoTime()}.db"
        var db = Room.databaseBuilder(context, CardCueDatabase::class.java, name).build()
        try {
            var repository = BillRepository(db)
            repository.seedIfNeeded()
            repository.recordPayment("demo-bcm", 1829L, "persist")
            db.close()
            db = Room.databaseBuilder(context, CardCueDatabase::class.java, name).build()
            repository = BillRepository(db)
            repository.seedIfNeeded()
            val bill = repository.bills.first().first { it.statement.id == "demo-bcm" }
            assertEquals(216500L, bill.remaining)
            assertEquals("persist", bill.activePayments.single().note)
        } finally { db.close(); context.deleteDatabase(name) }
    }

    @Test fun migrationFrom1To2PreservesLegacyDataAndEnablesSyncedTables() = runBlocking {
        val dbName = "migration-test-${System.nanoTime()}.db"
        val config = SupportSQLiteOpenHelper.Configuration.builder(context)
            .name(dbName)
            .callback(object : SupportSQLiteOpenHelper.Callback(1) {
                override fun onCreate(db: androidx.sqlite.db.SupportSQLiteDatabase) {
                    db.execSQL(
                        "CREATE TABLE IF NOT EXISTS `statements` (`id` TEXT NOT NULL, `accountKey` TEXT NOT NULL, `bank` TEXT NOT NULL, `bankMark` TEXT NOT NULL, `color` INTEGER NOT NULL, `cardTails` TEXT NOT NULL, `cycle` TEXT NOT NULL, `currency` TEXT NOT NULL, `amountMinor` INTEGER NOT NULL, `minimumMinor` INTEGER NOT NULL, `statementDate` TEXT NOT NULL, `dueDate` TEXT NOT NULL, `source` TEXT NOT NULL, `isDemo` INTEGER NOT NULL, PRIMARY KEY(`id`))"
                    )
                    db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS `index_statements_accountKey_cycle_currency` ON `statements` (`accountKey`, `cycle`, `currency`)")
                    db.execSQL(
                        "CREATE TABLE IF NOT EXISTS `payments` (`id` TEXT NOT NULL, `statementId` TEXT NOT NULL, `amountMinor` INTEGER NOT NULL, `recordedAt` INTEGER NOT NULL, `note` TEXT NOT NULL, `voidedAt` INTEGER, PRIMARY KEY(`id`), FOREIGN KEY(`statementId`) REFERENCES `statements`(`id`) ON UPDATE NO ACTION ON DELETE RESTRICT )"
                    )
                    db.execSQL("CREATE INDEX IF NOT EXISTS `index_payments_statementId` ON `payments` (`statementId`)")
                    db.execSQL("CREATE TABLE IF NOT EXISTS `app_meta` (`key` TEXT NOT NULL, `value` TEXT NOT NULL, PRIMARY KEY(`key`))")
                }
                override fun onUpgrade(db: androidx.sqlite.db.SupportSQLiteDatabase, oldVersion: Int, newVersion: Int) {}
            })
            .build()

        val helper = FrameworkSQLiteOpenHelperFactory().create(config)
        val v1Db = helper.writableDatabase
        v1Db.execSQL(
            "INSERT INTO statements (id, accountKey, bank, bankMark, color, cardTails, cycle, currency, amountMinor, minimumMinor, statementDate, dueDate, source, isDemo) VALUES " +
                "('legacy-st-1', 'acct-legacy', '交通银行', '交', 3438275, '8369', '2026-08', 'CNY', 150000, 15000, '2026-08-01', '2026-08-20', '旧版数据', 1)"
        )
        v1Db.execSQL(
            "INSERT INTO payments (id, statementId, amountMinor, recordedAt, note, voidedAt) VALUES " +
                "('legacy-pay-1', 'legacy-st-1', 50000, 1726000000000, '旧版已还', NULL)"
        )
        v1Db.close()

        val upgradedDb = Room.databaseBuilder(context, CardCueDatabase::class.java, dbName)
            .addMigrations(CardCueDatabase.MIGRATION_1_2)
            .build()

        try {
            val dao = upgradedDb.dao()
            val legacyStatement = dao.statement("legacy-st-1")
            assertNotNull(legacyStatement)
            assertEquals("交通银行", legacyStatement!!.bank)
            assertEquals(150000L, legacyStatement.amountMinor)

            val legacyPayment = dao.payment("legacy-pay-1")
            assertNotNull(legacyPayment)
            assertEquals(50000L, legacyPayment!!.amountMinor)
            assertEquals("旧版已还", legacyPayment.note)

            dao.upsertSyncedAccounts(listOf(
                SyncedAccount("sync-acct-1", "招商银行", "测试账户", null, "active", "2026-09-18T12:00:00")
            ))
            dao.setSyncMeta(SyncMeta("sync_cursor", "1"))

            val accounts = dao.getSyncedAccounts()
            assertEquals(1, accounts.size)
            assertEquals("sync-acct-1", accounts.single().id)
            assertEquals("1", dao.syncMeta("sync_cursor"))
        } finally {
            upgradedDb.close()
            context.deleteDatabase(dbName)
        }
    }

    @Test fun syncedBillsMappingAndReactiveFlow() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, CardCueDatabase::class.java).build()
        try {
            val repository = BillRepository(db)
            val dao = db.dao()

            dao.upsertSyncedAccounts(listOf(
                SyncedAccount(
                    id = "acct-cmb-1",
                    bank = "招商银行",
                    alias = "招行经典白",
                    reference = "REF12345678",
                    status = "active",
                    updatedAt = "2026-09-18T10:00:00"
                )
            ))
            dao.upsertSyncedCards(listOf(
                SyncedCard("card-1", "acct-cmb-1", "主卡", "8899", "active"),
                SyncedCard("card-2", "acct-cmb-1", "附属卡", "1122", "active")
            ))
            dao.upsertSyncedStatementVersions(listOf(
                SyncedStatementVersion(
                    id = "ver-1",
                    statementId = "st-cmb-202609",
                    versionNumber = 1,
                    amountMinor = 500000L,
                    minimumMinor = 50000L,
                    source = "后台同步",
                    reason = null,
                    confirmedAt = null,
                    confirmedBy = null
                )
            ))
            dao.upsertSyncedStatements(listOf(
                SyncedStatement(
                    id = "st-cmb-202609",
                    accountId = "acct-cmb-1",
                    currency = "CNY",
                    statementDate = "2026-09-05",
                    dueDate = "2026-09-25",
                    currentVersionId = "ver-1",
                    totalPaidMinor = 100000L,
                    remainingMinor = 400000L,
                    updatedAt = "2026-09-18T10:00:00"
                )
            ))
            dao.upsertSyncedPayments(listOf(
                SyncedPayment(
                    id = "pay-1",
                    statementId = "st-cmb-202609",
                    amountMinor = 100000L,
                    currency = "CNY",
                    note = "已还首笔",
                    recordedAt = "2026-09-10T12:00:00",
                    revokedAt = null,
                    revokeReason = null
                )
            ))
            dao.setSyncMeta(SyncMeta("sync_cursor", "10"))

            val bills = repository.bills.first()
            assertEquals(1, bills.size)
            val bill = bills.single()
            assertEquals("st-cmb-202609", bill.statement.id)
            assertEquals("招商银行", bill.statement.bank)
            assertEquals("招", bill.statement.bankMark)
            assertEquals(0xFFC25259.toLong(), bill.statement.color)
            assertEquals("1122 · 8899", bill.statement.cardTails)
            assertEquals(500000L, bill.statement.amountMinor)
            assertEquals(400000L, bill.remaining)
            assertFalse(bill.settled)
            assertFalse(bill.statement.isDemo)
            assertEquals(1, bill.payments.size)
            assertEquals(100000L, bill.payments.single().amountMinor)
            assertEquals("已还首笔", bill.payments.single().note)
        } finally { db.close() }
    }

    @Test fun offlinePaymentThrowsExceptionAndDoesNotMutate() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, CardCueDatabase::class.java).build()
        try {
            val syncManager = SyncManager(db, serverUrl = "http://127.0.0.1:59999")
            val repository = BillRepository(db, syncManager)
            val dao = db.dao()

            dao.upsertSyncedStatements(listOf(
                SyncedStatement(
                    id = "st-offline-1",
                    accountId = "acct-1",
                    currency = "CNY",
                    statementDate = "2026-09-05",
                    dueDate = "2026-09-25",
                    currentVersionId = null,
                    totalPaidMinor = 0L,
                    remainingMinor = 100000L,
                    updatedAt = "2026-09-18T10:00:00"
                )
            ))
            dao.setSyncMeta(SyncMeta("sync_cursor", "5"))

            val error = runCatching {
                repository.recordPayment("st-offline-1", 10000L, "offline attempt")
            }.exceptionOrNull()

            assertNotNull(error)
            assertTrue(error is IllegalStateException)
            assertTrue(error!!.message!!.contains("离线只读") || error.message!!.contains("未连接"))

            val payments = dao.getSyncedPayments()
            assertTrue(payments.isEmpty())
            val st = dao.getSyncedStatement("st-offline-1")!!
            assertEquals(100000L, st.remainingMinor)
        } finally { db.close() }
    }
}
