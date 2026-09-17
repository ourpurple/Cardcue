package com.cardcue.app.ui

import android.graphics.Bitmap
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModelProvider
import com.cardcue.app.CardCueViewModel
import com.cardcue.app.MainActivity
import com.cardcue.app.testing.TestDatabaseRule
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.RuleChain
import java.io.File

class CompactLayoutTest {
    private val database = TestDatabaseRule()
    private val compose = createAndroidComposeRule<MainActivity>()
    @get:Rule val rules: RuleChain = RuleChain.outerRule(database).around(compose)

    private fun assertTextFits(tag: String) {
        val results = mutableListOf<TextLayoutResult>()
        compose.onNodeWithTag(tag, useUnmergedTree = true)
            .performSemanticsAction(SemanticsActions.GetTextLayoutResult) { it(results) }
        assertTrue("No text layout for $tag", results.isNotEmpty())
        assertTrue("Clipped text: $tag; " + results.joinToString { result ->
            "size=${result.size}, paragraph=${result.multiParagraph.width}x${result.multiParagraph.height}, " +
                "widthOverflow=${result.didOverflowWidth}, heightOverflow=${result.didOverflowHeight}, " +
                "constraints=${result.layoutInput.constraints}"
        }, results.none { it.hasVisualOverflow })
    }

    private fun checkLayout(scale: Float) {
        compose.runOnUiThread {
            val model = ViewModelProvider(compose.activity,
                CardCueViewModel.Factory(database.repository))[CardCueViewModel::class.java]
            val density = compose.activity.resources.displayMetrics.density
            compose.activity.setContent {
                CompositionLocalProvider(LocalDensity provides Density(density, scale)) {
                    Box(Modifier.width(360.dp)) { CardCueApp(model) }
                }
            }
        }
        compose.waitUntil(15_000) { compose.onAllNodesWithTag("home-total-CNY").fetchSemanticsNodes().isNotEmpty() }
        val output = File(compose.activity.getExternalFilesDir(null), "layout-evidence").apply { mkdirs() }
        File(output, "home-font-$scale.png").outputStream().use {
            compose.onRoot().captureToImage().asAndroidBitmap().compress(Bitmap.CompressFormat.PNG, 100, it)
        }
        compose.onNodeWithTag("home-total-CNY").assertTextEquals("¥6,830.51")
        assertTextFits("home-total-CNY")
        if (scale == 1f) {
            assertTrue("Header became too tall", compose.onNodeWithTag("home-header").getUnclippedBoundsInRoot().let { it.bottom - it.top } < 200.dp)
            assertTrue("Bill became too tall", compose.onNodeWithTag("home-bill-demo-bcm").getUnclippedBoundsInRoot().let { it.bottom - it.top } < 150.dp)
        }
        for (id in listOf("demo-bcm", "demo-cmb", "demo-citic")) {
            compose.onNodeWithTag("home-list").performScrollToNode(hasTestTag("home-bill-$id"))
            assertTextFits("home-remaining-$id")
            assertTextFits("home-due-$id")
            assertTextFits("home-cards-$id")
            assertTrue("Payment tap target too small",
                compose.onNodeWithTag("home-pay-$id").getUnclippedBoundsInRoot().let { it.bottom - it.top } >= 48.dp)
        }
        compose.onNodeWithTag("home-pay-demo-citic").performClick()
        compose.onNodeWithTag("payment-amount").performClick().performTextReplacement("1.00")
        compose.onNodeWithTag("payment-save").assertIsDisplayed().assertIsEnabled()
        compose.onNodeWithTag("payment-cancel").assertIsDisplayed().performClick()
    }

    @Test fun defaultFontAt360dp() = checkLayout(1f)
    @Test fun largeFontAt360dp() = checkLayout(1.3f)
    @Test fun largestFontAt360dp() = checkLayout(1.5f)
}
