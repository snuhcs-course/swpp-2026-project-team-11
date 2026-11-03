package com.example.metchu.ui

import com.example.metchu.Fixtures
import com.example.metchu.R
import com.example.metchu.data.model.Offer
import com.example.metchu.data.repository.Place
import com.example.metchu.ui.question.phaseText
import com.example.metchu.ui.question.progressFill
import com.example.metchu.ui.result.AllListed
import com.example.metchu.ui.result.Cafeteria
import com.example.metchu.ui.result.NEAR_METERS
import com.example.metchu.ui.result.Point
import com.example.metchu.ui.result.cafeteriaList
import com.example.metchu.ui.result.distanceMeters
import com.example.metchu.ui.result.framedPoints
import com.example.metchu.ui.start.Meal
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ProgressTest {

    @Test
    fun theBarFillsFastFirstAndNeverReachesTheEndBeforeADish() {
        assertEquals(0f, progressFill(0, null), 0f)
        assertEquals(0.28f, progressFill(1, null), 0.001f)
        assertTrue(progressFill(2, null) - progressFill(1, null) < progressFill(1, null))
        assertEquals(0.95f, progressFill(40, null), 0f)
    }

    @Test
    fun aQuestionCapKeepsTheBarAtLeastAtTheAnsweredShare() {
        // The curve alone would show 28 % after one answer; the cap says half done.
        assertEquals(0.5f, progressFill(1, 2), 0f)
        assertEquals(0.95f, progressFill(10, 10), 0f)
    }

    @Test
    fun thePhaseFollowsTheFill() {
        assertEquals(R.string.phase_start, phaseText(0.1f))
        assertEquals(R.string.phase_narrowing, phaseText(0.5f))
        assertEquals(R.string.phase_almost, phaseText(0.9f))
    }
}

class MealTest {

    @Test
    fun theStartScreenPicksTheNextMealByTheHour() {
        assertEquals(Meal.BREAKFAST, Meal.at(7))
        assertEquals(Meal.LUNCH, Meal.at(10))
        assertEquals(Meal.LUNCH, Meal.at(14))
        assertEquals(Meal.DINNER, Meal.at(15))
        assertEquals(Meal.DINNER, Meal.at(23))
    }

    @Test
    fun mealCodesAreTheServers() {
        assertEquals(listOf("BR", "LU", "DN"), Meal.entries.map { it.code })
        assertEquals(Meal.DINNER, Meal.of("DN"))
        assertEquals(null, Meal.of(null))
    }
}

class CafeteriasTest {

    private val food = Fixtures.state("recommendation").step.food!!
    private val near = Offer("220동식당", "LU", 5900, 37.46451, 126.95424, null)
    private val far = Offer("301동식당", "LU", 6000, 37.44951, 126.95224, null)
    private val unlocated = Offer("기숙사식당", "LU", null, null, null, null)
    private val user = Point(37.46400, 126.95400)

    @Test
    fun distanceIsMetersOnTheGround() {
        val meters = distanceMeters(Point(37.4600, 126.9520), Point(37.4690, 126.9520))
        assertEquals(1001.0, meters.toDouble(), 2.0)
    }

    @Test
    fun cafeteriasAreListedNearestFirstAndUnlocatedLast() {
        val list = cafeteriaList(food.copy(offers = listOf(unlocated, far, near)), user, Place.ANY)
        assertEquals(listOf(near, far, unlocated), list.cafeterias.map { it.offer })
        assertEquals(1, list.cafeterias.first().walkMinutes)
        assertNull(list.allListed)
    }

    @Test
    fun nearbyKeepsTheCafeteriasWithinATenMinuteWalk() {
        val list = cafeteriaList(food.copy(offers = listOf(far, near)), user, Place.NEAR)
        assertEquals(listOf(near), list.cafeterias.map { it.offer })
        assertTrue(list.cafeterias.all { it.meters!! <= NEAR_METERS })
    }

    @Test
    fun nearbyWithNothingCloseListsEveryCafeteriaAndSaysSo() {
        val list = cafeteriaList(food.copy(offers = listOf(far)), user, Place.NEAR)
        assertEquals(listOf(far), list.cafeterias.map { it.offer })
        assertEquals(AllListed.NONE_NEAR, list.allListed)
    }

    @Test
    fun withoutAnyDistanceNearbyListsEveryCafeteriaAndSaysTheLocationIsUnknown() {
        val list = cafeteriaList(food.copy(offers = listOf(far, near)), null, Place.NEAR)
        assertEquals(listOf(far, near), list.cafeterias.map { it.offer })
        assertTrue(list.cafeterias.all { it.meters == null })
        assertEquals(AllListed.NO_LOCATION, list.allListed)
        assertNull(cafeteriaList(food.copy(offers = listOf(far, near)), null, Place.ANY).allListed)
    }

    @Test
    fun theServersDistanceStandsInUntilThePhoneHasAPosition() {
        val offers = listOf(far.copy(distanceM = 1500), near.copy(distanceM = 120))
        val list = cafeteriaList(food.copy(offers = offers), null, Place.NEAR)
        assertEquals(listOf(120), list.cafeterias.map { it.meters })
        assertEquals(listOf(near.restaurant, far.restaurant), cafeteriaList(food.copy(offers = offers), user, Place.ANY).cafeterias.map { it.offer.restaurant })
    }

    @Test
    fun theMapFramesTheUserWithTheCafeteriasOnlyWhenNearOne() {
        val cafeterias = listOf(Cafeteria(near, null), Cafeteria(far, null), Cafeteria(unlocated, null))
        val points = listOf(Point(near.lat!!, near.lng!!), Point(far.lat!!, far.lng!!))
        assertEquals(points + user, framedPoints(cafeterias, user))
        assertEquals(points, framedPoints(cafeterias, Point(37.3861, -122.0839)))
        assertEquals(points, framedPoints(cafeterias, null))
    }

    @Test
    fun aCafeteriaServingSeveralMealsGetsALineForEach() {
        val dinner = near.copy(meal = "DN", price = 6500)
        val list = cafeteriaList(food.copy(offers = listOf(near, dinner, near)), user, Place.ANY)
        assertEquals(listOf(near, dinner), list.cafeterias.map { it.offer })
    }
}
