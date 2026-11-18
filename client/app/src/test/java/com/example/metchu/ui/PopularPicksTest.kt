package com.example.metchu.ui

import com.example.metchu.Fixtures
import com.example.metchu.data.model.RoomState
import com.example.metchu.ui.group.popularPicks
import org.junit.Assert.assertEquals
import org.junit.Test

/** Which restaurant chips carry the "popular" badge. */
class PopularPicksTest {

    private val done = Fixtures.room("room_done")

    private fun withVotes(vararg votes: Int, decided: Int? = null): RoomState {
        val pick = done.picks!!.first()
        return done.copy(picks = votes.map { pick.copy(votes = it) }, decided = decided)
    }

    @Test
    fun theMostVotedPickIsPopular() {
        assertEquals(setOf(1), popularPicks(withVotes(1, 3)))
    }

    @Test
    fun everyPickTiedForTheMostIsPopular() {
        assertEquals(setOf(0, 2), popularPicks(withVotes(2, 1, 2)))
    }

    @Test
    fun noBadgeWithoutVotesOrWithOnePickOrOnceDecided() {
        assertEquals(emptySet<Int>(), popularPicks(withVotes(0, 0)))
        assertEquals(emptySet<Int>(), popularPicks(withVotes(3)))
        assertEquals(emptySet<Int>(), popularPicks(withVotes(1, 3, decided = 1)))
    }
}
