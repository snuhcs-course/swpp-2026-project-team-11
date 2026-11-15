package com.example.metchu.data.network

import com.example.metchu.data.model.Reason
import com.example.metchu.data.model.RestaurantMenu
import com.example.metchu.data.model.SessionState
import com.google.gson.annotations.SerializedName
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * The contract with backend/recommend/views.py. Field names must match its JSON.
 *
 * [CreateSessionRequest.meal] is "BR", "LU", "DN" or null for the whole day.
 * [CreateSessionRequest.engine] is one of the [Engine] IDs, or null for the server's
 * default. [CreateSessionRequest.location] is where the user is, if known; the server
 * then adds each cafeteria's distance. [CreateSessionRequest.allergies] lists Allergen
 * IDs the server must never propose, or is null for none. [CreateSessionRequest.language]
 * is "en" or "ko", the language of every text the server sends, or null for English.
 * Gson leaves a null field out of the body. The menu date is the server's decision, so
 * the phone does not send one. `source=all` combines cafeteria and restaurant menus.
 */
data class CreateSessionRequest(
    val meal: String?,
    val engine: String? = null,
    val location: UserLocation?,
    val allergies: List<String>?,
    val language: String? = null,
    val source: String? = null,
    @SerializedName("distance_scope") val distanceScope: String? = null
)

/** What a session with these fields reads, so the server builds it before Start. */
data class PrewarmRequest(val meal: String?, val allergies: List<String>?, val source: String?)

data class UserLocation(val lat: Double, val lng: Double)

data class AnswerRequest(
    @SerializedName("question_id") val questionId: String,
    @SerializedName("answer_id") val answerId: String
)

data class FeedbackRequest(
    @SerializedName("guess_id") val guessId: String,
    val accepted: Boolean
)

data class BanRequest(
    @SerializedName("food_id") val foodId: Int?,
    @SerializedName("food_group") val foodGroup: String?,
    val banned: Boolean
)

/** Body of a non-2xx response. `state` is only sent with a 409 stale_step. */
data class ApiErrorResponse(val error: ApiError?, val state: SessionState?)

data class ApiError(val code: String, val message: String) {
    companion object {
        /** 503: the chosen engine cannot run with the available configuration or catalogue. */
        const val ENGINE_UNAVAILABLE = "engine_unavailable"
        /** 400: the server rejected a request field, such as an unsupported engine ID. */
        const val INVALID_REQUEST = "invalid_request"
        const val ALL_SOURCE_LLM_UNSUPPORTED = "all_source_llm_unsupported"
    }
}

interface ApiService {

    @POST("api/sessions/")
    suspend fun createSession(@Body request: CreateSessionRequest): SessionState

    @POST("api/sessions/prewarm/")
    suspend fun prewarm(@Body request: PrewarmRequest): Response<Unit>

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

    @POST("api/sessions/{id}/ban/")
    suspend fun ban(@Path("id") sessionId: String, @Body request: BanRequest): SessionState

    @GET("api/sessions/{id}/reason/")
    suspend fun reason(@Path("id") sessionId: String): Reason

    @GET("api/sessions/{id}/menu/")
    suspend fun menu(@Path("id") sessionId: String, @Query("restaurant") restaurant: String): RestaurantMenu
}
