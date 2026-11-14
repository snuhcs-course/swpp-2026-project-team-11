package com.example.metchu

import com.example.metchu.data.model.RoomReply
import com.example.metchu.data.model.RoomState
import com.example.metchu.data.network.AnswerRequest
import com.example.metchu.data.network.CreateRoomRequest
import com.example.metchu.data.network.DecideRequest
import com.example.metchu.data.network.JoinRoomRequest
import com.example.metchu.data.network.RoomApi
import retrofit2.Response
import java.io.IOException
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Records each call as text ("answer 6543 member-token q:soupy yes") and answers from a
 * queue of replies. With nothing queued a call fails as an unreachable server would.
 */
class FakeRoomApi : RoomApi {
    val calls = CopyOnWriteArrayList<String>()
    private val replies = ArrayDeque<() -> Any>()

    fun reply(value: Any) { replies.add { value } }
    fun fail(error: Throwable) { replies.add { throw error } }

    @Suppress("UNCHECKED_CAST")
    private fun <T> next(call: String): T {
        calls.add(call)
        val reply = replies.removeFirstOrNull() ?: throw IOException("No reply queued for $call")
        return reply() as T
    }

    override suspend fun create(authorization: String?, request: CreateRoomRequest): RoomReply =
        next("create $authorization ${request.name}")
    override suspend fun join(authorization: String?, request: JoinRoomRequest): RoomReply =
        next("join $authorization ${request.code} ${request.name}")
    override suspend fun state(code: String, token: String): RoomState = next("state $code $token")
    override suspend fun start(code: String, token: String): RoomState = next("start $code $token")
    override suspend fun answer(code: String, token: String, request: AnswerRequest): RoomState =
        next("answer $code $token ${request.questionId} ${request.answerId}")
    override suspend fun recommendNow(code: String, token: String): RoomState = next("recommend-now $code $token")
    override suspend fun decide(code: String, token: String, request: DecideRequest): RoomState =
        next("decide $code $token ${request.restaurant}")
    override suspend fun leave(code: String, token: String): Response<Unit> {
        calls.add("leave $code $token")
        return Response.success(Unit)
    }
}
