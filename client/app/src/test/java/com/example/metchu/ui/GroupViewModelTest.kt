package com.example.metchu.ui

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import com.example.metchu.FakeRoomApi
import com.example.metchu.Fixtures
import com.example.metchu.R
import com.example.metchu.data.model.AnswerId
import com.example.metchu.data.model.Allergen
import com.example.metchu.data.model.RoomQuestion
import com.example.metchu.data.repository.RoomRepository
import com.example.metchu.ui.group.GroupViewModel
import com.example.metchu.ui.main.AnsweredQuestion
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestCoroutineScheduler
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class GroupViewModelTest {

    @get:Rule
    val instantTasks = InstantTaskExecutorRule()

    private val scheduler = TestCoroutineScheduler()
    private val api = FakeRoomApi()
    private lateinit var viewModel: GroupViewModel

    private val created = Fixtures.roomReply("room_created")
    private val asking = Fixtures.room("room_asking")
    private val code = created.state.code

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher(scheduler))
        viewModel = GroupViewModel(RoomRepository(api))
    }

    @After
    fun tearDown() {
        viewModel.leave()
        Dispatchers.resetMain()
    }

    private fun create() {
        api.reply(created)
        viewModel.create(null, "지민", listOf(Allergen.EGG), "ko", "LU", { null }, "any")
    }

    @Test
    fun aGuestCreatesARoomUnderTheirName() {
        create()
        assertEquals("create null 지민", api.calls.single())
        assertEquals(code, viewModel.room.value!!.code)
    }

    @Test
    fun theRoomCarriesThePriceRange() {
        api.reply(created)
        viewModel.create(null, "지민", emptyList(), "ko", "LU", { null }, "near", priceLevel = 2)
        assertEquals(2, api.lastCreateRequest?.priceLevel)
        create()
        assertNull(api.lastCreateRequest?.priceLevel)
    }

    @Test
    fun theRoomCarriesTheRoundTime() {
        api.reply(created)
        viewModel.create(null, "지민", emptyList(), "ko", "LU", { null }, "any", roundSeconds = 30)
        assertEquals(30, api.lastCreateRequest?.roundSeconds)
        create()
        assertEquals(15, api.lastCreateRequest?.roundSeconds)
    }

    @Test
    fun aSignedInMemberSendsTheAccountInsteadOfAName() {
        api.reply(created)
        viewModel.join("device-token", code, "ignored", emptyList(), "ko")
        assertEquals("join Token device-token $code null", api.calls.single())
    }

    @Test
    fun actionsCarryTheMemberToken() {
        create()
        api.reply(asking)
        viewModel.start()
        api.reply(asking)
        viewModel.answer(AnswerId.YES)
        assertEquals(
            listOf("start $code member-token", "answer $code member-token ${asking.question!!.questionId} yes"),
            api.calls.drop(1)
        )
    }

    @Test
    fun theRoomIsPolledEverySecond() {
        create()
        api.reply(asking)
        scheduler.advanceTimeBy(1001)
        assertEquals("state $code member-token", api.calls.last())
        assertEquals(asking, viewModel.room.value)
    }

    @Test
    fun aMemberWhoBecomesHostIsToldUntilTheNextRequest() {
        val lobby = Fixtures.room("room_lobby")
        api.reply(created.copy(state = lobby))
        viewModel.join(null, code, "서연", emptyList(), "ko")
        api.reply(lobby)
        scheduler.advanceTimeBy(1001)
        assertNull(viewModel.error.value)
        api.reply(lobby.copy(host = lobby.me))
        scheduler.advanceTimeBy(1000)
        assertEquals(R.string.group_now_host, viewModel.error.value!!.message)
        assertTrue(viewModel.room.value!!.isHost)
        api.reply(asking)
        viewModel.start()
        assertNull(viewModel.error.value)
    }

    @Test
    fun leavingClearsTheNewHostNotice() {
        val lobby = Fixtures.room("room_lobby")
        api.reply(created.copy(state = lobby))
        viewModel.join(null, code, "서연", emptyList(), "ko")
        api.reply(lobby.copy(host = lobby.me))
        scheduler.advanceTimeBy(1001)
        assertEquals(R.string.group_now_host, viewModel.error.value!!.message)
        viewModel.leave()
        assertNull(viewModel.error.value)
    }

    @Test
    fun aFinishedRoundGoesIntoTheHistoryWithTheAnswerOrNotSure() {
        create()
        api.reply(asking)
        scheduler.advanceTimeBy(1001)
        val next = asking.copy(round = 1, myAnswer = null, question = RoomQuestion("q:spicy", "매운 음식이 먹고 싶어요?", asking.question!!.options))
        api.reply(next)
        scheduler.advanceTimeBy(1000)
        api.reply(next.copy(round = 2, question = RoomQuestion("q:meat", "고기?", next.question!!.options)))
        scheduler.advanceTimeBy(1000)
        assertEquals(
            listOf(AnsweredQuestion(asking.question!!.text, AnswerId.YES), AnsweredQuestion("매운 음식이 먹고 싶어요?", AnswerId.UNKNOWN)),
            viewModel.history.value
        )
    }

    @Test
    fun anAnswerThatEndsTheRoundStaysInTheHistory() {
        create()
        api.reply(asking.copy(myAnswer = null))
        scheduler.advanceTimeBy(1001)
        api.reply(asking.copy(round = 1, myAnswer = null, question = RoomQuestion("q:spicy", "매운 음식이 먹고 싶어요?", asking.question!!.options)))
        viewModel.answer(AnswerId.NO)
        assertEquals(listOf(AnsweredQuestion(asking.question!!.text, AnswerId.NO)), viewModel.history.value)
    }

    @Test
    fun aMemberVotesByPositionAndSeesTheCount() {
        create()
        val done = Fixtures.room("room_done").let { it.copy(decided = null, picks = it.picks!!.map { p -> p.copy(votes = 0, voted = false) }) }
        api.reply(done)
        scheduler.advanceTimeBy(1001)
        assertFalse(viewModel.room.value!!.picks!![1].voted)

        val voted = done.copy(picks = done.picks!!.mapIndexed { i, p -> if (i == 1) p.copy(votes = 1, voted = true) else p })
        api.reply(voted)
        viewModel.vote(1, true)
        assertEquals("vote $code member-token 1 true", api.calls.last())
        assertEquals(1, viewModel.room.value!!.picks!![1].votes)
        assertTrue(viewModel.room.value!!.picks!![1].voted)
    }

    @Test
    fun goHereRightAfterAVoteGoesOutAndTheVotesLateReplyIsDropped() {
        create()
        val done = Fixtures.room("room_done").copy(decided = null)
        val vote = api.hold()
        viewModel.vote(1, true)
        api.reply(done.copy(decided = 1))
        viewModel.decide(1)
        assertEquals("decide $code member-token 1", api.calls.last())
        vote.complete(done)
        assertEquals(1, viewModel.room.value!!.decided)
    }

    @Test
    fun theHostDecidesByPosition() {
        create()
        api.reply(Fixtures.room("room_done"))
        viewModel.decide(1)
        assertEquals("decide $code member-token 1", api.calls.last())
    }

    @Test
    fun theHostAsksForOtherRestaurants() {
        create()
        val done = Fixtures.room("room_done").copy(decided = null, more = true)
        val other = done.copy(picks = done.picks!!.reversed(), more = false)
        api.reply(other)
        viewModel.another()
        assertEquals("another $code member-token", api.calls.last())
        assertEquals(other, viewModel.room.value)
    }

    @Test
    fun aPollSentBeforeFindAnotherCannotBringTheOldRestaurantsBack() {
        create()
        val done = Fixtures.room("room_done").copy(decided = null, more = true)
        val other = done.copy(picks = done.picks!!.reversed(), more = false)
        val late = api.hold()
        scheduler.advanceTimeBy(1001)
        assertEquals("state $code member-token", api.calls.last())
        api.reply(other)
        viewModel.another()
        late.complete(done)
        assertEquals(other, viewModel.room.value)
    }

    @Test
    fun tooManyWrongCodesSaySo() {
        api.fail(Fixtures.httpError(429, """{"error": {"code": "too_many_attempts", "message": "wait"}}"""))
        viewModel.join(null, "0000", "서연", emptyList(), "ko")
        assertEquals(R.string.group_error_attempts, viewModel.error.value!!.message)
    }

    @Test
    fun anUnknownCodeSaysSo() {
        api.fail(Fixtures.httpError(404, Fixtures.json("error_room_not_found")))
        viewModel.join(null, "0000", "서연", emptyList(), "ko")
        assertNull(viewModel.room.value)
        assertEquals(R.string.group_error_not_found, viewModel.error.value!!.message)
    }

    @Test
    fun aStaleAnswerWaitsForTheNextPoll() {
        create()
        api.reply(asking)
        scheduler.advanceTimeBy(1001)
        api.fail(Fixtures.httpError(409, """{"error": {"code": "stale_step", "message": "late"}}"""))
        viewModel.answer(AnswerId.NO)
        assertNull(viewModel.error.value)
        assertEquals(asking, viewModel.room.value)
    }

    @Test
    fun aRoomThatIsGoneTakesThePhoneBackToTheStart() {
        create()
        api.fail(Fixtures.httpError(403, """{"error": {"code": "not_member", "message": "gone"}}"""))
        scheduler.advanceTimeBy(1001)
        assertNull(viewModel.room.value)
        assertEquals(R.string.group_error_gone, viewModel.error.value!!.message)
    }

    @Test
    fun leavingTellsTheServerAndStopsPolling() {
        create()
        viewModel.leave()
        assertNull(viewModel.room.value)
        assertEquals("leave $code member-token", api.calls.last())
        scheduler.advanceTimeBy(5000)
        assertEquals("leave $code member-token", api.calls.last())
    }
}
