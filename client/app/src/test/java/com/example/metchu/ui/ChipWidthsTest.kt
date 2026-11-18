package com.example.metchu.ui

import com.example.metchu.ui.group.chipWidths
import org.junit.Assert.assertEquals
import org.junit.Test

/** How the restaurant chips share the row. */
class ChipWidthsTest {

    @Test
    fun chipsThatFitKeepTheirWidth() {
        assertEquals(listOf(90, 120), chipWidths(listOf(90, 120), free = 300))
    }

    @Test
    fun aShortChipLeavesItsRoomToTheLongOne() {
        // An even split would cut the long name at 150 though 210 is free beside the short one.
        assertEquals(listOf(90, 210), chipWidths(listOf(90, 260), free = 300))
        assertEquals(listOf(210, 90), chipWidths(listOf(260, 90), free = 300))
    }

    @Test
    fun twoLongChipsShareTheRowEvenly() {
        assertEquals(listOf(150, 150), chipWidths(listOf(400, 260), free = 300))
    }

    @Test
    fun aSingleChipTakesUpToTheWholeRow() {
        assertEquals(listOf(120), chipWidths(listOf(120), free = 300))
        assertEquals(listOf(300), chipWidths(listOf(500), free = 300))
    }
}
