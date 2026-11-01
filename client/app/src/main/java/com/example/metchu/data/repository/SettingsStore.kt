package com.example.metchu.data.repository

import android.content.Context
import com.example.metchu.data.model.Engine

/** How far the user will walk. The server has no distance filter, so the result screen applies it. */
enum class Place { NEAR, ANY }

/** The start and settings screens' choices, kept on this device between launches. */
class SettingsStore(context: Context) {
    private val prefs = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    /** One of the [Engine] IDs. */
    var engine: String
        get() = prefs.getString(ENGINE, Engine.DECISION_TREE) ?: Engine.DECISION_TREE
        set(value) = prefs.edit().putString(ENGINE, value).apply()

    var place: Place
        get() = runCatching { Place.valueOf(prefs.getString(PLACE, null).orEmpty()) }.getOrDefault(Place.NEAR)
        set(value) = prefs.edit().putString(PLACE, value.name).apply()

    private companion object {
        const val FILE = "settings"
        const val ENGINE = "engine"
        const val PLACE = "place"
    }
}
