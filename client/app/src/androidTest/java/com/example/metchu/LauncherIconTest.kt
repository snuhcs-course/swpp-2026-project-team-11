package com.example.metchu

import android.graphics.drawable.AdaptiveIconDrawable
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

// Samsung's package installer sizes its bitmap from the layers' intrinsic size and
// aborts the install screen when it is not positive.
@RunWith(AndroidJUnit4::class)
class LauncherIconTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun launcherIconLayersHaveAnIntrinsicSize() {
        for (id in listOf(R.mipmap.ic_launcher, R.mipmap.ic_launcher_round)) {
            val icon = context.getDrawable(id) as AdaptiveIconDrawable
            for (layer in listOf(icon.background, icon.foreground)) {
                assertTrue(layer.intrinsicWidth > 0 && layer.intrinsicHeight > 0)
            }
        }
    }
}
