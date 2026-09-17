package com.cardcue.app.testing

import android.app.Application
import android.app.Activity
import android.content.Context
import android.os.Bundle
import android.view.WindowManager
import androidx.test.runner.AndroidJUnitRunner
import com.cardcue.app.CardCueApplication
import com.cardcue.app.data.CardCueDatabase

class CardCueTestRunner : AndroidJUnitRunner() {
    override fun newApplication(cl: ClassLoader, className: String, context: Context): Application =
        super.newApplication(cl, TestCardCueApplication::class.java.name, context)

    override fun callActivityOnCreate(activity: Activity, icicle: Bundle?) {
        activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        super.callActivityOnCreate(activity, icicle)
    }
}

class TestCardCueApplication : CardCueApplication() {
    var testDatabase: CardCueDatabase? = null
    // Fail closed: no instrumentation test can fall back to cardcue.db.
    override val database: CardCueDatabase
        get() = checkNotNull(testDatabase) { "Install an isolated test database before launching an Activity" }
}
