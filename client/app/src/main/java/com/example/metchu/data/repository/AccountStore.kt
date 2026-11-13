package com.example.metchu.data.repository

import android.content.Context
import com.example.metchu.data.network.AccountUser

/** The account signed in on this device, with the token that proves it to the server. */
data class Account(val token: String, val user: AccountUser)

/** Where the signed-in account is kept; null means a guest. Unit tests keep it in memory. */
interface AccountStore {
    var account: Account?
}

/**
 * Kept in its own preferences file, which Android's backup leaves out
 * (res/xml/backup_rules.xml), so a token never travels to another device.
 */
class DeviceAccountStore(context: Context) : AccountStore {
    private val prefs = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    override var account: Account?
        get() {
            val token = prefs.getString(TOKEN, null) ?: return null
            val username = prefs.getString(USERNAME, null) ?: return null
            return Account(token, AccountUser(username, prefs.getString(GOOGLE_EMAIL, null), prefs.getBoolean(HAS_PASSWORD, true)))
        }
        set(value) {
            prefs.edit().apply {
                clear()
                if (value != null) {
                    putString(TOKEN, value.token)
                    putString(USERNAME, value.user.username)
                    putString(GOOGLE_EMAIL, value.user.googleEmail)
                    putBoolean(HAS_PASSWORD, value.user.hasPassword)
                }
            }.apply()
        }

    companion object {
        const val FILE = "account"
        private const val TOKEN = "token"
        private const val USERNAME = "username"
        private const val GOOGLE_EMAIL = "google_email"
        private const val HAS_PASSWORD = "has_password"
    }
}
