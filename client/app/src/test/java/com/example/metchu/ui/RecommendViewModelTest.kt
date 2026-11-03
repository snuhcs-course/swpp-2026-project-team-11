package com.example.metchu.ui

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import com.example.metchu.FakeApi
import com.example.metchu.Fixtures
import com.example.metchu.R
import com.example.metchu.data.location.LocationSource
import com.example.metchu.data.model.Allergen
import com.example.metchu.data.model.Ban
import com.example.metchu.data.model.Engine
import com.example.metchu.data.model.Reason
import com.example.metchu.data.model.RestaurantMenu
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.model.Step
import com.example.metchu.data.network.ApiError
import com.example.metchu.data.network.ApiErrorResponse
import com.example.metchu.data.network.RetrofitInstance
import com.example.metchu.data.network.UserLocation
import com.example.metchu.data.repository.RecommendRepository
import com.example.metchu.ui.main.AnsweredQuestion
import com.example.metchu.ui.main.RecommendViewModel
import com.example.metchu.ui.main.UiError
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import java.io.IOException

@OptIn(ExperimentalCoroutinesApi::class)
class RecommendViewModelTest {

    @get:Rule
    val instantTasks = InstantTaskExecutorRule()

    private val api = FakeApi()
    private lateinit var viewModel: RecommendViewModel

    private val question = Fixtures.state("question")
    private val guess = Fixtures.state("guess_food")
    private val groupGuess = Fixtures.state("guess_group")
    private val recommendation = Fixtures.state("recommendation")
    private val unavailable = Fixtures.state("unavailable_empty")

    private val noServer = UiError(R.string.error_no_server, canRetry = true)
    private val serverError = UiError(R.string.error_server, canRetry = true)
    private val sessionLost = UiError(R.string.error_session_lost, canRetry = false)
    private val engineUnavailable = UiError(R.string.error_engine_unavailable, canRetry = false)

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
        viewModel = RecommendViewModel(RecommendRepository(api))
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun startWith(state: SessionState) {
        api.reply(state)
        viewModel.start("LU")
        api.calls.clear()
    }

    /** Answers the question on screen, as the question screen does. */
    private fun answer(answerId: String) = viewModel.answer(answerId, viewModel.session.value!!.step)

    private fun assertIdle(session: SessionState?, error: UiError? = null) {
        assertEquals(false, viewModel.loading.value)
        assertEquals(session, viewModel.session.value)
        assertEquals(error, viewModel.error.value)
    }

    // --- the happy path ---

    @Test
    fun beforeStartThereIsNoSession() {
        assertIdle(null)
        assertEquals(emptyList<String>(), api.calls)
    }

    @Test
    fun startCreatesASessionForTheChosenMeal() {
        api.reply(question)
        viewModel.start("DN")
        assertEquals(listOf("create DN"), api.calls)
        assertIdle(question)
    }

    @Test
    fun startAsksForTheChosenEngine() {
        val llmQuestion = Fixtures.state("question_llm")
        api.reply(llmQuestion)
        viewModel.start("LU", Engine.LLM)
        api.reply(question)
        viewModel.startOver()
        viewModel.start("LU", Engine.DECISION_TREE)
        assertEquals(listOf("create LU llm", "create LU decision_tree"), api.calls)
        assertIdle(question)
    }

    /** An LLM session is driven exactly like a decision-tree one. */
    @Test
    fun anLlmSessionAnswersItsOwnQuestionId() {
        val llmQuestion = Fixtures.state("question_llm")
        api.reply(llmQuestion)
        viewModel.start("LU", Engine.LLM)
        api.reply(guess)
        answer("probably_yes")
        assertEquals("answer ${llmQuestion.sessionId} q:llm-0 probably_yes", api.calls.last())
        assertIdle(guess)
    }

    @Test
    fun startSendsTheAllergies() {
        api.reply(question)
        viewModel.start("LU", Engine.DECISION_TREE, allergies = listOf(Allergen.MILK, Allergen.SHRIMP))
        assertEquals(listOf("create LU decision_tree milk,shrimp"), api.calls)
    }

    @Test
    fun startSendsTheUsersLocationWhenThereIsOne() {
        api.reply(question)
        viewModel.start("LU", Engine.DECISION_TREE, LocationSource { UserLocation(37.45932, 126.95058) })
        assertEquals(listOf("create LU decision_tree @37.45932,126.95058"), api.calls)
    }

    @Test
    fun startSendsTheLocationAndTheAllergiesTogether() {
        api.reply(question)
        viewModel.start("LU", Engine.LLM, LocationSource { UserLocation(37.45932, 126.95058) }, listOf(Allergen.EGG))
        assertEquals(listOf("create LU llm @37.45932,126.95058 egg"), api.calls)
    }

    @Test
    fun findingTheLocationIsPartOfTheStartRequest() {
        val fix = CompletableDeferred<UserLocation?>()
        api.reply(question)
        viewModel.start("LU", Engine.DECISION_TREE, LocationSource { fix.await() })
        assertEquals(true, viewModel.loading.value)
        viewModel.start("LU", Engine.DECISION_TREE)
        assertEquals("A second tap while locating is ignored", emptyList<String>(), api.calls.toList())

        fix.complete(null)
        assertEquals(listOf("create LU decision_tree"), api.calls)
        assertIdle(question)
    }

    @Test
    fun startSendsTheLanguage() {
        api.reply(question)
        viewModel.start("LU", Engine.DECISION_TREE, allergies = listOf(Allergen.EGG), language = "ko")
        assertEquals(listOf("create LU decision_tree egg ko"), api.calls)
    }

    @Test
    fun startForTheWholeDaySendsNoMeal() {
        api.reply(unavailable)
        viewModel.start(null)
        assertEquals(listOf("create null"), api.calls)
        assertIdle(unavailable)
    }

    @Test
    fun answerUsesTheQuestionOnScreen() {
        startWith(question)
        api.reply(guess)
        answer("probably_yes")
        assertEquals(
            listOf("answer ${question.sessionId} ${question.step.questionId} probably_yes"), api.calls
        )
        assertIdle(guess)
    }

    @Test
    fun feedbackUsesTheGuessOnScreen() {
        startWith(groupGuess)
        api.reply(recommendation)
        viewModel.feedback(accepted = true)
        assertEquals(
            listOf("feedback ${groupGuess.sessionId} ${groupGuess.step.guessId} true"), api.calls
        )
        assertIdle(recommendation)

        startWith(guess)
        api.reply(question)
        viewModel.feedback(accepted = false)
        assertEquals(listOf("feedback ${guess.sessionId} ${guess.step.guessId} false"), api.calls)
        assertIdle(question)
    }

    @Test
    fun recommendNowAndUndoCallTheCurrentSession() {
        startWith(question)
        api.reply(guess)
        viewModel.recommendNow()
        api.reply(question)
        viewModel.undo()
        assertEquals(
            listOf("recommend-now ${question.sessionId}", "undo ${guess.sessionId}"), api.calls
        )
        assertIdle(question)
    }

    // --- taps that must not reach the server ---

    @Test
    fun nothingIsSentWithoutASession() {
        viewModel.answer("yes", question.step)
        viewModel.feedback(true)
        viewModel.recommendNow()
        viewModel.undo()
        viewModel.retry()
        assertEquals(emptyList<String>(), api.calls)
        assertIdle(null)
    }

    @Test
    fun answerIsIgnoredWhenTheStepIsNotAQuestion() {
        for (state in listOf(guess, recommendation, unavailable)) {
            startWith(state)
            answer("yes")
            assertEquals(emptyList<String>(), api.calls)
            assertIdle(state)
        }
    }

    @Test
    fun feedbackIsIgnoredWhenTheStepIsNotAGuess() {
        for (state in listOf(question, recommendation, unavailable)) {
            startWith(state)
            viewModel.feedback(true)
            assertEquals(emptyList<String>(), api.calls)
            assertIdle(state)
        }
    }

    @Test
    fun aSecondTapWhileLoadingIsDropped() {
        startWith(question)
        val gate = api.hold()
        answer("yes")
        assertEquals(true, viewModel.loading.value)
        assertSame(question, viewModel.session.value)

        // Everything the user could reach while the first request is in flight.
        answer("no")
        answer("yes")
        viewModel.recommendNow()
        viewModel.undo()
        viewModel.feedback(true)
        viewModel.start("BR")
        viewModel.retry()
        viewModel.startOver()
        assertEquals(1, api.calls.size)
        assertSame(question, viewModel.session.value)

        gate.complete(guess)
        assertIdle(guess)
        assertEquals(1, api.calls.size)
    }

    @Test
    fun loadingIsTrueOnlyWhileTheRequestRuns() {
        val seen = mutableListOf<Boolean>()
        viewModel.loading.observeForever { seen.add(it) }
        val gate = api.hold()
        viewModel.start("LU")
        gate.complete(question)
        assertEquals(listOf(false, true, false), seen)
    }

    // --- failures ---

    @Test
    fun noConnectionShowsARetryableErrorAndKeepsTheScreen() {
        startWith(question)
        api.fail(IOException("Failed to connect to /10.0.2.2:8000"))
        answer("yes")
        assertIdle(question, noServer)
    }

    @Test
    fun retryRepeatsTheFailedRequestExactly() {
        startWith(question)
        api.fail(IOException("timeout"))
        answer("no")
        api.reply(guess)
        viewModel.retry()
        val call = "answer ${question.sessionId} ${question.step.questionId} no"
        assertEquals(listOf(call, call), api.calls)
        assertIdle(guess)
    }

    /** The undo reached the server but its reply was lost: a second undo would skip a step. */
    @Test
    fun retryOfAnUndoThatAlreadyHappenedDoesNotUndoAgain() {
        startWith(guess)
        api.fail(IOException("timeout"))
        viewModel.undo()
        assertIdle(guess, noServer)

        api.reply(question)  // the state read shows the server already went back
        viewModel.retry()
        assertEquals(listOf("undo ${guess.sessionId}", "state ${guess.sessionId}"), api.calls)
        assertIdle(question)
    }

    @Test
    fun retryOfAnUndoThatNeverArrivedSendsItAgain() {
        startWith(guess)
        api.fail(IOException("refused"))
        viewModel.undo()

        api.reply(guess)  // the server is still on the step the screen shows
        api.reply(question)
        viewModel.retry()
        val id = guess.sessionId
        assertEquals(listOf("undo $id", "state $id", "undo $id"), api.calls)
        assertIdle(question)
    }

    /** However often Try again fails, at most one undo is sent per step. */
    @Test
    fun repeatedRetriesOfAnUndoStaySafe() {
        startWith(guess)
        val id = guess.sessionId
        api.fail(IOException("timeout"))
        viewModel.undo()
        api.fail(IOException("still down"))  // the state read fails
        viewModel.retry()
        assertIdle(guess, noServer)
        api.reply(guess)
        api.fail(IOException("timeout"))  // this undo arrives, its reply does not
        viewModel.retry()
        assertIdle(guess, noServer)
        api.reply(question)
        viewModel.retry()
        assertEquals(
            listOf("undo $id", "state $id", "state $id", "undo $id", "state $id"), api.calls
        )
        assertIdle(question)
    }

    @Test
    fun retryOfAnUndoOnALostSessionReturnsToTheStartScreen() {
        startWith(guess)
        api.fail(IOException("timeout"))
        viewModel.undo()
        api.fail(Fixtures.httpError(404, Fixtures.json("error_session_not_found")))
        viewModel.retry()
        assertIdle(null, sessionLost)
    }

    @Test
    fun retryOfAFailedStartCreatesTheSession() {
        api.fail(IOException("refused"))
        viewModel.start("LU")
        assertIdle(null, noServer)
        api.fail(IOException("refused again"))
        viewModel.retry()
        assertIdle(null, noServer)
        api.reply(question)
        viewModel.retry()
        assertEquals(listOf("create LU", "create LU", "create LU"), api.calls)
        assertIdle(question)
    }

    @Test
    fun theNextRequestClearsTheError() {
        startWith(question)
        api.fail(IOException("timeout"))
        viewModel.recommendNow()
        assertEquals(noServer, viewModel.error.value)
        val gate = api.hold()
        viewModel.undo()
        assertNull(viewModel.error.value)
        gate.complete(question)
        assertIdle(question)
    }

    @Test
    fun staleStepRedrawsFromTheServerWithoutAnError() {
        startWith(question)
        api.fail(Fixtures.httpError(409, Fixtures.json("error_stale_step")))
        answer("yes")
        assertEquals(false, viewModel.loading.value)
        assertNull(viewModel.error.value)
        assertEquals(Fixtures.error("error_stale_step").state, viewModel.session.value)
        assertEquals(Step.GUESS, viewModel.session.value!!.step.type)
    }

    @Test
    fun conflictWithoutAUsableStateIsAServerError() {
        val bodies = listOf(
            "", "<html>Conflict</html>", "{\"error\": {\"code\": \"stale_step\", \"message\": \"x\"}}",
            Fixtures.json("error_stale_step").replace("\"step\"", "\"stepp\"")
        )
        for (body in bodies) {
            startWith(question)
            api.fail(Fixtures.httpError(409, body))
            answer("yes")
            assertIdle(question, serverError)
        }
    }

    @Test
    fun lostSessionReturnsToTheStartScreen() {
        startWith(guess)
        api.fail(Fixtures.httpError(404, Fixtures.json("error_session_not_found")))
        viewModel.feedback(true)
        assertIdle(null, sessionLost)

        viewModel.retry()
        assertEquals(1, api.calls.size)

        // Starting again works and clears the message.
        api.reply(question)
        viewModel.start("LU")
        assertIdle(question)
    }

    @Test
    fun anUnavailableEngineStaysOnTheStartScreenWithoutRetry() {
        api.fail(Fixtures.httpError(503, Fixtures.json("error_engine_unavailable")))
        viewModel.start("LU", Engine.LLM)
        assertIdle(null, engineUnavailable)

        viewModel.retry()
        assertEquals(listOf("create LU llm"), api.calls)

        // The other engine still starts, and clears the message.
        api.reply(question)
        viewModel.start("LU", Engine.DECISION_TREE)
        assertIdle(question)
    }

    @Test
    fun anUnavailableRlCatalogueCanBeRecoveredByChoosingAnotherEngine() {
        api.fail(Fixtures.httpError(503, Fixtures.json("error_engine_unavailable")))
        viewModel.start("LU", Engine.RL)
        assertIdle(null, engineUnavailable)
        viewModel.retry()
        api.reply(question)
        viewModel.start("LU", Engine.DECISION_TREE)
        assertEquals(listOf("create LU rl", "create LU decision_tree"), api.calls)
        assertIdle(question)
    }

    @Test
    fun anOlderServerRejectingRlDoesNotRetryTheSameRequest() {
        api.fail(Fixtures.httpError(400, Fixtures.json("error_invalid_request")))
        viewModel.start("LU", Engine.RL)
        assertIdle(null, UiError(R.string.error_session_settings, canRetry = false))
        viewModel.retry()
        assertEquals(listOf("create LU rl"), api.calls)
    }

    /** A 503 that is not about the engine, such as a proxy's, is an ordinary server error. */
    @Test
    fun another503OffersRetry() {
        api.fail(Fixtures.httpError(503, "<html>Service Unavailable</html>"))
        viewModel.start("LU", Engine.LLM)
        assertIdle(null, serverError)
    }

    /** Cloudflare's reply when the tunnel's server has stopped: the server cannot be reached. */
    @Test
    fun aTunnelWithNoServerBehindItIsUnreachable() {
        startWith(question)
        api.fail(Fixtures.httpError(530, "<html>Cloudflare Tunnel error</html>"))
        viewModel.recommendNow()
        assertIdle(question, noServer)
    }

    @Test
    fun otherHttpErrorsKeepTheScreenAndOfferRetry() {
        for (code in listOf(400, 403, 500, 502, 503)) {
            startWith(question)
            api.fail(Fixtures.httpError(code, "<html>error</html>"))
            viewModel.recommendNow()
            assertIdle(question, serverError)
        }
    }

    @Test
    fun aReplyThatCannotBeDrawnIsAnErrorNotACrash() {
        startWith(question)
        val broken = com.example.metchu.data.network.RetrofitInstance.gson.fromJson(
            Fixtures.json("guess_food").replace("\"food\"", "\"dish\""), SessionState::class.java
        )
        api.reply(broken)
        viewModel.recommendNow()
        assertIdle(question, serverError)
    }

    @Test
    fun anUnexpectedExceptionDoesNotLeaveLoadingStuck() {
        startWith(question)
        api.fail(IllegalArgumentException("boom"))
        answer("yes")
        assertIdle(question, serverError)
        api.reply(guess)
        answer("yes")
        assertIdle(guess)
    }

    // --- start over ---

    @Test
    fun startOverLeavesTheSessionAndClearsTheError() {
        startWith(question)
        api.fail(IOException("timeout"))
        answer("yes")
        viewModel.startOver()
        assertIdle(null)
        assertEquals(1, api.calls.size)
    }

    @Test
    fun aNewSessionAfterStartOverUsesTheNewSessionId() {
        startWith(question)
        viewModel.startOver()
        val second = question.copy(sessionId = "second-session")
        api.reply(second)
        viewModel.start("LU")
        api.reply(guess)
        answer("yes")
        assertEquals("answer second-session ${question.step.questionId} yes", api.calls.last())
    }

    @Test
    fun retryAfterStartOverDoesNotReviveTheOldSession() {
        startWith(question)
        api.fail(IOException("timeout"))
        answer("yes")
        viewModel.startOver()
        api.calls.clear()
        viewModel.retry()
        assertEquals(emptyList<String>(), api.calls)
        assertIdle(null)
    }

    // --- question history and shown dishes ---

    /** [question] after [answered] answers, with its own ID and text. */
    private fun questionAt(answered: Int) = question.copy(
        canUndo = answered > 0,
        step = question.step.copy(questionId = "q:$answered", questionCount = answered, text = "Question $answered?")
    )

    private fun answerTo(next: SessionState, answerId: String = "yes") {
        api.reply(next)
        answer(answerId)
    }

    @Test
    fun anAnswerHeldWhileBackMovedTheSessionIsDropped() {
        startWith(questionAt(1))
        val asked = viewModel.session.value!!.step
        api.reply(questionAt(0))
        viewModel.undo()
        viewModel.answer("yes", asked)
        assertEquals(listOf("undo ${question.sessionId}"), api.calls)
        assertIdle(questionAt(0))
    }

    @Test
    fun anAnswerWhoseReplyWasLostStillJoinsTheHistory() {
        startWith(questionAt(0))
        api.fail(IOException("reply lost"))
        answer("no")
        // The server recorded the answer, so Try again finds it on the next question.
        val stale = RetrofitInstance.gson.toJson(
            ApiErrorResponse(ApiError("stale_step", "moved on"), questionAt(1))
        )
        api.fail(Fixtures.httpError(409, stale))
        viewModel.retry()
        assertIdle(questionAt(1))
        assertEquals(listOf(AnsweredQuestion("Question 0?", "no")), viewModel.history.value)

        answerTo(questionAt(2), "yes")
        assertEquals("Question 1?", viewModel.history.value!![1].text)
    }

    @Test
    fun eachAnswerJoinsTheHistoryWithItsQuestionText() {
        startWith(questionAt(0))
        answerTo(questionAt(1), "no")
        answerTo(questionAt(2), "probably_yes")
        assertEquals(
            listOf(AnsweredQuestion("Question 0?", "no"), AnsweredQuestion("Question 1?", "probably_yes")),
            viewModel.history.value
        )
    }

    @Test
    fun undoDropsTheLastAnsweredQuestion() {
        startWith(questionAt(0))
        answerTo(questionAt(1))
        answerTo(questionAt(2))
        api.reply(questionAt(1))
        viewModel.undo()
        assertEquals(listOf(AnsweredQuestion("Question 0?", "yes")), viewModel.history.value)
    }

    @Test
    fun theHistoryNeverOutgrowsTheServersQuestionCount() {
        startWith(questionAt(0))
        // The server says it is still on the first question, for example after a stale step.
        answerTo(questionAt(0))
        assertEquals(emptyList<AnsweredQuestion>(), viewModel.history.value)
    }

    @Test
    fun aRetriedAnswerStillJoinsTheHistory() {
        startWith(questionAt(0))
        api.fail(IOException("timeout"))
        answer("no")
        api.reply(questionAt(1))
        viewModel.retry()
        assertEquals(listOf(AnsweredQuestion("Question 0?", "no")), viewModel.history.value)
    }

    @Test
    fun revisitUndoesUntilTheServerIsOnThatQuestion() {
        startWith(questionAt(0))
        answerTo(questionAt(1))
        answerTo(questionAt(2))
        answerTo(guess.copy(step = guess.step.copy(questionCount = 3)))
        api.calls.clear()
        api.reply(questionAt(2))
        api.reply(questionAt(1))
        viewModel.revisit(1)
        assertEquals(listOf("undo ${question.sessionId}", "undo ${question.sessionId}"), api.calls.toList())
        assertEquals(questionAt(1), viewModel.session.value)
        assertEquals(listOf(AnsweredQuestion("Question 0?", "yes")), viewModel.history.value)
    }

    @Test
    fun revisitStopsWhenThereIsNothingLeftToUndo() {
        startWith(questionAt(1))
        api.reply(questionAt(0))
        viewModel.revisit(0)
        assertEquals(listOf("undo ${question.sessionId}"), api.calls.toList())
        assertEquals(questionAt(0), viewModel.session.value)
    }

    @Test
    fun aRetriedRevisitReadsTheServerBeforeUndoingAgain() {
        startWith(questionAt(0))
        answerTo(questionAt(1))
        answerTo(questionAt(2))
        api.calls.clear()
        api.fail(IOException("timeout"))
        viewModel.revisit(0)
        // The undo may have arrived: the server is already on question 1.
        api.reply(questionAt(1))
        api.reply(questionAt(0))
        viewModel.retry()
        assertEquals(
            listOf("undo ${question.sessionId}", "state ${question.sessionId}", "undo ${question.sessionId}"),
            api.calls.toList()
        )
        assertEquals(questionAt(0), viewModel.session.value)
    }

    @Test
    fun eachGuessIsShownOnceAndANewSessionForgetsThem() {
        startWith(guess)
        api.reply(questionAt(1))
        viewModel.feedback(accepted = false)
        api.reply(groupGuess)
        answer("yes")
        api.reply(groupGuess)
        viewModel.recommendNow()
        assertEquals(listOf(guess.step, groupGuess.step), viewModel.shown.value)

        api.reply(question)
        viewModel.start("LU")
        assertEquals(emptyList<Step>(), viewModel.shown.value)
        assertEquals(emptyList<AnsweredQuestion>(), viewModel.history.value)
    }

    @Test
    fun startOverForgetsTheHistory() {
        startWith(questionAt(0))
        answerTo(questionAt(1))
        viewModel.startOver()
        assertEquals(emptyList<AnsweredQuestion>(), viewModel.history.value)
        assertEquals(emptyList<Step>(), viewModel.shown.value)
    }

    // --- the reason under a proposed dish ---

    @Test
    fun aProposedDishGetsItsReasonOnce() {
        val food = guess.step.food!!
        api.reason = Reason(food.foodId, "Spicy, as you wanted.")
        startWith(question)
        assertEquals(emptyList<String>(), api.reasonCalls.toList())
        answerTo(guess)
        assertEquals(mapOf(guess.step.guessId to "Spicy, as you wanted."), viewModel.reasons.value)

        api.reply(question)
        viewModel.undo()
        answerTo(guess)
        assertEquals(listOf(guess.sessionId), api.reasonCalls.toList())
    }

    @Test
    fun changingAnAnswerReplacesTheReasonAndIgnoresALateReply() {
        val target = guess.copy(step = guess.step.copy(questionCount = 1))
        val food = target.step.food!!
        val old = CompletableDeferred<Reason>()
        api.heldReason = old
        startWith(question)
        answerTo(target, "yes")
        api.reply(question)
        viewModel.undo()
        api.reason = Reason(food.foodId, "Available at this restaurant.")
        answerTo(target, "any")
        old.complete(Reason(food.foodId, "Because you wanted chicken."))
        assertEquals(2, api.reasonCalls.size)
        assertEquals("Available at this restaurant.", viewModel.reasons.value!![target.step.guessId])
    }

    @Test
    fun aReasonBeingWrittenIsHeldAsNull() {
        val held = CompletableDeferred<Reason>()
        api.heldReason = held
        startWith(question)
        answerTo(guess)
        assertEquals(mapOf(guess.step.guessId to null), viewModel.reasons.value)

        held.complete(Reason(guess.step.food!!.foodId, "Spicy, as you wanted."))
        assertEquals(mapOf(guess.step.guessId to "Spicy, as you wanted."), viewModel.reasons.value)
    }

    @Test
    fun aReasonForAnotherDishIsLeftOut() {
        api.reason = Reason(guess.step.food!!.foodId + 1, "Spicy, as you wanted.")
        startWith(question)
        answerTo(guess)
        assertEquals(emptyMap<String, String?>(), viewModel.reasons.value)
    }

    @Test
    fun aFailedReasonIsLeftOutWithoutAnError() {
        startWith(question)
        answerTo(guess)
        assertEquals(listOf(guess.sessionId), api.reasonCalls.toList())
        assertEquals(emptyMap<String, String?>(), viewModel.reasons.value)
        assertIdle(guess)
    }

    // --- banning a dish or a group for the session ---

    @Test
    fun aBanLastsUntilTheSessionEnds() {
        val dish = Ban(foodId = guess.step.food!!.foodId)
        val group = Ban(foodGroup = "국수")
        startWith(guess)
        api.reply(guess)
        viewModel.ban(dish, true)
        api.reply(guess)
        viewModel.ban(group, true)
        assertEquals(listOf("ban ${guess.sessionId} ${dish.foodId} true", "ban ${guess.sessionId} 국수 true"), api.calls)
        assertEquals(setOf(dish, group), viewModel.banned.value)
        assertIdle(guess)

        api.reply(guess)
        viewModel.ban(dish, false)
        assertEquals(setOf(group), viewModel.banned.value)

        viewModel.startOver()
        assertEquals(emptySet<Ban>(), viewModel.banned.value)
    }

    @Test
    fun aFailedBanIsNotRememberedAndTryAgainSendsIt() {
        val group = Ban(foodGroup = "국수")
        startWith(guess)
        api.fail(IOException("offline"))
        viewModel.ban(group, true)
        assertIdle(guess, noServer)
        assertEquals(emptySet<Ban>(), viewModel.banned.value)

        api.reply(guess)
        viewModel.retry()
        assertEquals(setOf(group), viewModel.banned.value)
        assertEquals(2, api.calls.size)
    }

    // --- the menu of a cafeteria ---

    @Test
    fun aMenuLoadsOnceAndStartOverForgetsIt() {
        val menu = Fixtures.menu()
        api.menu = menu
        startWith(guess)
        viewModel.menu(menu.restaurant)
        viewModel.menu(menu.restaurant)
        assertEquals(listOf("${guess.sessionId} ${menu.restaurant}"), api.menuCalls.toList())
        assertEquals(mapOf(menu.restaurant to menu.dishes), viewModel.menus.value)
        assertIdle(guess)

        viewModel.startOver()
        assertEquals(emptyMap<String, Any?>(), viewModel.menus.value)
    }

    @Test
    fun aFailedMenuLeavesNoEntrySoItCanBeAskedAgain() {
        startWith(guess)
        viewModel.menu("220동식당")
        assertEquals(emptyMap<String, Any?>(), viewModel.menus.value)
        assertIdle(guess)

        // A reply Gson half-filled is a failure too.
        api.menu = RetrofitInstance.gson.fromJson("""{"dishes": [{"food_id": 1}]}""", RestaurantMenu::class.java)
        viewModel.menu("220동식당")
        assertEquals(emptyMap<String, Any?>(), viewModel.menus.value)

        api.menu = Fixtures.menu()
        viewModel.menu("220동식당")
        assertEquals(3, api.menuCalls.size)
        assertEquals(Fixtures.menu().dishes, viewModel.menus.value!!["220동식당"])
    }

    @Test
    fun startOverForgetsTheReasons() {
        api.reason = Reason(guess.step.food!!.foodId, "Spicy, as you wanted.")
        startWith(guess)
        viewModel.startOver()
        assertEquals(emptyMap<String, String?>(), viewModel.reasons.value)
        startWith(guess)
        assertEquals(2, api.reasonCalls.size)
    }
}
