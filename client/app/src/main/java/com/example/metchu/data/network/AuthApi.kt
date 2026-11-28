package com.example.metchu.data.network

import com.google.gson.annotations.SerializedName
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path

data class Credentials(val username: String, val password: String)

data class GoogleTokenRequest(@SerializedName("id_token") val idToken: String)

/** [googleEmail] is null with no Google account linked, and "" when Google shared no address. */
data class AccountUser(
    val username: String,
    @SerializedName("google_email") val googleEmail: String?,
    @SerializedName("has_password") val hasPassword: Boolean
)

/** A sign-in's reply. [created] is set by Google sign-in: true when it made a new account. */
data class SignedIn(val token: String, val user: AccountUser, val created: Boolean? = null)

data class AccountReply(val user: AccountUser)

/**
 * A restaurant the account saved, by the name a result showed. [address] (null when the server
 * knows none, as for the campus cafeterias), [createdAt] (the server's ISO time) and [id] (removes
 * it) come from the server; the phone sends only [restaurant].
 */
data class Bookmark(
    val restaurant: String,
    val address: String? = null,
    @SerializedName("created_at") val createdAt: String? = null,
    val id: Int? = null
)

data class BookmarkReply(val bookmark: Bookmark)

data class BookmarksReply(val bookmarks: List<Bookmark>)

/** A dish a solo session proposed to the account. [meal] is null for a whole-day session. */
data class HistoryEntry(
    val date: String,
    val meal: String?,
    @SerializedName("food_id") val foodId: Int,
    @SerializedName("display_name") val displayName: String,
    val restaurant: String,
    @SerializedName("created_at") val createdAt: String
)

data class HistoryReply(val history: List<HistoryEntry>)

/** The account endpoints (backend/accounts/views.py). Signed-in calls take "Token <token>". */
interface AuthApi {

    @POST("api/auth/signup/")
    suspend fun signUp(@Body credentials: Credentials): SignedIn

    @POST("api/auth/login/")
    suspend fun logIn(@Body credentials: Credentials): SignedIn

    @POST("api/auth/google/")
    suspend fun google(@Body request: GoogleTokenRequest): SignedIn

    @POST("api/auth/google/link/")
    suspend fun linkGoogle(@Header("Authorization") authorization: String, @Body request: GoogleTokenRequest): AccountReply

    @GET("api/auth/me/")
    suspend fun me(@Header("Authorization") authorization: String): AccountReply

    @POST("api/auth/logout/")
    suspend fun logOut(@Header("Authorization") authorization: String): Response<Unit>

    @GET("api/auth/bookmarks/")
    suspend fun bookmarks(@Header("Authorization") authorization: String): BookmarksReply

    @POST("api/auth/bookmarks/")
    suspend fun bookmark(@Header("Authorization") authorization: String, @Body bookmark: Bookmark): BookmarkReply

    @DELETE("api/auth/bookmarks/{id}/")
    suspend fun unbookmark(@Header("Authorization") authorization: String, @Path("id") id: Int): Response<Unit>

    @DELETE("api/auth/bookmarks/")
    suspend fun clearBookmarks(@Header("Authorization") authorization: String): Response<Unit>

    @GET("api/auth/history/")
    suspend fun history(@Header("Authorization") authorization: String): HistoryReply

    @DELETE("api/auth/history/")
    suspend fun clearHistory(@Header("Authorization") authorization: String): Response<Unit>
}

/** Error codes of the account endpoints, in `{"error": {"code", "message"}}`. */
object AuthError {
    const val INVALID_USERNAME = "invalid_username"
    const val USERNAME_TAKEN = "username_taken"
    const val WEAK_PASSWORD = "weak_password"
    const val INVALID_CREDENTIALS = "invalid_credentials"
    const val INVALID_GOOGLE_TOKEN = "invalid_google_token"
    const val GOOGLE_UNAVAILABLE = "google_unavailable"
    const val GOOGLE_IN_USE = "google_in_use"
    const val ALREADY_LINKED = "already_linked"
    const val NOT_AUTHENTICATED = "not_authenticated"
}
