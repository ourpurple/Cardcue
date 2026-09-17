package com.cardcue.app.testing

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.cardcue.app.data.BillRepository
import com.cardcue.app.data.CardCueDatabase
import kotlinx.coroutines.runBlocking
import org.junit.rules.ExternalResource
import java.util.UUID

/** Must wrap the Activity rule, so the Activity closes before the database does. */
class TestDatabaseRule : ExternalResource() {
    private val name = "cardcue-instrumentation-${UUID.randomUUID()}.db"
    private lateinit var app: TestCardCueApplication
    lateinit var db: CardCueDatabase
        private set
    val repository get() = BillRepository(db)

    override fun before() {
        app = ApplicationProvider.getApplicationContext()
        db = Room.databaseBuilder(app, CardCueDatabase::class.java, name).build()
        app.testDatabase = db
        runBlocking { repository.seedIfNeeded() }
    }

    override fun after() {
        app.testDatabase = null
        db.close()
        check(name.startsWith("cardcue-instrumentation-"))
        app.deleteDatabase(name)
    }
}
