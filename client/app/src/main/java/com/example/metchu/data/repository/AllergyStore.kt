package com.example.metchu.data.repository

import android.content.Context
import com.example.metchu.data.model.Allergen

/** A dish the user asked never to be suggested; [name] is how the result screen showed it. */
data class BannedDish(val foodId: Int, val name: String)

/**
 * The user's allergies and banned dishes, kept on this device only and sent with every
 * new session. [chosen] stays false until the allergy screen has been saved once, so
 * the app opens that screen on first launch.
 */
class AllergyStore(context: Context) {
    private val prefs = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    val chosen: Boolean get() = prefs.contains(KEY)

    /** In [Allergen] order. */
    var allergies: List<Allergen>
        get() {
            val ids = prefs.getStringSet(KEY, emptySet()).orEmpty()
            return Allergen.entries.filter { it.id in ids }
        }
        set(value) = prefs.edit().putStringSet(KEY, value.map { it.id }.toSet()).apply()

    /** By name. Each is kept as "<food ID>:<name>". */
    var banned: List<BannedDish>
        get() = prefs.getStringSet(BANNED, emptySet()).orEmpty().mapNotNull { entry ->
            entry.substringBefore(':').toIntOrNull()?.let { BannedDish(it, entry.substringAfter(':')) }
        }.sortedBy { it.name }
        set(value) = prefs.edit().putStringSet(BANNED, value.map { "${it.foodId}:${it.name}" }.toSet()).apply()

    private companion object {
        const val FILE = "profile"
        const val KEY = "allergies"
        const val BANNED = "banned"
    }
}
