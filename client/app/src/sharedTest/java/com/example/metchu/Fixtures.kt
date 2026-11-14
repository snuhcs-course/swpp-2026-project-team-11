package com.example.metchu

import com.example.metchu.data.model.RestaurantMenu
import com.example.metchu.data.model.RoomReply
import com.example.metchu.data.model.RoomState
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.network.ApiErrorResponse
import com.example.metchu.data.network.RetrofitInstance
import com.example.metchu.data.network.SignedIn
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import retrofit2.HttpException
import retrofit2.Response

/**
 * Replies captured from the real server (backend/recommend) on the 2026-09-29
 * snapshot (since replaced; the reply shape is unchanged), stored under
 * src/sharedTest/resources/contract. If the server's JSON changes,
 * recapture them; the tests that read them are the client's side of the contract.
 *
 * src/sharedTest is compiled into both the JVM unit tests and the on-device tests.
 */
object Fixtures {
    /** Reads a file under src/sharedTest/resources. On-device tests read assets instead. */
    var read: (path: String) -> String = { path ->
        checkNotNull(javaClass.classLoader?.getResource(path)) { "Missing fixture $path" }.readText()
    }

    fun json(name: String): String = read("contract/$name.json")

    fun state(name: String): SessionState =
        RetrofitInstance.gson.fromJson(json(name), SessionState::class.java)

    fun menu(): RestaurantMenu = RetrofitInstance.gson.fromJson(json("menu"), RestaurantMenu::class.java)

    /** A sign-in reply (backend/accounts), captured from a local server on SQLite. */
    fun signedIn(name: String = "auth_signed_in"): SignedIn =
        RetrofitInstance.gson.fromJson(json(name), SignedIn::class.java)

    /** Group room replies (backend/recommend/rooms.py), captured from a local server on the 2026-11-02 snapshot. */
    fun room(name: String): RoomState = RetrofitInstance.gson.fromJson(json(name), RoomState::class.java)

    fun roomReply(name: String): RoomReply = RetrofitInstance.gson.fromJson(json(name), RoomReply::class.java)

    fun error(name: String): ApiErrorResponse =
        RetrofitInstance.gson.fromJson(json(name), ApiErrorResponse::class.java)

    fun httpError(code: Int, body: String): HttpException =
        HttpException(Response.error<Any>(code, body.toResponseBody("application/json".toMediaType())))
}
