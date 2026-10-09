// AI-generated: written with Claude (Anthropic) and reviewed by the team.
package com.example.metchu.data.repository

import com.example.metchu.data.model.SessionState
import com.example.metchu.data.model.Step
import com.example.metchu.data.network.AnswerRequest
import com.example.metchu.data.network.ApiErrorResponse
import com.example.metchu.data.network.ApiService
import com.example.metchu.data.network.CreateSessionRequest
import com.example.metchu.data.network.FeedbackRequest
import com.example.metchu.data.network.RetrofitInstance
import retrofit2.HttpException

/**
 * The only class that knows Retrofit exists. Activities never call the network;
 * the ViewModel calls this repository.
 */
class RecommendRepository(private val api: ApiService = RetrofitInstance.api) {

    suspend fun createSession(meal: String?, engine: String? = null): SessionState =
        api.createSession(CreateSessionRequest(meal, engine)).checked()

    suspend fun answer(sessionId: String, questionId: String, answerId: String): SessionState =
        api.answer(sessionId, AnswerRequest(questionId, answerId)).checked()

    suspend fun feedback(sessionId: String, guessId: String, accepted: Boolean): SessionState =
        api.feedback(sessionId, FeedbackRequest(guessId, accepted)).checked()

    suspend fun recommendNow(sessionId: String): SessionState =
        api.recommendNow(sessionId).checked()

    suspend fun undo(sessionId: String): SessionState = api.undo(sessionId).checked()

    /** The session as the server has it now. Changes nothing. */
    suspend fun state(sessionId: String): SessionState = api.getState(sessionId).checked()

    /**
     * Decodes the server's `{"error": ..., "state": ...}` body, or null if it is not
     * one. A `state` that fails [checked] is dropped rather than shown.
     */
    fun errorBody(exception: HttpException): ApiErrorResponse? = try {
        exception.response()?.errorBody()?.charStream()?.use {
            RetrofitInstance.gson.fromJson(it, ApiErrorResponse::class.java)
        }?.let { body ->
            if (body.state == null || runCatching { body.state.checked() }.isSuccess) body
            else body.copy(state = null)
        }
    } catch (e: Exception) {
        null
    }
}

/**
 * Gson fills a missing field with null even where Kotlin says it cannot be null, and
 * the screen would then crash while drawing. Reject such a reply here, where the
 * ViewModel reports it as a server error.
 */
@Suppress("SENSELESS_COMPARISON")
internal fun SessionState.checked(): SessionState {
    check(sessionId != null && date != null && step != null && step.type != null) {
        "Server reply is missing session fields"
    }
    when (step.type) {
        Step.QUESTION -> check(step.questionId != null && step.text != null &&
                step.options.orEmpty().none { it == null || it.id == null || it.label == null }) {
            "Question step is incomplete"
        }
        Step.GUESS, Step.RECOMMENDATION -> {
            val food = step.food
            check(food != null && food.displayName != null && food.name != null &&
                    food.offers != null && food.offers.none { it == null || it.restaurant == null }) {
                "Proposed dish is incomplete"
            }
            check(step.type != Step.GUESS || step.guessId != null) { "Guess has no ID" }
            check(step.group == null || (step.group.displayName != null && step.group.members != null &&
                    step.group.members.none { it == null || it.displayName == null })) {
                "Group is incomplete"
            }
        }
        Step.UNAVAILABLE -> Unit
        else -> error("Unknown step type: ${step.type}")
    }
    return this
}
