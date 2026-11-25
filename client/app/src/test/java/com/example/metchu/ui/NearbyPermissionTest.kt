package com.example.metchu.ui

import com.example.metchu.data.repository.Place
import com.example.metchu.ui.common.LocationAnswer
import com.example.metchu.ui.common.locationAnswer
import com.example.metchu.ui.start.pickPlace
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class NearbyPermissionTest {

    private val picked = mutableListOf<Place>()
    private var refused: LocationAnswer? = null
    private var asked: ((LocationAnswer) -> Unit)? = null

    private fun pick(place: Place, granted: Boolean) =
        pickPlace(place, granted, { asked = it }, { picked += it }) { refused = it }

    @Test
    fun nearbyWithoutPermissionAsksBeforeItIsPicked() {
        pick(Place.NEAR, granted = false)
        assertTrue(asked != null)
        assertEquals(emptyList<Place>(), picked)
    }

    @Test
    fun nearbyIsKeptWhenLocationIsAllowed() {
        pick(Place.NEAR, granted = false)
        asked!!(LocationAnswer.GRANTED)
        assertEquals(listOf(Place.NEAR), picked)
        assertNull(refused)
    }

    @Test
    fun aDenialFallsBackToAnywhereAndSaysWhy() {
        pick(Place.NEAR, granted = false)
        asked!!(LocationAnswer.DENIED)
        assertEquals(listOf(Place.ANY), picked)
        assertEquals(LocationAnswer.DENIED, refused)
    }

    @Test
    fun aBlockedRequestFallsBackToAnywhereToo() {
        pick(Place.NEAR, granted = false)
        asked!!(LocationAnswer.BLOCKED)
        assertEquals(listOf(Place.ANY), picked)
        assertEquals(LocationAnswer.BLOCKED, refused)
    }

    @Test
    fun withPermissionOrForAnywhereNothingIsAsked() {
        pick(Place.NEAR, granted = true)
        pick(Place.ANY, granted = false)
        assertNull(asked)
        assertEquals(listOf(Place.NEAR, Place.ANY), picked)
    }

    @Test
    fun noRationaleAfterADenialMeansAndroidWillNotAskAgain() {
        assertEquals(LocationAnswer.GRANTED, locationAnswer(granted = true, canAskAgain = false))
        assertEquals(LocationAnswer.DENIED, locationAnswer(granted = false, canAskAgain = true))
        assertEquals(LocationAnswer.BLOCKED, locationAnswer(granted = false, canAskAgain = false))
    }
}
