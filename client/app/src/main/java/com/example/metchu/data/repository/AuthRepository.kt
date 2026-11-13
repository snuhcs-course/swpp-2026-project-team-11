package com.example.metchu.data.repository

import com.example.metchu.data.network.AccountUser
import com.example.metchu.data.network.ApiErrorResponse
import com.example.metchu.data.network.AuthApi
import com.example.metchu.data.network.AuthError
import com.example.metchu.data.network.Credentials
import com.example.metchu.data.network.GoogleTokenRequest
import com.example.metchu.data.network.RetrofitInstance
import com.example.metchu.data.network.SignedIn
import retrofit2.HttpException

/**
 * Signs in and out with the server and keeps the account in [store]. Like
 * [RecommendRepository], the only class on its side that knows Retrofit exists.
 * Signing in is optional: recommendations work the same for a guest.
 */
class AuthRepository(private val store: AccountStore, private val api: AuthApi = RetrofitInstance.authApi) {

    val account: Account? get() = store.account

    suspend fun signUp(username: String, password: String): Account = keep(api.signUp(Credentials(username, password)))

    suspend fun logIn(username: String, password: String): Account = keep(api.logIn(Credentials(username, password)))

    /** Signs in with a Google ID token, making an account if this Google account has none. */
    suspend fun google(idToken: String): Account = keep(api.google(GoogleTokenRequest(idToken)))

    /** Links a Google account to the signed-in one, so either way of signing in reaches it. */
    suspend fun linkGoogle(idToken: String): Account {
        val account = checkNotNull(store.account) { "Not signed in" }
        val user = api.linkGoogle(account.authorization, GoogleTokenRequest(idToken)).user.checked()
        return account.copy(user = user).also { store.account = it }
    }

    /** Ends this device's sign-in. The device forgets it even if the server cannot be reached. */
    suspend fun logOut() {
        val account = store.account ?: return
        store.account = null
        api.logOut(account.authorization)
    }

    /**
     * Asks the server whether the saved account still stands, and returns the account signed in
     * afterwards. Only a confirmed rejection (`not_authenticated`) forgets it; an unreachable
     * server or any other failure throws and leaves it signed in.
     */
    suspend fun refresh(): Account? {
        val account = store.account ?: return null
        val user = try {
            api.me(account.authorization).user.checked()
        } catch (e: HttpException) {
            if (errorCode(e) != AuthError.NOT_AUTHENTICATED) throw e
            null
        }
        // A log-out or Google link made while the server answered stays as it is.
        if (store.account == account) store.account = user?.let { account.copy(user = it) }
        return store.account
    }

    /** Forgets an account the server no longer accepts. */
    fun forget() {
        store.account = null
    }

    /** The `code` of the server's `{"error": ...}` body, or null if it is not one. */
    fun errorCode(exception: HttpException): String? = try {
        exception.response()?.errorBody()?.charStream()?.use {
            RetrofitInstance.gson.fromJson(it, ApiErrorResponse::class.java)
        }?.error?.code
    } catch (e: Exception) {
        null
    }

    @Suppress("SENSELESS_COMPARISON")
    private fun keep(reply: SignedIn): Account {
        check(reply.token != null && reply.user != null) { "Sign-in reply is incomplete" }
        return Account(reply.token, reply.user.checked()).also { store.account = it }
    }
}

private val Account.authorization get() = "Token $token"

/** Gson leaves a missing field null even where Kotlin says it cannot be; reject such a reply. */
@Suppress("SENSELESS_COMPARISON")
private fun AccountUser.checked(): AccountUser {
    check(username != null) { "Account reply has no username" }
    return this
}
