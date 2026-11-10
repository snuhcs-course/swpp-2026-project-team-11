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
 */
class AccountViewModel(private val repository: AuthRepository) : ViewModel() {

    private val _account = MutableLiveData(repository.account)
    val account: LiveData<Account?> = _account

    private val _busy = MutableLiveData(false)
    val busy: LiveData<Boolean> = _busy

    private val _error = MutableLiveData<Int?>(null)
    val error: LiveData<Int?> = _error

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
                _busy.value = false
            }
        }
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
            repository.forget()
            _account.value = null
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
