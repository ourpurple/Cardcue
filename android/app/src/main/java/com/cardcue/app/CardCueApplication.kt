package com.cardcue.app

import android.app.Application
import androidx.room.Room
import com.cardcue.app.data.BillRepository
import com.cardcue.app.data.CardCueDatabase
import com.cardcue.app.sync.SyncManager

/** The instrumentation runner supplies its own Application; production has no reset hook. */
open class CardCueApplication : Application() {
    open val database: CardCueDatabase by lazy {
        Room.databaseBuilder(this, CardCueDatabase::class.java, "cardcue.db")
            .addMigrations(CardCueDatabase.MIGRATION_1_2)
            .build()
    }
    open val syncManager: SyncManager by lazy {
        SyncManager(database)
    }
    open val repository: BillRepository get() = BillRepository(database, syncManager)
}
