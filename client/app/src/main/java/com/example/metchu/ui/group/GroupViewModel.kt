package com.example.metchu.ui.group

import android.util.Log
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.example.metchu.R
import com.example.metchu.data.model.AnswerId
import com.example.metchu.data.model.Allergen
import com.example.metchu.data.model.RoomState
import com.example.metchu.data.network.ApiError
import com.example.metchu.data.network.RetrofitInstance
import com.example.metchu.data.network.RoomApi
import com.example.metchu.data.network.UserLocation
import com.example.metchu.data.repository.Membership
import com.example.metchu.data.repository.RoomRepository
import com.example.metchu.ui.main.AnsweredQuestion
import com.example.metchu.ui.main.UiError
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.IOException

/**
 * The group room this phone is in. [room] is null outside one. While in a room the phone
 * asks the server for it every [POLL_MILLIS], since the others' answers, the host's start
 * and the 10-second deadlines all happen elsewhere; it stops once the host has decided.
 *
 * [history] lists the rounds already over, with this member's answer ("not sure" when the
 * time ran out), for the question screen; the server keeps no question texts.
 * [busy] is true while this phone's own request runs, and taps meanwhile are ignored.
 */
class GroupViewModel(private val repository: RoomRepository) : ViewModel() {

    private val _room = MutableLiveData<RoomState?>(null)
    val room: LiveData<RoomState?> = _room

    private val _history = MutableLiveData<List<AnsweredQuestion>>(emptyList())
    val history: LiveData<List<AnsweredQuestion>> = _history

    private val _busy = MutableLiveData(false)
    val busy: LiveData<Boolean> = _busy

    private val _error = MutableLiveData<UiError?>(null)
    val error: LiveData<UiError?> = _error

    private var membership: Membership? = null
    private var polling: Job? = null

    /** [account] is the signed-in account's token; without one, [name] names the member. */
    fun create(account: String?, name: String?, allergies: List<Allergen>, language: String, meal: String?, location: suspend () -> UserLocation?, distanceScope: String) =
        enter { repository.create(account, name, allergies, language, meal, location(), distanceScope) }

    fun join(account: String?, code: String, name: String?, allergies: List<Allergen>, language: String) =
        enter { repository.join(account, code, name, allergies, language) }

    fun start() = act { repository.start(it) }

    fun answer(answerId: String) {
        val question = _room.value?.question ?: return
        act { repository.answer(it, question.questionId, answerId) }
    }

    fun recommendNow() = act { repository.recommendNow(it) }

    fun decide(restaurant: String) = act { repository.decide(it, restaurant) }

    /** Leaves at once on this phone; the server is told on the side. */
    fun leave() {
        val left = membership ?: return
        reset()
        viewModelScope.launch {
            try {
                repository.leave(left)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w(TAG, "could not tell the room we left", e)
            }
        }
    }

    fun clearError() {
        _error.value = null
    }

    private fun enter(request: suspend () -> Pair<Membership, RoomState>) {
        if (_busy.value == true) return
        _busy.value = true
        _error.value = null
        viewModelScope.launch {
            try {
                val (joined, state) = request()
                membership = joined
                _history.value = emptyList()
                show(state)
                poll()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                fail(e, code(e))
            } finally {
                _busy.value = false
            }
        }
    }

    private fun act(request: suspend (Membership) -> RoomState) {
        val room = membership ?: return
        if (_busy.value == true) return
        _busy.value = true
        _error.value = null
        viewModelScope.launch {
            try {
                show(request(room))
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                // The room moved on meanwhile (a deadline, another phone): the next poll redraws it.
                val code = code(e)
                if (code != RoomApi.STALE_STEP) fail(e, code)
            } finally {
                _busy.value = false
            }
        }
    }

    private fun poll() {
        polling?.cancel()
        polling = viewModelScope.launch {
            while (isActive) {
                delay(POLL_MILLIS)
                val room = membership ?: return@launch
                if (_room.value?.decided != null) return@launch
                try {
                    val state = repository.state(room)
                    if (membership == room) show(state)
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    // Removed from the room, or the server forgot it: back to the start.
                    if (code(e) in GONE) {
                        reset()
                        _error.value = UiError(R.string.group_error_gone, canRetry = false)
                    } else {
                        Log.w(TAG, "poll failed", e)
                    }
                }
            }
        }
    }

    private fun show(state: RoomState) {
        val before = _room.value
        val asked = before?.question
        if (asked != null && asked.questionId != state.question?.questionId) {
            _history.value = _history.value.orEmpty() + AnsweredQuestion(asked.text, before.myAnswer ?: AnswerId.UNKNOWN)
        }
        _room.value = state
    }

    private fun reset() {
        polling?.cancel()
        membership = null
        _room.value = null
        _history.value = emptyList()
    }

    private fun fail(e: Exception, code: String?) {
        _error.value = when {
            e is IOException -> UiError(R.string.error_no_server, canRetry = false)
            else -> when (code) {
                RoomApi.ROOM_NOT_FOUND -> UiError(R.string.group_error_not_found, canRetry = false)
                RoomApi.ROOM_STARTED -> UiError(R.string.group_error_started, canRetry = false)
                RoomApi.ROOM_FULL -> UiError(R.string.group_error_full, canRetry = false)
                RoomApi.GROUP_UNAVAILABLE -> UiError(R.string.group_error_unavailable, canRetry = false)
                else -> UiError(R.string.error_server, canRetry = false)
            }
        }
        if (e !is HttpException && e !is IOException) Log.w(TAG, "room request failed", e)
    }

    private fun code(e: Exception): String? = (e as? HttpException)?.response()?.errorBody()?.let { body ->
        try {
            RetrofitInstance.gson.fromJson(body.charStream(), ErrorBody::class.java)?.error?.code
        } catch (_: Exception) {
            null
        }
    }

    private companion object {
        const val TAG = "GroupViewModel"
        const val POLL_MILLIS = 1000L
        val GONE = setOf(RoomApi.ROOM_NOT_FOUND, RoomApi.NOT_MEMBER)
    }
}

/** A room error's body; its 409 state is left to the next poll. */
private data class ErrorBody(val error: ApiError?)

class GroupViewModelFactory(private val repository: RoomRepository) : ViewModelProvider.Factory {
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        if (modelClass.isAssignableFrom(GroupViewModel::class.java)) {
            @Suppress("UNCHECKED_CAST")
            return GroupViewModel(repository) as T
        }
        throw IllegalArgumentException("Unknown ViewModel class")
    }
}
