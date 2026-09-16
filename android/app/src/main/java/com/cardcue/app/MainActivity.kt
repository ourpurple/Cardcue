package com.cardcue.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.ViewModelProvider
import androidx.room.Room
import com.cardcue.app.data.BillRepository
import com.cardcue.app.data.CardCueDatabase
import com.cardcue.app.ui.CardCueApp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
        )
        val db = DatabaseHolder.get(applicationContext)
        val model = ViewModelProvider(this, CardCueViewModel.Factory(BillRepository(db)))[CardCueViewModel::class.java]
        setContent { CardCueApp(model) }
    }
}

private object DatabaseHolder {
    @Volatile private var instance: CardCueDatabase? = null
    fun get(context: android.content.Context): CardCueDatabase = instance ?: synchronized(this) {
        instance ?: Room.databaseBuilder(context.applicationContext, CardCueDatabase::class.java, "cardcue.db")
            .build().also { instance = it }
    }
}
