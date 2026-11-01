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

/** One cafeteria serving the dish. [meters] is the straight-line distance from the user, if known. */
data class Cafeteria(val offer: Offer, val meters: Int?) {
    val point: Point? get() = if (offer.lat != null && offer.lng != null) Point(offer.lat, offer.lng) else null
    val walkMinutes: Int? get() = meters?.let { ceil(it / WALK_METERS_PER_MINUTE).toInt().coerceAtLeast(1) }
}

/** What the result sheet lists. [widened] is true when [Place.NEAR] found nothing close, so all are listed. */
data class CafeteriaList(val cafeterias: List<Cafeteria>, val widened: Boolean)

/**
 * The cafeterias serving [food], once each, nearest first when [user] is known. The server
 * has no distance filter, so [Place.NEAR] keeps those within a 10-minute walk here, or all
 * of them when none is that close.
 */
fun cafeteriaList(food: Food, user: Point?, place: Place): CafeteriaList {
    val all = food.offers.distinctBy { it.restaurant }.map { offer ->
        val meters = if (user != null && offer.lat != null && offer.lng != null) {
            distanceMeters(user, Point(offer.lat, offer.lng))
        } else null
        Cafeteria(offer, meters)
    }.sortedWith(compareBy(nullsLast()) { it.meters })
    if (place == Place.ANY || user == null) return CafeteriaList(all, widened = false)
    val near = all.filter { it.meters != null && it.meters <= NEAR_METERS }
    return if (near.isEmpty()) CafeteriaList(all, widened = all.isNotEmpty()) else CafeteriaList(near, widened = false)
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
