package com.example.metchu

import com.example.metchu.data.model.SessionState
import com.example.metchu.data.network.AnswerRequest
import com.example.metchu.data.network.ApiService
import com.example.metchu.data.network.CreateSessionRequest
import com.example.metchu.data.network.FeedbackRequest
import kotlinx.coroutines.CompletableDeferred
import java.util.concurrent.CopyOnWriteArrayList

/** Records each call as text and answers from a queue of replies. */
class FakeApi : ApiService {
    val calls = CopyOnWriteArrayList<String>()
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

    override suspend fun createSession(request: CreateSessionRequest) = next("create ${request.meal}")
    override suspend fun getState(sessionId: String) = next("state $sessionId")
    override suspend fun answer(sessionId: String, request: AnswerRequest) =
        next("answer $sessionId ${request.questionId} ${request.answerId}")
    override suspend fun feedback(sessionId: String, request: FeedbackRequest) =
        next("feedback $sessionId ${request.guessId} ${request.accepted}")
    override suspend fun recommendNow(sessionId: String) = next("recommend-now $sessionId")
    override suspend fun undo(sessionId: String) = next("undo $sessionId")
}
