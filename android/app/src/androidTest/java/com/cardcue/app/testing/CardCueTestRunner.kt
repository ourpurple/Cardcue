package com.cardcue.app.testing

import android.app.Activity
import android.app.Application
import android.app.KeyguardManager
import android.content.Context
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.test.runner.AndroidJUnitRunner
import com.cardcue.app.CardCueApplication
import com.cardcue.app.data.BillRepository
import com.cardcue.app.data.CardCueDatabase

class CardCueTestRunner : AndroidJUnitRunner() {
    override fun newApplication(cl: ClassLoader, className: String, context: Context): Application =
        super.newApplication(cl, TestCardCueApplication::class.java.name, context)

    override fun callActivityOnCreate(activity: Activity, icicle: Bundle?) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            activity.setShowWhenLocked(true)
            activity.setTurnScreenOn(true)
        }
        @Suppress("DEPRECATION")
        activity.window.addFlags(
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or
            WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD or
            WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
            WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val keyguardManager = activity.getSystemService(Context.KEYGUARD_SERVICE) as? KeyguardManager
            keyguardManager?.requestDismissKeyguard(activity, null)
        }
        super.callActivityOnCreate(activity, icicle)
    }
}

class TestCardCueApplication : CardCueApplication() {
    var testDatabase: CardCueDatabase? = null
    // Fail closed: no instrumentation test can fall back to cardcue.db.
    override val database: CardCueDatabase
        get() = checkNotNull(testDatabase) { "Install an isolated test database before launching an Activity" }
    override val repository: BillRepository
        get() = BillRepository(database, null)
}
