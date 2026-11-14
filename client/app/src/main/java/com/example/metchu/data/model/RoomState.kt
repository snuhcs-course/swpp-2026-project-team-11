package com.example.metchu.data.model

import com.google.gson.annotations.SerializedName

/**
 * Mirrors `Room.public_state(member)` in backend/recommend/rooms.py: one group room as one
 * member's phone sees it. [me] and [host] are member IDs, positions in [members].
 */
data class RoomState(
    val code: String,
    val status: String,
    val date: String,
    val meal: String?,
    val me: Int,
    val host: Int,
    val members: List<RoomMember>,
    val round: Int,
    @SerializedName("max_rounds") val maxRounds: Int,
    // asking
    val question: RoomQuestion?,
    @SerializedName("my_answer") val myAnswer: String?,
    @SerializedName("seconds_left") val secondsLeft: Double?,
    /** How long every round allows; silence then counts as "not sure". */
    @SerializedName("round_seconds") val roundSeconds: Int,
    // done
    val picks: List<RoomPick>?,
    /** The position in [picks] the host chose. */
    val decided: Int?
) {
    val isHost: Boolean get() = me == host

    companion object {
        const val LOBBY = "lobby"
        const val ASKING = "asking"
        const val DONE = "done"
    }
}

/** [allergies] are Allergen IDs. [answered]: this round, while the room is asking. */
data class RoomMember(
    val id: Int,
    val name: String,
    val allergies: List<String>,
    val left: Boolean,
    val answered: Boolean
)

data class RoomQuestion(
    @SerializedName("question_id") val questionId: String,
    val text: String,
    val options: List<AnswerOption>
)

/**
 * A suggested restaurant, each member's dish there and its [others] dishes. [kind] is the
 * engine's reason for it: "balanced" or "no_one_unhappy".
 */
data class RoomPick(
    val restaurant: String,
    val kind: String,
    val lat: Double?,
    val lng: Double?,
    @SerializedName("distance_m") val distanceM: Int?,
    val menus: List<RoomDish>,
    val others: List<MenuDish>
)

/** [fit] is "great" when the place is among the member's best for them, otherwise "good". */
data class RoomDish(
    @SerializedName("member_id") val memberId: Int,
    val food: Food,
    val fit: String
) {
    companion object {
        const val GREAT = "great"
    }
}

/** The reply to creating or joining a room: the member's secret [token] and the room. */
data class RoomReply(val token: String, val state: RoomState)
