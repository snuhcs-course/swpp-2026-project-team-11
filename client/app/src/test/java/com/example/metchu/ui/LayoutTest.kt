package com.example.metchu.ui

import com.example.metchu.ui.question.nearestLevel
import com.example.metchu.ui.question.scaleCenters
import com.example.metchu.ui.result.SheetStop.FULL
import com.example.metchu.ui.result.SheetStop.HALF
import com.example.metchu.ui.result.SheetStop.PEEK
import com.example.metchu.ui.result.draggedStop
import com.example.metchu.ui.result.sheetStops
import com.example.metchu.ui.result.tappedStop
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class AnswerScaleTest {

    @Test
    fun circlesSpanTheWidthWithEqualGaps() {
        // 20 + 10 gap + 40 + 10 gap + 20 = 100.
        assertEquals(listOf(10f, 50f, 90f), scaleCenters(100f, listOf(20f, 40f, 20f)))
    }

    @Test
    fun theFingerPicksTheNearestOfferedAnswer() {
        val centers = listOf(10f, 50f, 90f)
        assertEquals(1, nearestLevel(45f, centers, listOf(0, 1, 2)))
        assertEquals(2, nearestLevel(75f, centers, listOf(0, 2)))
        assertNull(nearestLevel(45f, centers, emptyList()))
    }
}

class SheetStopsTest {

    @Test
    fun oneCafeteriaHasNoFullStop() {
        assertEquals(listOf(HALF, PEEK), sheetStops(1))
        assertEquals(listOf(FULL, HALF, PEEK), sheetStops(3))
    }

    @Test
    fun aTapGoesUpAndComesBackToHalf() {
        val all = sheetStops(2)
        assertEquals(HALF, tappedStop(all, PEEK))
        assertEquals(FULL, tappedStop(all, HALF))
        assertEquals(HALF, tappedStop(all, FULL))
        assertEquals(PEEK, tappedStop(sheetStops(1), HALF))
    }

    @Test
    fun aLongDragMovesOneStopAndAShortOneSettlesNearest() {
        val all = sheetStops(2)
        assertEquals(PEEK, draggedStop(all, HALF, HALF, down = true, far = true))
        assertEquals(FULL, draggedStop(all, HALF, HALF, down = false, far = true))
        assertEquals(HALF, draggedStop(all, HALF, HALF, down = true, far = false))
        assertEquals(FULL, draggedStop(all, HALF, FULL, down = false, far = false))
        // Past the last stop it stays.
        assertEquals(PEEK, draggedStop(all, PEEK, PEEK, down = true, far = true))
    }
}
