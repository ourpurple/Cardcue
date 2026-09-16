package com.cardcue.app.domain

import org.junit.Test

class BillingTest {
    @Test fun moneyAndBillingAcceptanceChecks() { BillingChecks.verifyAll() }
}
