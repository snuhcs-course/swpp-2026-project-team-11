package com.example.metchu.data

import com.example.metchu.Fixtures
import com.example.metchu.data.model.RoomState
import com.example.metchu.data.network.RoomApi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The server's real room JSON decodes into the fields the group screens read. */
class RoomContractJsonTest {

    @Test
    fun created() {
        val reply = Fixtures.roomReply("room_created")
        assertEquals("member-token", reply.token)
        assertEquals(RoomState.LOBBY, reply.state.status)
        assertTrue(reply.state.code.matches(Regex("\\d{4}")))
        assertTrue(reply.state.isHost)
        assertEquals(listOf("egg"), reply.state.members.single().allergies)
    }

    @Test
    fun lobbySeenByAGuest() {
        val room = Fixtures.room("room_lobby")
        assertFalse(room.isHost)
        assertEquals(listOf("지민", "서연"), room.members.map { it.name })
        assertNull(room.question)
        assertNull(room.secondsLeft)
    }

    @Test
    fun asking() {
        val room = Fixtures.room("room_asking")
        assertEquals(RoomState.ASKING, room.status)
        val question = room.question!!
        assertTrue(question.questionId.startsWith("q:"))
        assertEquals(listOf("yes", "probably_yes", "any", "probably_no", "no", "unknown"), question.options.map { it.id })
        assertEquals("yes", room.myAnswer)
        assertEquals(listOf(true, false), room.members.map { it.answered })
        assertEquals(12.0, room.secondsLeft!!, 0.01)
        assertEquals(15, room.roundSeconds)
        assertEquals(4, room.maxRounds)
    }

    @Test
    fun decided() {
        val room = Fixtures.room("room_done")
        assertEquals(RoomState.DONE, room.status)
        val picks = room.picks!!
        assertTrue(picks.size in 1..2)
        assertEquals(0, room.decided)
        assertEquals(listOf("balanced", "no_one_unhappy"), picks.map { it.kind })
        assertTrue(picks.first().others.isNotEmpty())
        for (pick in picks) {
            assertEquals(listOf(0, 1), pick.menus.map { it.memberId })
            assertTrue(pick.menus.all { it.fit in setOf("great", "good") })
            assertTrue(pick.others.none { other -> pick.menus.any { it.food.foodId == other.foodId } })
            assertTrue(pick.menus.all { dish -> dish.food.offers.any { it.restaurant == pick.restaurant } })
        }
    }

    @Test
    fun unknownCode() {
        assertEquals(RoomApi.ROOM_NOT_FOUND, Fixtures.error("error_room_not_found").error!!.code)
    }
}
