package com.example.metchu.ui.account

import android.util.Log
import androidx.annotation.StringRes
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.example.metchu.R
import com.example.metchu.data.network.AuthError
import com.example.metchu.data.network.Bookmark
import com.example.metchu.data.network.HistoryEntry
import com.example.metchu.data.repository.Account
import com.example.metchu.data.repository.AuthRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.IOException

/**
 * Signing up, in and out, and linking Google. [account] is null for a guest. One request
 * runs at a time: taps while [busy] is true are ignored. [error] is the string to show
 * under the form, cleared by the next request or [clearError].
 *
 * Google's account picker needs an Activity, so the screen passes the token request in
 * as a function; this ViewModel never holds the Activity.
 *
 * [bookmarks] and [history] are the signed-in account's lists, null until loaded and for a
 * guest; [savedFailed] is true when the last load failed. [toggleBookmark] changes the list at
 * once and puts it back if the server refuses, ignoring taps on a restaurant whose change is on its
 * way. A list loaded while a change was on its way keeps that change, so a reload never undoes it.
 * A bookmark is one per restaurant, by the name a result shows.
 */
class AccountViewModel(private val repository: AuthRepository) : ViewModel() {

    private val _account = MutableLiveData(repository.account)
    val account: LiveData<Account?> = _account

    private val _busy = MutableLiveData(false)
    val busy: LiveData<Boolean> = _busy

    private val _error = MutableLiveData<Int?>(null)
    val error: LiveData<Int?> = _error

    private val _bookmarks = MutableLiveData<List<Bookmark>?>(null)
    val bookmarks: LiveData<List<Bookmark>?> = _bookmarks

    private val _history = MutableLiveData<List<HistoryEntry>?>(null)
    val history: LiveData<List<HistoryEntry>?> = _history

    private val _savedFailed = MutableLiveData(false)
    val savedFailed: LiveData<Boolean> = _savedFailed

    private val pending = mutableSetOf<String>()

    /** Each restaurant's latest state here (null: removed) and when it changed, for lists loaded meanwhile. */
    private val changed = mutableMapOf<String, Pair<Bookmark?, Int>>()
    private var changes = 0

    init {
        // The saved account may have been revoked while the app was closed.
        if (repository.account != null) viewModelScope.launch {
            try {
                _account.value = repository.refresh()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w(TAG, "saved account not confirmed; still signed in", e)
            }
        }
    }

    fun logIn(username: String, password: String) {
        if (username.isBlank() || password.isEmpty()) return fail(R.string.account_error_empty)
        request { repository.logIn(username.trim(), password) }
    }

    fun signUp(username: String, password: String, confirmation: String) {
        if (username.isBlank() || password.isEmpty()) return fail(R.string.account_error_empty)
        if (password != confirmation) return fail(R.string.account_error_mismatch)
        request { repository.signUp(username.trim(), password) }
    }

    /** [idToken] asks Google for a token; null means the user closed the picker. */
    fun google(idToken: suspend () -> String?) = request { idToken()?.let { repository.google(it) } }

    fun linkGoogle(idToken: suspend () -> String?) = request { idToken()?.let { repository.linkGoogle(it) } }

    fun logOut() {
        if (_busy.value == true) return
        viewModelScope.launch {
            _busy.value = true
            _error.value = null
            try {
                repository.logOut()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                // The device has forgotten the account either way; the server's token stays until it is used.
                Log.w(TAG, "sign-out not confirmed by the server", e)
            } finally {
                _account.value = null
                forgetSaved()
                _busy.value = false
            }
        }
    }

    fun loadBookmarks() {
        val since = changes
        load(_bookmarks, { list -> withChanges(list, since) }) { repository.bookmarks() }
    }

    fun loadHistory() = load(_history, { it }) { repository.history() }

    /** [list] as loaded, with the changes made here since [since] or still on their way laid over it. */
    private fun withChanges(list: List<Bookmark>, since: Int): List<Bookmark> {
        val newer = changed.filter { (key, change) -> change.second > since || key in pending }
        val kept = list.filterNot { it.restaurant in newer }
        return newer.values.mapNotNull { it.first } + kept
    }

    private fun change(restaurant: String, now: Bookmark?) {
        changed[restaurant] = now to ++changes
    }

    /** Saves [restaurant] as a result shows it, or removes it if saved. */
    fun toggleBookmark(restaurant: String) {
        val token = _account.value?.token ?: return
        val saved = _bookmarks.value ?: return
        if (!pending.add(restaurant)) return
        val old = saved.firstOrNull { it.restaurant == restaurant }
        val added = Bookmark(restaurant)
        _bookmarks.value = if (old == null) listOf(added) + saved else saved - old
        change(restaurant, if (old == null) added else null)
        viewModelScope.launch {
            try {
                if (old == null) {
                    val kept = repository.bookmark(added)
                    if (_account.value?.token == token) {
                        _bookmarks.value = _bookmarks.value?.map { if (it.restaurant == restaurant) kept else it }
                        change(restaurant, kept)
                    }
                } else {
                    // A bookmark added here has its id once the reply is in, and taps wait for that.
                    repository.unbookmark(checkNotNull(old.id) { "Bookmark has no id" })
                    change(restaurant, null)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w(TAG, "bookmark not changed", e)
                if (_account.value?.token == token && !signedOutBy(e)) {
                    val now = _bookmarks.value.orEmpty().filterNot { it.restaurant == restaurant }
                    _bookmarks.value = if (old == null) now else listOf(old) + now
                    change(restaurant, old)
                }
            } finally {
                pending.remove(restaurant)
            }
        }
    }

    private fun <T> load(target: MutableLiveData<List<T>?>, adjust: (List<T>) -> List<T>, call: suspend () -> List<T>) {
        val token = _account.value?.token ?: return
        _savedFailed.value = false
        viewModelScope.launch {
            try {
                val list = call()
                if (_account.value?.token == token) target.value = adjust(list)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w(TAG, "saved list not loaded", e)
                if (_account.value?.token == token && !signedOutBy(e)) _savedFailed.value = true
            }
        }
    }

    /** Signs out here when the server no longer accepts this device's token. */
    private fun signedOutBy(e: Exception): Boolean {
        if (e !is HttpException || repository.errorCode(e) != AuthError.NOT_AUTHENTICATED) return false
        signOutHere()
        _error.value = R.string.account_error_signed_out
        return true
    }

    private fun signOutHere() {
        repository.forget()
        _account.value = null
        forgetSaved()
    }

    private fun forgetSaved() {
        changed.clear()
        _bookmarks.value = null
        _history.value = null
        _savedFailed.value = false
    }

    fun clearError() {
        _error.value = null
    }

    private fun fail(@StringRes message: Int) {
        _error.value = message
    }

    /** Runs [call]; a non-null result is the account now signed in. */
    private fun request(call: suspend () -> Account?) {
        if (_busy.value == true) return
        viewModelScope.launch {
            _busy.value = true
            _error.value = null
            try {
                call()?.let { _account.value = it }
            } catch (e: CancellationException) {
                throw e
            } catch (e: HttpException) {
                Log.e(TAG, "account request rejected: ${e.code()}", e)
                _error.value = messageFor(repository.errorCode(e))
            } catch (e: IOException) {
                Log.e(TAG, "account request failed", e)
                _error.value = R.string.error_no_server
            } catch (e: Exception) {
                // Google's picker failing (no account on the device, an unregistered app) or an unusable reply.
                Log.e(TAG, "sign-in failed", e)
                _error.value = R.string.account_error_google
            } finally {
                _busy.value = false
            }
        }
    }

    @StringRes
    private fun messageFor(code: String?): Int = when (code) {
        AuthError.INVALID_USERNAME -> R.string.account_error_username
        AuthError.USERNAME_TAKEN -> R.string.account_error_taken
        AuthError.WEAK_PASSWORD -> R.string.account_error_weak
        AuthError.INVALID_CREDENTIALS -> R.string.account_error_credentials
        AuthError.INVALID_GOOGLE_TOKEN -> R.string.account_error_google
        AuthError.GOOGLE_UNAVAILABLE -> R.string.account_error_google_unavailable
        AuthError.GOOGLE_IN_USE -> R.string.account_error_google_in_use
        AuthError.ALREADY_LINKED -> R.string.account_error_already_linked
        // The server no longer accepts this device's token: sign out here too.
        AuthError.NOT_AUTHENTICATED -> {
            signOutHere()
            R.string.account_error_signed_out
        }
        else -> R.string.error_server
    }

    private companion object {
        const val TAG = "AccountViewModel"
    }
}

/** Supplies the repository dependency when Android creates the ViewModel. */
class AccountViewModelFactory(private val repository: AuthRepository) : ViewModelProvider.Factory {
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        if (modelClass.isAssignableFrom(AccountViewModel::class.java)) {
            @Suppress("UNCHECKED_CAST")
            return AccountViewModel(repository) as T
        }
        throw IllegalArgumentException("Unknown ViewModel class")
    }
}
