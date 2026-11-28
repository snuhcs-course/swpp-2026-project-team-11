package com.example.metchu.data.network

import com.example.metchu.data.model.Reason
import com.example.metchu.data.model.RestaurantMenu
import com.example.metchu.data.model.SessionState
import com.google.gson.annotations.SerializedName
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * The contract with backend/recommend/views.py. Field names must match its JSON.
 *
 * [CreateSessionRequest.meal] is "BR", "LU", "DN" or null for the whole day.
 * [CreateSessionRequest.engine] is one of the [Engine] IDs, or null for the server's
 * default. [CreateSessionRequest.allergies] lists Allergen
 * IDs the server must never propose, or is null for none. [CreateSessionRequest.language]
 * is "en" or "ko", the language of every text the server sends, or null for English.
 * [CreateSessionRequest.areas] are the picked [com.example.metchu.data.repository.Area] IDs; the phone
 * sends no location. Without them the server falls back to the single `area` of older apps, which is
 * campus when missing, so the app always sends them.
 * [CreateSessionRequest.priceLevels] are the numbers of ₩ signs picked (1 to 3), or null for any price.
 * Gson leaves a null field out of the body. The menu date is the server's decision, so
 * the phone does not send one.
 * A signed-in phone sends its "Token <token>" with the request, so the server records the
 * session's dishes in the account's history; a null header is left out.
 */
data class CreateSessionRequest(
    val meal: String?,
    val engine: String? = null,
    val allergies: List<String>?,
    val language: String? = null,
    val areas: List<String>? = null,
    @SerializedName("price_levels") val priceLevels: List<Int>? = null
)

/** What a session with these fields reads, so the server builds it before Start. */
data class PrewarmRequest(val meal: String?, val allergies: List<String>?, val areas: List<String>?)

data class AnswerRequest(
    @SerializedName("question_id") val questionId: String,
    @SerializedName("answer_id") val answerId: String
)

data class FeedbackRequest(
    @SerializedName("guess_id") val guessId: String,
    val accepted: Boolean
)

/**
 * What the user did in the app with the session's step on screen, for the server's interaction
 * log (backend/recommend/views.py, `event`): one of the names below, with the [restaurant] for
 * directions and a bookmark. It changes nothing in the session.
 */
data class EventRequest(val event: String, val restaurant: String? = null) {
    companion object {
        /** Back to the start screen. */
        const val HOME = "home"
        /** Back to the session left that way. */
        const val RESUME = "resume"
        /** Walking directions to a restaurant opened in a map app. */
        const val DIRECTIONS = "directions"
        /** A restaurant bookmarked. */
        const val BOOKMARK = "bookmark"
        /** The app went to the background. */
        const val BACKGROUND = "background"
    }
}

/** Body of a non-2xx response. `state` is only sent with a 409 stale_step. */
data class ApiErrorResponse(val error: ApiError?, val state: SessionState?)

data class ApiError(val code: String, val message: String) {
    companion object {
        /** 503: the chosen engine cannot run with the available configuration or catalogue. */
        const val ENGINE_UNAVAILABLE = "engine_unavailable"
        /** 400: the server rejected a request field, such as an unsupported engine ID. */
        const val INVALID_REQUEST = "invalid_request"
        /** 400: the LLM engine is offered only for the campus area. */
        const val AREA_LLM_UNSUPPORTED = "area_llm_unsupported"
    }
}

interface ApiService {

    @POST("api/sessions/")
    suspend fun createSession(@Header("Authorization") authorization: String?, @Body request: CreateSessionRequest): SessionState

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

    @GET("api/sessions/{id}/reason/")
    suspend fun reason(@Path("id") sessionId: String): Reason

    @GET("api/sessions/{id}/menu/")
    suspend fun menu(@Path("id") sessionId: String, @Query("restaurant") restaurant: String): RestaurantMenu

    /** 204; a server from before i5-A10 answers 404, which the caller ignores like any failure. */
    @POST("api/sessions/{id}/event/")
    suspend fun event(@Path("id") sessionId: String, @Body request: EventRequest): Response<Unit>
}
