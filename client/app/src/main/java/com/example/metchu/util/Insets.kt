package com.example.metchu.util

import android.view.View
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

/**
 * targetSdk 36 is always edge-to-edge, so the system draws the status bar, the
 * navigation bar and the camera cutout on top of the layout. This pads the view by
 * whatever the system is covering, plus the caller's own padding.
 */
fun View.padForSystemBars(extra: Int = 0) {
    ViewCompat.setOnApplyWindowInsetsListener(this) { v, windowInsets ->
        val i = windowInsets.getInsets(
            WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
        )
        v.setPadding(i.left + extra, i.top + extra, i.right + extra, i.bottom + extra)
        WindowInsetsCompat.CONSUMED
    }
}
