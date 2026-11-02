package com.example.metchu.ui.result

import com.example.metchu.data.model.Food
import com.example.metchu.data.model.Offer
import com.example.metchu.data.repository.Place
import kotlin.math.asin
import kotlin.math.ceil
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt

/** A place on the map, in degrees. */
data class Point(val lat: Double, val lng: Double)

/**
 * One cafeteria serving the dish at one meal. [meters] is the straight-line distance from
 * the user: from the phone's current position, or the server's `distance_m` from where the
 * session started until the phone has one.
 */
data class Cafeteria(val offer: Offer, val meters: Int?) {
    val point: Point? get() = if (offer.lat != null && offer.lng != null) Point(offer.lat, offer.lng) else null
    val walkMinutes: Int? get() = meters?.let { ceil(it / WALK_METERS_PER_MINUTE).toInt().coerceAtLeast(1) }
}

/** Why the result sheet lists every cafeteria although [Place.NEAR] was picked. */
enum class AllListed { NONE_NEAR, NO_LOCATION }

/** What the result sheet lists. [allListed] says why [Place.NEAR] did not narrow the list, if it did not. */
data class CafeteriaList(val cafeterias: List<Cafeteria>, val allListed: AllListed?)

/**
 * The cafeterias serving [food], one line per cafeteria and meal (times and prices can
 * differ), nearest first when the distance is known. The server cuts no distance by
 * default, so [Place.NEAR] keeps those within a 10-minute walk here, or all of them when
 * none is that close or no distance is known.
 */
fun cafeteriaList(food: Food, user: Point?, place: Place): CafeteriaList {
    val all = food.offers.distinctBy { it.restaurant to it.meal }.map { offer ->
        val meters = if (user != null && offer.lat != null && offer.lng != null) {
            distanceMeters(user, Point(offer.lat, offer.lng))
        } else offer.distanceM
        Cafeteria(offer, meters)
    }.sortedWith(compareBy(nullsLast()) { it.meters })
    if (place == Place.ANY || all.isEmpty()) return CafeteriaList(all, null)
    if (all.all { it.meters == null }) return CafeteriaList(all, AllListed.NO_LOCATION)
    val near = all.filter { it.meters != null && it.meters <= NEAR_METERS }
    return if (near.isEmpty()) CafeteriaList(all, AllListed.NONE_NEAR) else CafeteriaList(near, null)
}

/** Great-circle distance; on campus the error against a walking route is far larger. */
fun distanceMeters(from: Point, to: Point): Int {
    val dLat = Math.toRadians(to.lat - from.lat)
    val dLng = Math.toRadians(to.lng - from.lng)
    val h = sin(dLat / 2).let { it * it } +
        cos(Math.toRadians(from.lat)) * cos(Math.toRadians(to.lat)) * sin(dLng / 2).let { it * it }
    return (2 * EARTH_METERS * asin(sqrt(h))).roundToInt()
}

private const val EARTH_METERS = 6_371_000.0

/** About 4.8 km/h, a relaxed campus walk. */
const val WALK_METERS_PER_MINUTE = 80.0
const val NEAR_METERS = 800
