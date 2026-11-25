package com.example.metchu.ui

import com.example.metchu.Fixtures
import com.example.metchu.data.model.RoomPick
import com.example.metchu.ui.group.chipOrder
import com.example.metchu.ui.group.newestFirst
import org.junit.Assert.assertEquals
import org.junit.Test

/** The order of the group's restaurant chips and the one every phone moves to after a find. */
class ChipOrderTest {

    private val pick = Fixtures.room("room_done").picks!!.first()

    private fun picks(vararg batches: Int, votes: List<Int> = batches.map { 0 }): List<RoomPick> =
        batches.mapIndexed { i, batch -> pick.copy(batch = batch, votes = votes[i]) }

    @Test
    fun theNewestFindComesFirstAndEachFindKeepsTheServersOrder() {
        assertEquals(listOf(4, 2, 3, 0, 1), chipOrder(picks(0, 0, 1, 1, 2)))
    }

    @Test
    fun votesNeverMoveAChip() {
        assertEquals(listOf(2, 0, 1), chipOrder(picks(0, 0, 1, votes = listOf(0, 3, 0))))
    }

    @Test
    fun everyPhoneMovesToTheFirstRestaurantOfTheNewestFind() {
        assertEquals(0, newestFirst(picks(0, 0)))
        assertEquals(2, newestFirst(picks(0, 0, 1, 1)))
        assertEquals(4, newestFirst(picks(0, 0, 1, 1, 2)))
    }

    @Test
    fun anOlderServerWithoutFindsKeepsItsOrder() {
        assertEquals(listOf(0, 1), chipOrder(picks(0, 0)))
        assertEquals(0, newestFirst(emptyList()))
    }
}
