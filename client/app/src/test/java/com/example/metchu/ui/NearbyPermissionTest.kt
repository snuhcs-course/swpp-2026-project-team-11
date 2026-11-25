package com.example.metchu.ui

import com.example.metchu.data.repository.Place
import com.example.metchu.ui.common.LocationAnswer
import com.example.metchu.ui.common.locationAnswer
import com.example.metchu.ui.start.nearAnswered
import com.example.metchu.ui.start.pickPlace
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class NearbyPermissionTest {

    private val picked = mutableListOf<Place>()
    private var refused: LocationAnswer? = null
    private var asked = false

    private fun pick(place: Place, granted: Boolean) = pickPlace(place, granted, { picked += it }) { asked = true }

    private fun answer(answer: LocationAnswer) = nearAnswered(asked, answer, { picked += it }) { refused = it }

    @Test
    fun nearbyWithoutPermissionAsksBeforeItIsPicked() {
        pick(Place.NEAR, granted = false)
        assertTrue(asked)
        assertEquals(emptyList<Place>(), picked)
    }

    @Test
    fun nearbyIsKeptWhenLocationIsAllowed() {
        pick(Place.NEAR, granted = false)
        answer(LocationAnswer.GRANTED)
        assertEquals(listOf(Place.NEAR), picked)
        assertNull(refused)
    }

    @Test
    fun aDenialFallsBackToAnywhereAndSaysWhy() {
        pick(Place.NEAR, granted = false)
        answer(LocationAnswer.DENIED)
        assertEquals(listOf(Place.ANY), picked)
        assertEquals(LocationAnswer.DENIED, refused)
    }

    @Test
    fun aBlockedRequestFallsBackToAnywhereToo() {
        pick(Place.NEAR, granted = false)
        answer(LocationAnswer.BLOCKED)
        assertEquals(listOf(Place.ANY), picked)
        assertEquals(LocationAnswer.BLOCKED, refused)
    }

    @Test
    fun withPermissionOrForAnywhereNothingIsAsked() {
        pick(Place.NEAR, granted = true)
        pick(Place.ANY, granted = false)
        assertFalse(asked)
        assertEquals(listOf(Place.NEAR, Place.ANY), picked)
    }

    @Test
    fun anAnswerNearbyDidNotAskForChangesNothing() {
        answer(LocationAnswer.GRANTED)
        answer(LocationAnswer.BLOCKED)
        assertEquals(emptyList<Place>(), picked)
        assertNull(refused)
    }

    @Test
    fun aRationaleAfterTheAnswerMeansAndroidAsksAgain() {
        assertEquals(LocationAnswer.GRANTED, locationAnswer(granted = true, rationaleBefore = true, rationaleAfter = false, refusedBefore = true))
        assertEquals(LocationAnswer.DENIED, locationAnswer(granted = false, rationaleBefore = false, rationaleAfter = true, refusedBefore = false))
        assertEquals(LocationAnswer.DENIED, locationAnswer(granted = false, rationaleBefore = true, rationaleAfter = true, refusedBefore = true))
    }

    @Test
    fun aFirstDialogClosedWithoutAnAnswerIsNotBlocked() {
        assertEquals(LocationAnswer.DENIED, locationAnswer(granted = false, rationaleBefore = false, rationaleAfter = false, refusedBefore = false))
    }

    @Test
    fun aRationaleGoneAfterTheRequestMeansASecondDenial() {
        assertEquals(LocationAnswer.BLOCKED, locationAnswer(granted = false, rationaleBefore = true, rationaleAfter = false, refusedBefore = false))
    }

    @Test
    fun noRationaleAfterAnEarlierRefusalIsBlocked() {
        // An earlier refusal includes a dialog closed unanswered and a phone blocked before the app remembered refusals.
        assertEquals(LocationAnswer.BLOCKED, locationAnswer(granted = false, rationaleBefore = false, rationaleAfter = false, refusedBefore = true))
    }
}
