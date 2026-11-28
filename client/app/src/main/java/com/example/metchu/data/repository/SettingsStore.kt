package com.example.metchu.data.repository

import android.content.Context
import com.example.metchu.data.model.Engine
import com.example.metchu.data.network.RoomApi

/**
 * A place the user picked to eat, instead of the phone's location; [id] is one of the server's
 * `areas` (backend/recommend/areas.py): the campus cafeterias or the restaurants near one station.
 * The user picks one or more; all three keep every restaurant.
 */
enum class Area(val id: String) { CAMPUS("campus"), SNU_STATION("snu_station"), NAKSEONGDAE("nakseongdae") }

/**
 * A price range, picked as one to three ₩ signs; [level] is one of the server's `price_levels`
 * (backend/recommend/prices.py). The user picks one or more; all three are any price. The price
 * guide shows each band.
 */
enum class Price(val level: Int) { LOW(1), MID(2), HIGH(3) }

/** The picked areas' IDs in the server's order. */
fun Set<Area>.ids(): List<String> = Area.entries.filter { it in this }.map { it.id }

/** The picked price levels in order. */
fun Set<Price>.levels(): List<Int> = Price.entries.filter { it in this }.map { it.level }

/**
 * The areas kept by names joined with commas ([stored], "" for none), or else the single area
 * an app from before i5-A7 kept ([legacy]): "ALL" or nothing is every area.
 */
fun storedAreas(stored: String?, legacy: String?): Set<Area> = picks(stored, legacy, Area.entries)

/** As [storedAreas], for the price ranges: "ANY" or nothing is every one. */
fun storedPrices(stored: String?, legacy: String?): Set<Price> = picks(stored, legacy, Price.entries)

private fun <T : Enum<T>> picks(stored: String?, legacy: String?, entries: List<T>): Set<T> =
    stored?.split(",")?.mapNotNull { name -> entries.firstOrNull { it.name == name } }?.toSet()
        ?: entries.firstOrNull { it.name == legacy }?.let { setOf(it) }
        ?: entries.toSet()

/** Names joined with commas, as [storedAreas] and [storedPrices] read them. */
private fun Set<Enum<*>>.joined(): String = sortedBy { it.ordinal }.joinToString(",") { it.name }

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

    /** Every area at first; possibly none, which the start screen asks to change. */
    var areas: Set<Area>
        get() = storedAreas(prefs.getString(AREAS, null), prefs.getString(LEGACY_AREA, null))
        set(value) = prefs.edit().putString(AREAS, value.joined()).apply()

    /** Every price range at first; possibly none, which the start screen asks to change. */
    var prices: Set<Price>
        get() = storedPrices(prefs.getString(PRICES, null), prefs.getString(LEGACY_PRICE, null))
        set(value) = prefs.edit().putString(PRICES, value.joined()).apply()

    /** How long each question of a room this phone creates waits: one of [RoomApi.ROUND_SECONDS]. */
    var roundSeconds: Int
        get() = prefs.getInt(ROUND_SECONDS, RoomApi.DEFAULT_ROUND_SECONDS).takeIf { it in RoomApi.ROUND_SECONDS } ?: RoomApi.DEFAULT_ROUND_SECONDS
        set(value) = prefs.edit().putInt(ROUND_SECONDS, value).apply()

    var setup: Setup
        get() = runCatching { Setup.valueOf(prefs.getString(SETUP, null).orEmpty()) }.getOrDefault(Setup.LANGUAGE)
        set(value) = prefs.edit().putString(SETUP, value.name).apply()

    private companion object {
        const val FILE = "settings"
        const val ENGINE = "engine"
        const val AREAS = "areas"
        const val PRICES = "prices"
        /** The single choice an app from before i5-A7 kept, read until a new one is stored. */
        const val LEGACY_AREA = "area"
        const val LEGACY_PRICE = "price"
        const val ROUND_SECONDS = "round_seconds"
        const val SETUP = "setup"
    }
}
