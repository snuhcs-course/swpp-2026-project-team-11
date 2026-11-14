package com.example.metchu.data.repository

import com.example.metchu.data.model.Allergen
import com.example.metchu.data.model.RoomReply
import com.example.metchu.data.model.RoomState
import com.example.metchu.data.network.AnswerRequest
import com.example.metchu.data.network.CreateRoomRequest
import com.example.metchu.data.network.DecideRequest
import com.example.metchu.data.network.JoinRoomRequest
import com.example.metchu.data.network.RetrofitInstance
import com.example.metchu.data.network.RoomApi
import com.example.metchu.data.network.UserLocation

/** Which room this phone is in, and the secret that proves it is this member. */
data class Membership(val code: String, val token: String)

/**
 * The group rooms on the server. [account] is the signed-in account's token, if any: the
 * server then names the member by username and [name] is not sent.
 */
class RoomRepository(private val api: RoomApi = RetrofitInstance.roomApi) {

    suspend fun create(
        account: String?,
        name: String?,
        allergies: List<Allergen>,
        language: String,
        meal: String?,
        location: UserLocation?,
        distanceScope: String
    ): Pair<Membership, RoomState> = joined(api.create(
        account?.let { "Token $it" },
        CreateRoomRequest(name.takeIf { account == null }, allergies.map { it.id }, language, meal, location, SOURCE, distanceScope)
    ))

    suspend fun join(account: String?, code: String, name: String?, allergies: List<Allergen>, language: String): Pair<Membership, RoomState> =
        joined(api.join(account?.let { "Token $it" }, JoinRoomRequest(code, name.takeIf { account == null }, allergies.map { it.id }, language)))

    suspend fun state(room: Membership): RoomState = api.state(room.code, room.token)

    suspend fun start(room: Membership): RoomState = api.start(room.code, room.token)

    suspend fun answer(room: Membership, questionId: String, answerId: String): RoomState =
        api.answer(room.code, room.token, AnswerRequest(questionId, answerId))

    suspend fun recommendNow(room: Membership): RoomState = api.recommendNow(room.code, room.token)

    suspend fun decide(room: Membership, pick: Int): RoomState = api.decide(room.code, room.token, DecideRequest(pick))

    suspend fun leave(room: Membership) {
        api.leave(room.code, room.token)
    }

    private fun joined(reply: RoomReply) = Membership(reply.state.code, reply.token) to reply.state

    private companion object {
        /** Like solo sessions: the cafeterias and the restaurants near the stations. */
        const val SOURCE = "all"
    }
}
