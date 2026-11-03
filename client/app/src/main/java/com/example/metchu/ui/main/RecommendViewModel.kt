package com.example.metchu.ui.main

import android.util.Log
import androidx.annotation.StringRes
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.example.metchu.R
import com.example.metchu.data.location.LocationSource
import com.example.metchu.data.model.Allergen
import com.example.metchu.data.model.Ban
import com.example.metchu.data.model.MenuDish
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.model.Step
import com.example.metchu.data.network.ApiError
import com.example.metchu.data.repository.RecommendRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.IOException

/** What the error banner shows. [canRetry] offers to repeat the failed request. */
data class UiError(@StringRes val message: Int, val canRetry: Boolean)

/** A question the user has answered in this session, newest last. */
data class AnsweredQuestion(val text: String, val answerId: String)

/**
 * Owns the session and the coroutine boundary. The Activity observes LiveData and
 * forwards taps; it never touches Retrofit.
 *
 * [session] is null before a session starts. Every successful call replaces it with
 * the server's state, so the screen is always drawn from the engine's current step.
 * One request runs at a time: taps while [loading] is true are ignored, which is
 * what keeps a double tap from answering the next question by accident.
 *
 * [history] lists the answered questions for the question screen. The server keeps
 * no question texts, so the phone remembers them, and trims the list to the
 * server's `question_count` after every reply so the two never disagree.
 * [shown] lists the guesses this session has proposed, for the result screen.
 * [reasons] holds the latest explanation for each proposal, null while it is being
 * written; changing the answers invalidates that proposal's explanation.
 * [menus] holds the dishes of each restaurant asked for in this session, null while
 * they load; a failed request leaves no entry, so asking again retries it.
 * [banned] lists the dishes and groups the user banned in this session; the server
 * keeps them out of its later proposals until the session ends.
 */
class RecommendViewModel(private val repository: RecommendRepository) : ViewModel() {

    private val _session = MutableLiveData<SessionState?>(null)
    val session: LiveData<SessionState?> = _session

    private val _loading = MutableLiveData(false)
    val loading: LiveData<Boolean> = _loading

    private val _error = MutableLiveData<UiError?>(null)
    val error: LiveData<UiError?> = _error

    private val _history = MutableLiveData<List<AnsweredQuestion>>(emptyList())
    val history: LiveData<List<AnsweredQuestion>> = _history

    private val _shown = MutableLiveData<List<Step>>(emptyList())
    val shown: LiveData<List<Step>> = _shown

    private data class ReasonContext(val foodId: Int, val answers: List<AnsweredQuestion>)
    private val _reasons = MutableLiveData<Map<String, String?>>(emptyMap())
    val reasons: LiveData<Map<String, String?>> = _reasons
    private val reasonContexts = mutableMapOf<String, ReasonContext>()

    private val _banned = MutableLiveData<Set<Ban>>(emptySet())
    val banned: LiveData<Set<Ban>> = _banned

    private val _menus = MutableLiveData<Map<String, List<MenuDish>?>>(emptyMap())
    val menus: LiveData<Map<String, List<MenuDish>?>> = _menus

    private var lastRequest: (suspend () -> SessionState)? = null
    private var lastAnswered: AnsweredQuestion? = null

    /**
     * [meal] is "BR", "LU", "DN" or null for the whole day. [engine] is one of the
     * Engine IDs, or null for the server's default. [location] says where the user is; finding
     * that can take a few seconds, so it is part of the request and shows as [loading]. No dish
     * with one of [allergies] is proposed. [language] ("en" or "ko") is the language of every
     * text the server sends.
     */
    fun start(
        meal: String?,
        engine: String? = null,
        location: LocationSource? = null,
        allergies: List<Allergen> = emptyList(),
        language: String? = null
    ) {
        if (_loading.value == true) return
        forgetSession()
        request { repository.createSession(meal, engine, location?.current(), allergies, language) }
    }

    /**
     * Answers the current question if it is still [asked]: the question screen holds a
     * picked answer for a moment, and Back can move the session on meanwhile.
     */
    fun answer(answerId: String, asked: Step) {
        val current = _session.value ?: return
        if (current.step != asked) return
        val questionId = current.step.questionId ?: return
        request(answered = AnsweredQuestion(current.step.text, answerId)) {
            repository.answer(current.sessionId, questionId, answerId)
        }
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

    /** Keeps what [ban] covers out of the rest of the session, or with [banned] false lets it back. */
    fun ban(ban: Ban, banned: Boolean) {
        val current = _session.value ?: return
        request {
            repository.ban(current.sessionId, ban, banned).also {
                _banned.value = if (banned) _banned.value.orEmpty() + ban else _banned.value.orEmpty() - ban
            }
        }
    }

    /**
     * The server cannot tell a repeated undo from a second one: sent twice, it goes
     * back two steps. If the reply to an undo is lost the server may already have
     * gone back, so Try again first reads the state and sends undo again only when
     * the server is still on the step this screen shows.
     */
    fun undo() {
        val current = _session.value ?: return
        request(retry = {
            val now = repository.state(current.sessionId)
            if (now != current) now else repository.undo(current.sessionId)
        }) { repository.undo(current.sessionId) }
    }

    /**
     * Returns to the question at [index] in [history] by undoing one step at a time
     * until the server is back on it. Try again first reads where the server is.
     */
    fun revisit(index: Int) {
        val current = _session.value ?: return
        val walkBack: suspend (SessionState) -> SessionState = { from ->
            var state = from
            while (state.canUndo && !(state.step.type == Step.QUESTION && state.step.questionCount <= index)) {
                state = repository.undo(state.sessionId)
            }
            state
        }
        request(retry = { walkBack(repository.state(current.sessionId)) }) { walkBack(current) }
    }

    /** Leaves the session and returns to the start screen. */
    fun startOver() {
        if (_loading.value == true) return
        _session.value = null
        _error.value = null
        forgetSession()
        lastRequest = null
    }

    fun retry() {
        lastRequest?.let { request(answered = lastAnswered, call = it) }
    }

    /**
     * [retry] is what Try again runs if [call] fails; by default [call] itself.
     * [answered] joins the history if the reply moves past the question.
     */
    private fun request(
        retry: (suspend () -> SessionState)? = null,
        answered: AnsweredQuestion? = null,
        call: suspend () -> SessionState
    ) {
        if (_loading.value == true) return
        lastRequest = retry ?: call
        lastAnswered = answered
        viewModelScope.launch {
            _loading.value = true
            _error.value = null
            try {
                show(call(), answered)
            } catch (e: CancellationException) {
                throw e
            } catch (e: HttpException) {
                Log.e(TAG, "request rejected: ${e.code()}", e)
                handleHttpError(e)
            } catch (e: IOException) {
                Log.e(TAG, "request failed", e)
                _error.value = UiError(R.string.error_no_server, canRetry = true)
            } catch (e: Exception) {
                // For example a reply that is not the JSON this app expects.
                Log.e(TAG, "unusable reply", e)
                _error.value = UiError(R.string.error_server, canRetry = true)
            } finally {
                _loading.value = false
            }
        }
    }

    private fun handleHttpError(e: HttpException) {
        val body = repository.errorBody(e)
        when {
            // The server moved on (for example an answer whose reply was lost, sent again):
            // show the step it is actually on, with the answer if it was recorded.
            e.code() == 409 && body?.state != null -> show(body.state, lastAnswered)
            // The server restarted and forgot the session.
            e.code() == 404 -> {
                lastRequest = null
                _session.value = null
                forgetSession()
                _error.value = UiError(R.string.error_session_lost, canRetry = false)
            }
            // An older API can reject a new engine ID at session creation.
            e.code() == 400 && body?.error?.code == ApiError.INVALID_REQUEST && _session.value == null -> {
                lastRequest = null
                _error.value = UiError(R.string.error_session_settings, canRetry = false)
            }
            // Missing engine configuration or incompatible catalogue features.
            e.code() == 503 && body?.error?.code == ApiError.ENGINE_UNAVAILABLE -> {
                lastRequest = null
                _error.value = UiError(R.string.error_engine_unavailable, canRetry = false)
            }
            // Cloudflare answers 530 when nothing is behind a tunnel (serve_public stopped).
            e.code() == 530 -> _error.value = UiError(R.string.error_no_server, canRetry = true)
            else -> _error.value = UiError(R.string.error_server, canRetry = true)
        }
    }

    private fun show(state: SessionState, answered: AnsweredQuestion? = null) {
        _history.value = (_history.value.orEmpty() + listOfNotNull(answered)).take(state.step.questionCount)
        if (state.step.type == Step.GUESS) {
            val shown = _shown.value.orEmpty()
            _shown.value = if (shown.none { it.guessId == state.step.guessId }) shown + state.step
                else shown.map { if (it.guessId == state.step.guessId) state.step else it }
        }
        _session.value = state
        val proposal = state.step.proposalId ?: return
        val food = state.step.food ?: return
        val context = ReasonContext(food.foodId, _history.value.orEmpty())
        if (reasonContexts[proposal] == context) return
        reasonContexts[proposal] = context
        _reasons.value = _reasons.value.orEmpty() + (proposal to null)
        explain(state.sessionId, proposal, context)
    }

    private fun explain(sessionId: String, proposal: String, context: ReasonContext) {
        viewModelScope.launch {
            try {
                val reason = repository.reason(sessionId)
                if (current(sessionId, proposal, context)) {
                    _reasons.value = if (reason.foodId == context.foodId) _reasons.value.orEmpty() + (proposal to reason.reason)
                        else _reasons.value.orEmpty() - proposal
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w(TAG, "no reason for the dish", e)
                if (current(sessionId, proposal, context)) _reasons.value = _reasons.value.orEmpty() - proposal
            }
        }
    }

    /** Loads what [restaurant] serves, unless it is loaded or loading. Runs beside other requests. */
    fun menu(restaurant: String) {
        val sessionId = _session.value?.sessionId ?: return
        if (restaurant in _menus.value.orEmpty()) return
        _menus.value = _menus.value.orEmpty() + (restaurant to null)
        viewModelScope.launch {
            val dishes = try {
                repository.menu(sessionId, restaurant)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w(TAG, "no menu for the restaurant", e)
                null
            }
            if (_session.value?.sessionId != sessionId) return@launch
            _menus.value = if (dishes != null) _menus.value.orEmpty() + (restaurant to dishes)
                else _menus.value.orEmpty() - restaurant
        }
    }

    private fun current(sessionId: String, proposal: String, context: ReasonContext) =
        _session.value?.sessionId == sessionId && reasonContexts[proposal] === context

    private fun forgetSession() {
        _history.value = emptyList()
        _shown.value = emptyList()
        _reasons.value = emptyMap()
        reasonContexts.clear()
        _menus.value = emptyMap()
        _banned.value = emptySet()
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
