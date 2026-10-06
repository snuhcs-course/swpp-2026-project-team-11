package com.example.metchu.data.network

import com.example.metchu.data.model.SessionState
import com.google.gson.annotations.SerializedName
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

/**
 * The contract with backend/recommend/views.py. Field names must match its JSON.
 *
 * [CreateSessionRequest.meal] is "BR", "LU", "DN" or null for the whole day. The
 * menu date is the server's decision, so the phone does not send one.
 */
data class CreateSessionRequest(val meal: String?)

data class AnswerRequest(
    @SerializedName("question_id") val questionId: String,
    @SerializedName("answer_id") val answerId: String
)

data class FeedbackRequest(
    @SerializedName("guess_id") val guessId: String,
    val accepted: Boolean
)

/** Body of a non-2xx response. `state` is only sent with a 409 stale_step. */
data class ApiErrorResponse(val error: ApiError?, val state: SessionState?)

data class ApiError(val code: String, val message: String)

interface ApiService {

    @POST("api/sessions/")
    suspend fun createSession(@Body request: CreateSessionRequest): SessionState

    @GET("api/sessions/{id}/")
    suspend fun getState(@Path("id") sessionId: String): SessionState

    @POST("api/sessions/{id}/answer/")
    suspend fun answer(@Path("id") sessionId: String, @Body request: AnswerRequest): SessionState

    @POST("api/sessions/{id}/feedback/")
    suspend fun feedback(@Path("id") sessionId: String, @Body request: FeedbackRequest): SessionState

    @POST("api/sessions/{id}/recommend-now/")
    suspend fun recommendNow(@Path("id") sessionId: String): SessionState

    @POST("api/sessions/{id}/undo/")
    suspend fun undo(@Path("id") sessionId: String): SessionState
}
