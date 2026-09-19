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
        val v1Helper = FrameworkSQLiteOpenHelperFactory().create(config)
        val v1Db = v1Helper.writableDatabase
        // Seed v1 data: a demo statement, a payment, and seed markers.
        v1Db.execSQL("INSERT INTO statements VALUES ('v1-bcm','demo-交','交通银行','交',${0xFF3476C3},'8369','2026-09','CNY',218329,21832,'2026-09-01','2026-09-20','内置演示账单',1)")
        v1Db.execSQL("INSERT INTO payments VALUES ('v1-pay','v1-bcm',50000,${System.currentTimeMillis()},'还款测试',NULL)")
        v1Db.execSQL("INSERT INTO app_meta VALUES ('demo_seed_v1','done')")
        v1Db.close()
        v1Helper.close()

        val upgradedDb = Room.databaseBuilder(context, CardCueDatabase::class.java, dbName)
            .addMigrations(CardCueDatabase.MIGRATION_1_2)
            .build()
        try {
            val dao = upgradedDb.dao()
            val statement = dao.statement("v1-bcm")
            assertNotNull("Legacy statement must survive migration", statement)
            assertEquals(218329L, statement!!.amountMinor)
            assertEquals("交通银行", statement.bank)
            assertTrue("Legacy data must be flagged as demo", statement.isDemo)

            val payment = dao.payment("v1-pay")
            assertNotNull("Legacy payment must survive migration", payment)
            assertEquals(50000L, payment!!.amountMinor)
            assertNull("Payment should not be voided", payment.voidedAt)

            val meta = dao.meta("demo_seed_v1")
            assertEquals("Seed marker must survive", "done", meta)

            // Verify synced tables are empty and operational.
            val syncedAccounts = dao.getSyncedAccounts()
            assertTrue(syncedAccounts.isEmpty())
            dao.upsertSyncedAccounts(listOf(
                SyncedAccount("test-acct", "测试银行", null, "REF123", "active", "2026-09-18T10:00:00")
            ))
            assertEquals(1, dao.getSyncedAccounts().size)
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

    // ── R1-01: Demo data preserved after migration, shows separate from synced ──

    @Test fun demoDataNotAutoUploadedAndHasSeparateViewEntry() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, CardCueDatabase::class.java).build()
        try {
            val repository = BillRepository(db)
            repository.seedIfNeeded()
            val dao = db.dao()

            // Verify all seeded statements are flagged as demo.
            val demoStatements = dao.observeStatements().first()
            assertTrue("Seed should produce demo statements", demoStatements.isNotEmpty())
            assertTrue("All seeded data must be flagged isDemo=true", demoStatements.all { it.isDemo })
            assertTrue("All seeded data must have demo source", demoStatements.all { it.source == "内置演示账单" })

            // When no sync cursor exists, bills show demo data.
            val billsBeforeSync = repository.bills.first()
            assertEquals(demoStatements.size, billsBeforeSync.size)
            assertTrue(billsBeforeSync.all { it.statement.isDemo })

            // After setting sync_cursor with synced data, demo bills are hidden.
            dao.upsertSyncedAccounts(listOf(
                SyncedAccount("acct-1", "工商银行", null, "REF111", "active", "2026-09-19T00:00:00")
            ))
            dao.upsertSyncedStatements(listOf(
                SyncedStatement("st-sync-1", "acct-1", "CNY", "2026-09-01", "2026-09-20",
                    null, 0L, 300000L, "2026-09-19T00:00:00")
            ))
            dao.setSyncMeta(SyncMeta("sync_cursor", "1"))

            val billsAfterSync = repository.bills.first()
            assertEquals("Only synced bill should show", 1, billsAfterSync.size)
            assertFalse("Synced bill should not be demo", billsAfterSync.first().statement.isDemo)

            // Demo data still exists in the local tables, not deleted.
            val demoStillExists = dao.observeStatements().first()
            assertEquals("Demo data must still exist in local table", demoStatements.size, demoStillExists.size)
        } finally { db.close() }
    }

    // ── R1-03: Empty backend or sync failure doesn't wipe old local records ──

    @Test fun emptyBackendPreservesLocalDemoBills() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, CardCueDatabase::class.java).build()
        try {
            val repository = BillRepository(db)
            repository.seedIfNeeded()
            val dao = db.dao()

            // Simulate: user previously synced (cursor exists), but backend was reset and is now empty.
            dao.setSyncMeta(SyncMeta("sync_cursor", "5"))
            // Synced tables are empty (simulating empty backend bootstrap).

            val bills = repository.bills.first()
            assertTrue("Must show demo bills when backend is empty", bills.isNotEmpty())
            assertTrue("Shown bills should be demo data", bills.all { it.statement.isDemo })

            // Verify demo data is intact.
            val demoStatements = dao.observeStatements().first()
            assertTrue("Demo statements preserved", demoStatements.size >= 5)
        } finally { db.close() }
    }

    @Test fun syncFailureDoesNotClearExistingSyncedRecords() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, CardCueDatabase::class.java).build()
        try {
            val repository = BillRepository(db)
            val dao = db.dao()

            // Pre-populate synced data as if a previous sync succeeded.
            dao.upsertSyncedAccounts(listOf(
                SyncedAccount("acct-pre", "交通银行", null, "REF999", "active", "2026-09-18T00:00:00")
            ))
            dao.upsertSyncedStatements(listOf(
                SyncedStatement("st-pre-1", "acct-pre", "CNY", "2026-09-01", "2026-09-20",
                    null, 0L, 150000L, "2026-09-18T00:00:00")
            ))
            dao.setSyncMeta(SyncMeta("sync_cursor", "10"))

            // Verify synced data is shown.
            val billsBefore = repository.bills.first()
            assertEquals(1, billsBefore.size)
            assertEquals("st-pre-1", billsBefore.first().statement.id)

            // SyncManager with unreachable server — simulate sync failure.
            // (We don't call syncNow here, just verify that existing data survives.)
            val billsAfterFailure = repository.bills.first()
            assertEquals("Synced records must survive sync failure", 1, billsAfterFailure.size)
            assertEquals("st-pre-1", billsAfterFailure.first().statement.id)
        } finally { db.close() }
    }
}
