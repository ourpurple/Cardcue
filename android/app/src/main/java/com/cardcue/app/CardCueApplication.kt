package com.cardcue.app

import android.app.Application
import androidx.room.Room
import com.cardcue.app.data.BillRepository
import com.cardcue.app.data.CardCueDatabase

/** The instrumentation runner supplies its own Application; production has no reset hook. */
open class CardCueApplication : Application() {
    open val database: CardCueDatabase by lazy {
        Room.databaseBuilder(this, CardCueDatabase::class.java, "cardcue.db").build()
    }
    val repository: BillRepository get() = BillRepository(database)
}
