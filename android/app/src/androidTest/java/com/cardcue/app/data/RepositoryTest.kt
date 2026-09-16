package com.cardcue.app.data

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.cardcue.app.domain.BillingRules
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
}
