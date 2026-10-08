package com.example.metchu.data

import com.example.metchu.Fixtures
import com.example.metchu.data.model.Engine
import com.example.metchu.data.model.Step
import com.example.metchu.data.network.RetrofitInstance
import com.example.metchu.data.repository.RecommendRepository
import com.google.gson.JsonParser
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import retrofit2.HttpException
import java.io.IOException

/** Real Retrofit and Gson against a local fake server: what actually goes over the wire. */
class RecommendRepositoryTest {

    private val server = MockWebServer()
    private lateinit var repository: RecommendRepository

    @Before
    fun setUp() {
        server.start()
        repository = RecommendRepository(RetrofitInstance.create(server.url("/").toString()))
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun reply(fixture: String, code: Int = 200) {
        server.enqueue(MockResponse().setResponseCode(code).setBody(Fixtures.json(fixture)))
    }

    private fun RecordedRequest.json() = JsonParser().parse(body.readUtf8()).asJsonObject

    @Test
    fun createSessionSendsTheMeal() = runTest {
        reply("question", 201)
        val state = repository.createSession("LU")
        assertEquals(Step.QUESTION, state.step.type)

        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/sessions/", request.path)
        assertTrue(request.getHeader("Content-Type")!!.startsWith("application/json"))
        assertEquals("""{"meal":"LU"}""", request.json().toString())
    }

    @Test
    fun createSessionSendsTheChosenEngine() = runTest {
        reply("question_llm", 201)
        val state = repository.createSession("LU", Engine.LLM)
        assertEquals(Engine.LLM, state.engine)
        assertEquals("""{"meal":"LU","engine":"llm"}""", server.takeRequest().json().toString())
    }

    /** The server refuses the LLM engine when it has no API key; the body says so. */
    @Test
    fun engineUnavailableBodyIsDecoded() = runTest {
        reply("error_engine_unavailable", 503)
        try {
            repository.createSession("LU", Engine.LLM)
            fail("Expected an HttpException")
        } catch (e: HttpException) {
            assertEquals(503, e.code())
            assertEquals("engine_unavailable", repository.errorBody(e)!!.error!!.code)
        }
    }

    /** Whole day: the field is left out, which the server reads as "no meal filter". */
    @Test
    fun createSessionForTheWholeDayOmitsTheMeal() = runTest {
        reply("unavailable_empty", 201)
        repository.createSession(null)
        assertEquals("{}", server.takeRequest().json().toString())
    }

    @Test
    fun stateReadsTheSessionWithoutChangingIt() = runTest {
        reply("guess_food")
        val state = repository.state("abc")
        assertEquals(Step.GUESS, state.step.type)

        val request = server.takeRequest()
        assertEquals("GET", request.method)
        assertEquals("/api/sessions/abc/", request.path)
    }

    @Test
    fun answerSendsQuestionAndAnswerIds() = runTest {
        reply("question")
        repository.answer("abc", "q:soupy", "probably_no")
        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/sessions/abc/answer/", request.path)
        assertEquals("""{"question_id":"q:soupy","answer_id":"probably_no"}""", request.json().toString())
    }

    @Test
    fun feedbackSendsARealBoolean() = runTest {
        reply("recommendation")
        reply("question")
        repository.feedback("abc", "group:0123abcd", true)
        repository.feedback("abc", "food:17", false)

        val accepted = server.takeRequest()
        assertEquals("/api/sessions/abc/feedback/", accepted.path)
        assertEquals("""{"guess_id":"group:0123abcd","accepted":true}""", accepted.json().toString())
        assertEquals("""{"guess_id":"food:17","accepted":false}""", server.takeRequest().json().toString())
    }

    @Test
    fun recommendNowAndUndoPostToTheirOwnPaths() = runTest {
        reply("guess_food")
        reply("question")
        repository.recommendNow("abc")
        repository.undo("abc")
        val first = server.takeRequest()
        val second = server.takeRequest()
        assertEquals("POST /api/sessions/abc/recommend-now/", "${first.method} ${first.path}")
        assertEquals("POST /api/sessions/abc/undo/", "${second.method} ${second.path}")
    }

    @Test
    fun koreanNamesSurviveTheRoundTrip() = runTest {
        reply("guess_group")
        val step = repository.recommendNow("abc").step
        assertEquals("국수", step.group!!.displayName)
        assertEquals("냉모밀", step.food!!.displayName)
    }

    @Test
    fun staleStepIsAnHttpErrorCarryingTheCurrentState() = runTest {
        reply("error_stale_step", 409)
        try {
            repository.answer("abc", "q:rice", "yes")
            fail("Expected HttpException")
        } catch (e: HttpException) {
            assertEquals(409, e.code())
            val body = repository.errorBody(e)!!
            assertEquals("stale_step", body.error!!.code)
            assertEquals(Step.GUESS, body.state!!.step.type)
        }
    }

    @Test
    fun errorBodyThatIsNotOursIsNull() {
        for (body in listOf("<html><h1>Server Error (500)</h1></html>", "", "[1, 2]", "\"text\"", "{")) {
            assertNull(body, repository.errorBody(Fixtures.httpError(500, body)))
        }
    }

    @Test
    fun errorBodyDropsAStateThatWouldCrashTheScreen() {
        val broken = Fixtures.json("error_stale_step").replace("\"step\"", "\"stepp\"")
        val body = repository.errorBody(Fixtures.httpError(409, broken))!!
        assertEquals("stale_step", body.error!!.code)
        assertNull(body.state)
    }

    @Test
    fun aSuccessReplyThatIsNotASessionIsAnError() = runTest {
        for (body in listOf("{}", "{\"session_id\": \"abc\"}", "null", "<html></html>", "")) {
            server.enqueue(MockResponse().setResponseCode(200).setBody(body))
            try {
                repository.undo("abc")
                fail("Expected a failure for body: $body")
            } catch (e: Exception) {
                // IllegalStateException from checked(), a Gson syntax error, or a null body.
                assertTrue(body, e !is HttpException)
            }
        }
    }

    @Test
    fun aDroppedConnectionIsAnIoException() = runTest {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))
        try {
            repository.createSession("LU")
            fail("Expected IOException")
        } catch (e: IOException) {
            // expected
        }
    }
}
