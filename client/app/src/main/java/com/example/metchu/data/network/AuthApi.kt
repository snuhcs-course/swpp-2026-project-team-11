package com.example.metchu.data.network

import com.google.gson.annotations.SerializedName
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST

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
