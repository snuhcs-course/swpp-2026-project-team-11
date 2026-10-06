package com.example.metchu.data.repository

import com.example.metchu.data.model.SessionState
import com.example.metchu.data.network.AnswerRequest
import com.example.metchu.data.network.ApiErrorResponse
import com.example.metchu.data.network.CreateSessionRequest
import com.example.metchu.data.network.FeedbackRequest
import com.example.metchu.data.network.RetrofitInstance
import retrofit2.HttpException

/**
 * The only class that knows Retrofit exists. Activities never call the network;
 * the ViewModel calls this repository.
 */
class RecommendRepository {

    private val api = RetrofitInstance.api

    suspend fun createSession(meal: String?): SessionState =
        api.createSession(CreateSessionRequest(meal))

    suspend fun answer(sessionId: String, questionId: String, answerId: String): SessionState =
        api.answer(sessionId, AnswerRequest(questionId, answerId))

    suspend fun feedback(sessionId: String, guessId: String, accepted: Boolean): SessionState =
        api.feedback(sessionId, FeedbackRequest(guessId, accepted))

    suspend fun recommendNow(sessionId: String): SessionState = api.recommendNow(sessionId)

    suspend fun undo(sessionId: String): SessionState = api.undo(sessionId)

    /** Decodes the server's `{"error": ..., "state": ...}` body, or null if it is not one. */
    fun errorBody(exception: HttpException): ApiErrorResponse? = try {
        exception.response()?.errorBody()?.charStream()?.use {
            RetrofitInstance.gson.fromJson(it, ApiErrorResponse::class.java)
        }
    } catch (e: Exception) {
        null
    }
}
