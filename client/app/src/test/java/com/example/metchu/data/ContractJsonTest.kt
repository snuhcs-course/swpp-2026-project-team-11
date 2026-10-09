// AI-generated: written with Claude (Anthropic) and reviewed by the team.
package com.example.metchu.data

import com.example.metchu.Fixtures
import com.example.metchu.data.model.Engine
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.model.Step
import com.example.metchu.data.network.ApiError
import com.example.metchu.data.network.RetrofitInstance
import com.example.metchu.data.repository.checked
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

/** The server's real JSON decodes into the fields the screen reads. */
class ContractJsonTest {

    @Test
    fun question() {
        val state = Fixtures.state("question").checked()
        assertEquals(Engine.DECISION_TREE, state.engine)
        assertEquals("2026-09-29", state.date)
        assertEquals("LU", state.meal)
        assertEquals(193, state.candidateCount)
        assertEquals(10, state.maxQuestions)
        assertFalse(state.canUndo)
        assertTrue(state.sessionId.isNotEmpty())

        val step = state.step
        assertEquals(Step.QUESTION, step.type)
        assertEquals(0, step.questionCount)
        assertTrue(step.questionId!!.startsWith("q:"))
        assertTrue(step.text.isNotBlank())
        assertEquals(
            listOf("yes", "probably_yes", "any", "probably_no", "no", "unknown"),
            step.options!!.map { it.id }
        )
        assertTrue(step.options!!.all { it.label.isNotBlank() })
        assertNull(step.guessId)
        assertNull(step.food)
        assertNull(step.group)
    }

    /** The LLM engine sends the same shape; only the engine name and the question ID differ. */
    @Test
    fun questionFromTheLlmEngine() {
        val state = Fixtures.state("question_llm").checked()
        assertEquals(Engine.LLM, state.engine)
        assertEquals(193, state.candidateCount)
        assertEquals(10, state.maxQuestions)

        val step = state.step
        assertEquals(Step.QUESTION, step.type)
        assertEquals("q:llm-0", step.questionId)
        assertTrue(step.text.isNotBlank())
        assertEquals(Fixtures.state("question").step.options, step.options)
    }

    @Test
    fun engineUnavailableError() {
        val body = Fixtures.error("error_engine_unavailable")
        assertEquals(ApiError.ENGINE_UNAVAILABLE, body.error!!.code)
        assertNull(body.state)
    }

    @Test
    fun guessForOneDish() {
        val state = Fixtures.state("guess_food").checked()
        val step = state.step
        assertTrue(state.canUndo)
        assertEquals(Step.GUESS, step.type)
        assertEquals("food", step.targetKind)
        assertEquals("food:${step.food!!.foodId}", step.guessId)
        assertNull(step.group)
        assertNull(step.questionId)
        assertTrue(step.food!!.displayName.isNotBlank())
        val offer = step.food!!.offers.single()
        assertTrue(offer.restaurant.isNotBlank())
        assertEquals("LU", offer.meal)
        assertNotNull(offer.price)
    }

    @Test
    fun guessForAGroup() {
        val step = Fixtures.state("guess_group").checked().step
        val group = step.group!!
        assertEquals("group", step.targetKind)
        assertEquals(group.groupId, step.guessId)
        assertEquals("국수", group.displayName)
        assertEquals(8, group.members.size)
        assertTrue(group.members.any { it.foodId == step.food!!.foodId })
        assertTrue(group.members.all { it.displayName.isNotBlank() })
        assertEquals("냉모밀", step.food!!.displayName)
    }

    @Test
    fun recommendation() {
        val step = Fixtures.state("recommendation").checked().step
        assertEquals(Step.RECOMMENDATION, step.type)
        assertNull(step.guessId)
        assertTrue(step.food!!.offers.isNotEmpty())
    }

    @Test
    fun recommendationAfterAcceptingAGroupKeepsTheShownDish() {
        val guess = Fixtures.state("guess_group").step
        val result = Fixtures.state("recommendation_group").checked().step
        assertEquals(Step.RECOMMENDATION, result.type)
        assertEquals(guess.food, result.food)
        assertEquals(guess.group, result.group)
    }

    @Test
    fun unavailableWithNoMealAndNoCandidates() {
        val state = Fixtures.state("unavailable_empty").checked()
        assertNull(state.meal)
        assertEquals(0, state.candidateCount)
        assertEquals(Step.UNAVAILABLE, state.step.type)
        assertEquals("empty_candidates", state.step.reason)
        assertNull(state.step.food)
    }

    @Test
    fun errorBodies() {
        val stale = Fixtures.error("error_stale_step")
        assertEquals("stale_step", stale.error!!.code)
        assertEquals(Step.GUESS, stale.state!!.checked().step.type)

        val missing = Fixtures.error("error_session_not_found")
        assertEquals("session_not_found", missing.error!!.code)
        assertNull(missing.state)

        assertEquals("invalid_request", Fixtures.error("error_invalid_request").error!!.code)
    }

    @Test
    fun nullPriceAndNoCapDecode() {
        val json = Fixtures.json("guess_food")
            .replace(Regex("\"price\": \\d+"), "\"price\": null")
            .replace("\"max_questions\": 10", "\"max_questions\": null")
        val state = parse(json).checked()
        assertNull(state.maxQuestions)
        assertNull(state.step.food!!.offers.single().price)
    }

    @Test
    fun unknownExtraFieldsAreIgnored() {
        val json = Fixtures.json("question").replaceFirst("{", "{\"added_later\": {\"x\": [1, 2]},")
        assertEquals(Fixtures.state("question"), parse(json).checked())
    }

    /** Gson leaves a missing field null. [checked] must refuse it before the screen draws. */
    @Test
    fun incompleteRepliesAreRejected() {
        val broken = mapOf(
            "no step" to Fixtures.json("question").replace("\"step\"", "\"stepp\""),
            "no session id" to Fixtures.json("question").replace("\"session_id\"", "\"id\""),
            "no step type" to Fixtures.json("question").replace("\"type\"", "\"kind\""),
            "unknown step type" to Fixtures.json("question").replace("\"type\": \"question\"", "\"type\": \"quiz\""),
            "question without id" to Fixtures.json("question").replace("\"question_id\"", "\"questionId\""),
            "option without label" to Fixtures.json("question").replace("\"label\"", "\"title\""),
            "guess without food" to Fixtures.json("guess_food").replace("\"food\"", "\"dish\""),
            "guess without id" to Fixtures.json("guess_food").replace("\"guess_id\"", "\"guessId\""),
            "food without offers" to Fixtures.json("guess_food").replace("\"offers\"", "\"places\""),
            "food without display name" to Fixtures.json("guess_food").replace("\"display_name\"", "\"label\""),
            "offer without restaurant" to Fixtures.json("guess_food").replace("\"restaurant\"", "\"place\""),
            "group without members" to Fixtures.json("guess_group").replace("\"members\"", "\"food_ids\""),
            "recommendation without food" to Fixtures.json("recommendation").replace("\"food\"", "\"dish\""),
            "empty object" to "{}"
        )
        for ((name, json) in broken) {
            assertThrows(name, IllegalStateException::class.java) { parse(json).checked() }
        }
    }

    private fun parse(json: String): SessionState =
        RetrofitInstance.gson.fromJson(json, SessionState::class.java)
}
