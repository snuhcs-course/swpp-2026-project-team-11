package com.example.metchu.ui.main

import com.example.metchu.data.model.Food

/** A cafeteria marked on the result map. */
data class CafeteriaPin(val name: String, val lat: Double, val lng: Double)

/** The located cafeterias serving [food], once each even when they serve it at several meals. */
fun cafeteriaPins(food: Food): List<CafeteriaPin> =
    food.offers.mapNotNull { offer ->
        val lat = offer.lat ?: return@mapNotNull null
        val lng = offer.lng ?: return@mapNotNull null
        CafeteriaPin(offer.restaurant, lat, lng)
    }.distinct()

/**
 * Space kept on each side around the pins of a [width] x [height] map, in pixels: a fifth of the
 * shorter side, so the pins keep the middle three fifths on any screen density.
 */
fun boundsPadding(width: Int, height: Int): Int = minOf(width, height) / 5
