package com.example.metchu.ui.main

import android.util.Log
import androidx.annotation.StringRes
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.example.metchu.R
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.repository.RecommendRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import retrofit2.HttpException

/** What the error banner shows. [canRetry] offers to repeat the failed request. */
data class UiError(@StringRes val message: Int, val canRetry: Boolean)

/**
 * Owns the session and the coroutine boundary. The Activity observes LiveData and
 * forwards taps; it never touches Retrofit.
 *
 * [session] is null before a session starts. Every successful call replaces it with
 * the server's state, so the screen is always drawn from the engine's current step.
 * One request runs at a time: taps while [loading] is true are ignored, which is
 * what keeps a double tap from answering the next question by accident.
 */
class RecommendViewModel(private val repository: RecommendRepository) : ViewModel() {

    private val _session = MutableLiveData<SessionState?>(null)
    val session: LiveData<SessionState?> = _session

    private val _loading = MutableLiveData(false)
    val loading: LiveData<Boolean> = _loading

    private val _error = MutableLiveData<UiError?>(null)
    val error: LiveData<UiError?> = _error

    private var lastRequest: (suspend () -> SessionState)? = null

    /** [meal] is "BR", "LU", "DN" or null for the whole day. */
    fun start(meal: String?) = request { repository.createSession(meal) }

    fun answer(answerId: String) {
        val current = _session.value ?: return
        val questionId = current.step.questionId ?: return
        request { repository.answer(current.sessionId, questionId, answerId) }
    }

    fun feedback(accepted: Boolean) {
        val current = _session.value ?: return
        val guessId = current.step.guessId ?: return
        request { repository.feedback(current.sessionId, guessId, accepted) }
    }

    fun recommendNow() {
        val current = _session.value ?: return
        request { repository.recommendNow(current.sessionId) }
    }

    fun undo() {
        val current = _session.value ?: return
        request { repository.undo(current.sessionId) }
    }

    /** Leaves the session and returns to the start screen. */
    fun startOver() {
        if (_loading.value == true) return
        _session.value = null
        _error.value = null
    }

    fun retry() {
        lastRequest?.let { request(it) }
    }

    private fun request(call: suspend () -> SessionState) {
        if (_loading.value == true) return
        lastRequest = call
        viewModelScope.launch {
            _loading.value = true
            _error.value = null
            try {
                _session.value = call()
            } catch (e: CancellationException) {
                throw e
            } catch (e: HttpException) {
                Log.e(TAG, "request rejected: ${e.code()}", e)
                handleHttpError(e)
            } catch (e: Exception) {
                Log.e(TAG, "request failed", e)
                _error.value = UiError(R.string.error_no_server, canRetry = true)
            } finally {
                _loading.value = false
            }
        }
    }

    private fun handleHttpError(e: HttpException) {
        val body = repository.errorBody(e)
        when {
            // The server moved on (for example a request that was sent twice):
            // show the step it is actually on.
            e.code() == 409 && body?.state != null -> _session.value = body.state
            // The server restarted and forgot the session.
            e.code() == 404 -> {
                _session.value = null
                _error.value = UiError(R.string.error_session_lost, canRetry = false)
            }
            else -> _error.value = UiError(R.string.error_server, canRetry = true)
        }
    }

    private companion object {
        const val TAG = "RecommendViewModel"
    }
}

/** Supplies the repository dependency when Android creates the ViewModel. */
class RecommendViewModelFactory(
    private val repository: RecommendRepository
) : ViewModelProvider.Factory {
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        if (modelClass.isAssignableFrom(RecommendViewModel::class.java)) {
            @Suppress("UNCHECKED_CAST")
            return RecommendViewModel(repository) as T
        }
        throw IllegalArgumentException("Unknown ViewModel class")
    }
}
