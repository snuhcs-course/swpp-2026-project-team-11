package com.example.metchu.ui.question

import kotlin.math.abs

/** The centers of circles of [sizes] laid out edge to edge across [width] with equal gaps between them. */
fun scaleCenters(width: Float, sizes: List<Float>): List<Float> {
    val gap = (width - sizes.sum()) / (sizes.size - 1)
    var left = 0f
    return sizes.map { size -> (left + size / 2).also { left += size + gap } }
}

/** The index in [allowed] whose center is nearest [x]; null when nothing is allowed. */
fun nearestLevel(x: Float, centers: List<Float>, allowed: List<Int>): Int? = allowed.minByOrNull { abs(centers[it] - x) }
