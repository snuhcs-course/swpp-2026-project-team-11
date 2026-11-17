package com.example.metchu.data.repository

import android.content.Context
import com.example.metchu.data.model.Engine

/** How far the user will walk. The server has no distance filter, so the result screen applies it. */
enum class Place { NEAR, ANY }

/**
 * The price range, picked as one to three ₩ signs; [level] is what the server filters by
 * (backend/recommend/prices.py), null for any price. The price guide shows each band.
 */
enum class Price(val level: Int?) { ANY(null), LOW(1), MID(2), HIGH(3) }

/**
 * How far the first launch has got: the language, an optional account, the allergies, then a
 * tip on the start screen. Stored by name, so a step added here does not shift the others.
 */
enum class Setup { LANGUAGE, ACCOUNT, ALLERGIES, TIP, DONE }

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

    var price: Price
        get() = runCatching { Price.valueOf(prefs.getString(PRICE, null).orEmpty()) }.getOrDefault(Price.ANY)
        set(value) = prefs.edit().putString(PRICE, value.name).apply()

    var setup: Setup
        get() = runCatching { Setup.valueOf(prefs.getString(SETUP, null).orEmpty()) }.getOrDefault(Setup.LANGUAGE)
        set(value) = prefs.edit().putString(SETUP, value.name).apply()

    private companion object {
        const val FILE = "settings"
        const val ENGINE = "engine"
        const val PLACE = "place"
        const val PRICE = "price"
        const val SETUP = "setup"
    }
}
