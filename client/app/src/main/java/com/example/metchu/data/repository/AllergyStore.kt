package com.example.metchu.data.repository

import android.content.Context
import com.example.metchu.data.model.Allergen

/** The user's allergies, kept on this device only and sent with every new session. */
class AllergyStore(context: Context) {
    private val prefs = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    /** In [Allergen] order. */
    var allergies: List<Allergen>
        get() {
            val ids = prefs.getStringSet(KEY, emptySet()).orEmpty()
            return Allergen.entries.filter { it.id in ids }
        }
        set(value) = prefs.edit().putStringSet(KEY, value.map { it.id }.toSet()).apply()

    private companion object {
        const val FILE = "profile"
        const val KEY = "allergies"
    }
}
