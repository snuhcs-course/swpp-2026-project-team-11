package com.example.metchu.ui.question

import androidx.annotation.StringRes
import com.example.metchu.R
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

/**
 * How full the progress bar is after [answered] answers: quickly at first, then less
 * with each answer, so it feels closer to the end without promising a count. With a
 * question cap the bar is never behind answered / cap. It stops at 95 % until a dish is found.
 */
fun progressFill(answered: Int, maxQuestions: Int?): Float {
    val curve = 1f - 0.72f.pow(answered)
    val capped = maxQuestions?.let { answered.toFloat() / it } ?: 0f
    return min(MAX_FILL, max(curve, capped))
}

@StringRes
fun phaseText(fill: Float): Int = when {
    fill < 0.3f -> R.string.phase_start
    fill < 0.75f -> R.string.phase_narrowing
    else -> R.string.phase_almost
}

private const val MAX_FILL = 0.95f
