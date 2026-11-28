package com.example.metchu.ui.result

import com.example.metchu.data.model.Food
import com.example.metchu.data.model.Offer

/** A place on the map, in degrees. */
data class Point(val lat: Double, val lng: Double)

/** One cafeteria serving the dish at one meal. */
data class Cafeteria(val offer: Offer) {
    val point: Point? get() = if (offer.lat != null && offer.lng != null) Point(offer.lat, offer.lng) else null
}

/**
 * The cafeterias serving [food], one line per cafeteria, meal and sales menu (times and
 * prices can differ), in the server's order. The session already holds only the picked area.
 */
fun cafeteriaList(food: Food): List<Cafeteria> =
    food.offers.distinctBy { Triple(it.restaurant, it.meal, it.menuName) }.map(::Cafeteria)
