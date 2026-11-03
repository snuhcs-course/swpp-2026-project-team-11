package com.example.metchu.data.repository

import android.content.Context
import com.example.metchu.data.model.Engine

/** How far the user will walk. The server has no distance filter, so the result screen applies it. */
enum class Place { NEAR, ANY }

/** How far the first launch has got: the language, the allergies, then a tip on the start screen. */
enum class Setup { LANGUAGE, ALLERGIES, TIP, DONE }

/** RL unless the decision tree was picked: the LLM engine is switched off, so a stored choice of it falls back too. */
fun usableEngine(stored: String?): String = if (stored == Engine.DECISION_TREE) stored else Engine.RL

/** The start and settings screens' choices and the first launch's progress, kept on this device between launches. */
class SettingsStore(context: Context) {
    private val prefs = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    /** One of the [Engine] IDs. */
    var engine: String
        get() = usableEngine(prefs.getString(ENGINE, null))
        set(value) = prefs.edit().putString(ENGINE, value).apply()

    var place: Place
        get() = runCatching { Place.valueOf(prefs.getString(PLACE, null).orEmpty()) }.getOrDefault(Place.NEAR)
        set(value) = prefs.edit().putString(PLACE, value.name).apply()

    var setup: Setup
        get() = runCatching { Setup.valueOf(prefs.getString(SETUP, null).orEmpty()) }.getOrDefault(Setup.LANGUAGE)
        set(value) = prefs.edit().putString(SETUP, value.name).apply()

    private companion object {
        const val FILE = "settings"
        const val ENGINE = "engine"
        const val PLACE = "place"
        const val SETUP = "setup"
    }
}
