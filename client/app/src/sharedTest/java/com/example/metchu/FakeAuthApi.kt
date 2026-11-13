package com.example.metchu

import com.example.metchu.data.network.AccountReply
import com.example.metchu.data.network.AuthApi
import com.example.metchu.data.network.Credentials
import com.example.metchu.data.network.GoogleTokenRequest
import com.example.metchu.data.network.SignedIn
import com.example.metchu.data.repository.Account
import com.example.metchu.data.repository.AccountStore
import retrofit2.Response
import java.io.IOException
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Records each call as text ("login metchu_user", "link Token t g-token") and answers from a
 * queue of replies. With nothing queued a call fails as an unreachable server would.
 */
class FakeAuthApi : AuthApi {
    val calls = CopyOnWriteArrayList<String>()
    private val replies = ArrayDeque<() -> Any>()

    fun reply(value: Any) { replies.add { value } }
    fun fail(error: Throwable) { replies.add { throw error } }

    /** Answers with [block]'s value, running it as the call is made. */
    fun answer(block: () -> Any) { replies.add(block) }

    @Suppress("UNCHECKED_CAST")
    private fun <T> next(call: String): T {
        calls.add(call)
        val reply = replies.removeFirstOrNull() ?: throw IOException("No reply queued for $call")
        return reply() as T
    }

    override suspend fun signUp(credentials: Credentials): SignedIn = next("signup ${credentials.username}")
    override suspend fun logIn(credentials: Credentials): SignedIn = next("login ${credentials.username}")
    override suspend fun google(request: GoogleTokenRequest): SignedIn = next("google ${request.idToken}")
    override suspend fun linkGoogle(authorization: String, request: GoogleTokenRequest): AccountReply =
        next("link $authorization ${request.idToken}")
    override suspend fun me(authorization: String): AccountReply = next("me $authorization")
    override suspend fun logOut(authorization: String): Response<Unit> = next("logout $authorization")
}

/** An [AccountStore] in memory, for tests that have no Android preferences. */
class MemoryAccountStore(override var account: Account? = null) : AccountStore
