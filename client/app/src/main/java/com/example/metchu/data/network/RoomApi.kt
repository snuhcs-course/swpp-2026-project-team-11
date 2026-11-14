package com.example.metchu.data.network

import com.example.metchu.data.model.RoomReply
import com.example.metchu.data.model.RoomState
import com.google.gson.annotations.SerializedName
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path

/**
 * The group rooms of backend/recommend/views.py. Creating and joining send the account's
 * `Authorization` when signed in (the server then shows the username) and a [name]
 * otherwise; every other request carries the member token those replies return.
 */
data class CreateRoomRequest(
    val name: String?,
    val allergies: List<String>,
    val language: String,
    val meal: String?,
    val location: UserLocation?,
    val source: String,
    @SerializedName("distance_scope") val distanceScope: String
)

data class JoinRoomRequest(
    val code: String,
    val name: String?,
    val allergies: List<String>,
    val language: String
)

data class DecideRequest(val restaurant: String)

interface RoomApi {

    @POST("api/rooms/")
    suspend fun create(@Header("Authorization") authorization: String?, @Body request: CreateRoomRequest): RoomReply

    @POST("api/rooms/join/")
    suspend fun join(@Header("Authorization") authorization: String?, @Body request: JoinRoomRequest): RoomReply

    @GET("api/rooms/{code}/")
    suspend fun state(@Path("code") code: String, @Header(MEMBER) token: String): RoomState

    @POST("api/rooms/{code}/start/")
    suspend fun start(@Path("code") code: String, @Header(MEMBER) token: String): RoomState

    @POST("api/rooms/{code}/answer/")
    suspend fun answer(@Path("code") code: String, @Header(MEMBER) token: String, @Body request: AnswerRequest): RoomState

    @POST("api/rooms/{code}/recommend-now/")
    suspend fun recommendNow(@Path("code") code: String, @Header(MEMBER) token: String): RoomState

    @POST("api/rooms/{code}/decide/")
    suspend fun decide(@Path("code") code: String, @Header(MEMBER) token: String, @Body request: DecideRequest): RoomState

    @POST("api/rooms/{code}/leave/")
    suspend fun leave(@Path("code") code: String, @Header(MEMBER) token: String): Response<Unit>

    companion object {
        const val MEMBER = "X-Member-Token"
        const val ROOM_NOT_FOUND = "room_not_found"
        const val ROOM_STARTED = "room_started"
        const val ROOM_FULL = "room_full"
        const val NOT_MEMBER = "not_member"
        const val GROUP_UNAVAILABLE = "group_unavailable"
        const val STALE_STEP = "stale_step"
    }
}
