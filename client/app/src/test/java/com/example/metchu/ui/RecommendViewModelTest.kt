package com.example.metchu.ui

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import com.example.metchu.FakeApi
import com.example.metchu.Fixtures
import com.example.metchu.R
import com.example.metchu.data.model.Engine
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.model.Step
import com.example.metchu.data.repository.RecommendRepository
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
        viewModel.answer("probably_yes")
        assertEquals("answer ${llmQuestion.sessionId} q:llm-0 probably_yes", api.calls.last())
        assertIdle(guess)
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
        viewModel.answer("probably_yes")
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
        viewModel.answer("yes")
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
            viewModel.answer("yes")
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
        viewModel.answer("yes")
        assertEquals(true, viewModel.loading.value)
        assertSame(question, viewModel.session.value)

        // Everything the user could reach while the first request is in flight.
        viewModel.answer("no")
        viewModel.answer("yes")
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
        viewModel.answer("yes")
        assertIdle(question, noServer)
    }

    @Test
    fun retryRepeatsTheFailedRequestExactly() {
        startWith(question)
        api.fail(IOException("timeout"))
        viewModel.answer("no")
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
        viewModel.answer("yes")
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
            viewModel.answer("yes")
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

    /** A 503 that is not about the engine, such as a proxy's, is an ordinary server error. */
    @Test
    fun another503OffersRetry() {
        api.fail(Fixtures.httpError(503, "<html>Service Unavailable</html>"))
        viewModel.start("LU", Engine.LLM)
        assertIdle(null, serverError)
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
        viewModel.answer("yes")
        assertIdle(question, serverError)
        api.reply(guess)
        viewModel.answer("yes")
        assertIdle(guess)
    }

    // --- start over ---

    @Test
    fun startOverLeavesTheSessionAndClearsTheError() {
        startWith(question)
        api.fail(IOException("timeout"))
        viewModel.answer("yes")
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
        viewModel.answer("yes")
        assertEquals("answer second-session ${question.step.questionId} yes", api.calls.last())
    }

    @Test
    fun retryAfterStartOverDoesNotReviveTheOldSession() {
        startWith(question)
        api.fail(IOException("timeout"))
        viewModel.answer("yes")
        viewModel.startOver()
        api.calls.clear()
        viewModel.retry()
        assertEquals(emptyList<String>(), api.calls)
        assertIdle(null)
    }
}
