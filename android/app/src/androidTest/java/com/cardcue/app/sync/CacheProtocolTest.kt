package com.cardcue.app.sync

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.cardcue.app.data.CardCueDatabase
import com.cardcue.app.data.BillRepository
import com.cardcue.app.data.SyncMeta
import com.cardcue.app.data.SyncedAccount
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.flow.first
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class CacheProtocolTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()
    private class FakeApi : SyncApiClient() {
        var bootstraps = 0
        var changes = 0
        var fail = false
        var online = true
        override fun checkHealth(baseUrl: String) = online
        override fun getBootstrap(baseUrl: String, token: String): SyncBootstrapResponse {
            bootstraps++
            if (fail) throw SyncApiException(503, "synthetic failure")
            return SyncBootstrapResponse(42, "2026-09-29T00:00:00Z", listOf(AccountDto(
                "account-1", "测试银行", "旧账户", null, "active", "", "",
                "独立持卡人", "per_card", "manual_override", 7,
            )), emptyList(), emptyList(), emptyList())
        }
        override fun getChanges(baseUrl: String, token: String, cursor: Long, limit: Int): SyncChangesResponse {
            changes++
            return SyncChangesResponse(cursor, false, emptyList(), "2026-09-29T00:00:00Z")
        }
    }
    private suspend fun prepare(db: CardCueDatabase) {
        val dao = db.dao()
        dao.upsertSyncedAccounts(listOf(SyncedAccount("account-1", "测试银行", "旧账户", null, "active", "", revision = 1)))
        dao.setSyncMeta(SyncMeta(SyncManager.META_DEVICE_TOKEN, "synthetic-token"))
        dao.setSyncMeta(SyncMeta(SyncManager.META_DEVICE_ID, "synthetic-device"))
        dao.setSyncMeta(SyncMeta(SyncManager.META_CURSOR, "42"))
    }
    @Test fun oldCacheRefreshesWithoutServerChanges() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, CardCueDatabase::class.java).build()
        try {
            prepare(db)
            val api = FakeApi()
            val manager = SyncManager(db, api, "http://localhost")
            assertTrue(manager.syncNow())
            assertEquals(1, api.bootstraps)
            assertEquals(0, api.changes)
            assertEquals("per_card", db.dao().getSyncedAccounts().single().billingMode)
            assertEquals("独立持卡人", db.dao().getSyncedAccounts().single().holder)
            assertEquals(7, db.dao().getSyncedAccounts().single().revision)
            assertEquals(SyncManager.CACHE_PROTOCOL, db.dao().syncMeta(SyncManager.META_CACHE_PROTOCOL))
            assertTrue(manager.syncNow())
            assertEquals(1, api.bootstraps)
            assertEquals(1, api.changes)
        } finally { db.close() }
    }
    @Test fun bootstrapNeverUploadsOrDeletesLocalDemoPayments() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, CardCueDatabase::class.java).build()
        try {
            val repository = BillRepository(db)
            repository.seedIfNeeded()
            val demo = db.dao().observeStatements().first().first { it.amountMinor > 100L }
            repository.recordPayment(demo.id, 100L, "synthetic demo")
            val paymentsBefore = db.dao().activePayments(demo.id)
            prepare(db)
            val api = FakeApi()
            val manager = SyncManager(db, api, "http://localhost")

            assertTrue(manager.syncNow())
            assertEquals(1, api.bootstraps)
            assertEquals(0, api.changes)
            assertEquals(demo, db.dao().statement(demo.id))
            assertEquals(paymentsBefore, db.dao().activePayments(demo.id))
            assertEquals("Empty remote snapshot must not become a formal debt", 0, db.dao().getSyncedStatements().size)
        } finally { db.close() }
    }

    @Test fun offlineDoesNotClearCacheOrAdvanceProtocol() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, CardCueDatabase::class.java).build()
        try {
            prepare(db)
            val api = FakeApi().apply { online = false }
            val manager = SyncManager(db, api, "http://localhost")
            assertFalse(manager.syncNow())
            assertEquals(SyncState.OFFLINE, manager.syncInfo.value.state)
            assertEquals(1, db.dao().getSyncedAccounts().single().revision)
            assertEquals("42", db.dao().syncMeta(SyncManager.META_CURSOR))
            assertNull(db.dao().syncMeta(SyncManager.META_CACHE_PROTOCOL))
            assertEquals(0, api.bootstraps)
        } finally { db.close() }
    }
    @Test fun failedRefreshPreservesCacheAndRetries() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(context, CardCueDatabase::class.java).build()
        try {
            prepare(db)
            val api = FakeApi().apply { fail = true }
            val manager = SyncManager(db, api, "http://localhost")
            assertFalse(manager.syncNow())
            assertEquals(1, db.dao().getSyncedAccounts().single().revision)
            assertEquals("42", db.dao().syncMeta(SyncManager.META_CURSOR))
            assertNull(db.dao().syncMeta(SyncManager.META_CACHE_PROTOCOL))
            api.fail = false
            assertTrue(manager.syncNow())
            assertEquals(2, api.bootstraps)
            assertEquals(7, db.dao().getSyncedAccounts().single().revision)
        } finally { db.close() }
    }
}
