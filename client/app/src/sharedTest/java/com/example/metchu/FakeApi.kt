package com.example.metchu

import com.example.metchu.data.model.Reason
import com.example.metchu.data.model.RestaurantMenu
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.network.AnswerRequest
import com.example.metchu.data.network.BanRequest
import com.example.metchu.data.network.ApiService
import com.example.metchu.data.network.CreateSessionRequest
import com.example.metchu.data.network.FeedbackRequest
import kotlinx.coroutines.CompletableDeferred
import java.io.IOException
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Records each call as text and answers from a queue of replies. Reason requests are
 * recorded apart, in [reasonCalls], and answered with [reason]; without one they fail
 * as an unreachable server would. Menu requests likewise go to [menuCalls], as
 * "<session> <restaurant>", and are answered with [menu].
 */
class FakeApi : ApiService {
    val calls = CopyOnWriteArrayList<String>()
    val reasonCalls = CopyOnWriteArrayList<String>()
    var reason: Reason? = null
    var heldReason: CompletableDeferred<Reason>? = null
    val menuCalls = CopyOnWriteArrayList<String>()
    var menu: RestaurantMenu? = null
    private val replies = ArrayDeque<suspend () -> SessionState>()

    fun reply(state: SessionState) { replies.add { state } }
    fun fail(error: Throwable) { replies.add { throw error } }
    /** The next call suspends until the returned gate is completed. */
    fun hold(): CompletableDeferred<SessionState> =
        CompletableDeferred<SessionState>().also { gate -> replies.add { gate.await() } }

    private suspend fun next(call: String): SessionState {
        calls.add(call)
        return replies.removeFirst().invoke()
    }

    /**
     * Recorded as "create LU" with the server's default engine, or "create LU llm",
     * followed by any location, allergies and language: "create LU llm @37.4,126.9 egg,milk ko".
     */
    override suspend fun createSession(request: CreateSessionRequest) = next(
        listOfNotNull(
            "create", request.meal ?: "null", request.engine,
            request.location?.let { "@${it.lat},${it.lng}" }, request.allergies?.joinToString(","),
            request.language
        ).joinToString(" ")
    )
    override suspend fun getState(sessionId: String) = next("state $sessionId")
    override suspend fun answer(sessionId: String, request: AnswerRequest) =
        next("answer $sessionId ${request.questionId} ${request.answerId}")
    override suspend fun feedback(sessionId: String, request: FeedbackRequest) =
        next("feedback $sessionId ${request.guessId} ${request.accepted}")
    override suspend fun recommendNow(sessionId: String) = next("recommend-now $sessionId")
    override suspend fun undo(sessionId: String) = next("undo $sessionId")
    override suspend fun ban(sessionId: String, request: BanRequest) =
        next("ban $sessionId ${request.foodId ?: request.foodGroup} ${request.banned}")
    override suspend fun reason(sessionId: String): Reason {
        reasonCalls.add(sessionId)
        val gate = heldReason
        heldReason = null
        return gate?.await() ?: reason ?: throw IOException("no reason")
    }
    override suspend fun menu(sessionId: String, restaurant: String): RestaurantMenu {
        menuCalls.add("$sessionId $restaurant")
        return menu ?: throw IOException("no menu")
    }
}
