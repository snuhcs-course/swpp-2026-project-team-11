package com.example.metchu.ui

import com.example.metchu.Fixtures
import com.example.metchu.data.model.Offer
import com.example.metchu.ui.main.CafeteriaPin
import com.example.metchu.ui.main.boundsPadding
import com.example.metchu.ui.main.cafeteriaPins
import org.junit.Assert.assertEquals
import org.junit.Test

class CafeteriaPinTest {

    private val food = Fixtures.state("recommendation").step.food!!

    @Test
    fun aLocatedOfferBecomesAPin() {
        assertEquals(listOf(CafeteriaPin("220동식당", 37.46451, 126.95424)), cafeteriaPins(food))
    }

    @Test
    fun aCafeteriaServingSeveralMealsIsPinnedOnce() {
        val lunch = food.offers.single()
        val offers = listOf(lunch, lunch.copy(meal = "DN", price = 7000))
        assertEquals(1, cafeteriaPins(food.copy(offers = offers)).size)
    }

    @Test
    fun offersWithoutALocationAreLeftOut() {
        val offers = listOf(
            Offer("301동식당>교직원전용식당", "LU", 6000, null, null, null),
            Offer("학생회관식당", "LU", 5000, 37.45932, 126.95058, null)
        )
        assertEquals(listOf("학생회관식당"), cafeteriaPins(food.copy(offers = offers)).map { it.name })
        assertEquals(emptyList<CafeteriaPin>(), cafeteriaPins(food.copy(offers = offers.take(1))))
    }

    @Test
    fun theBoundsPaddingLeavesRoomForThePinsOnTheShortSide() {
        // The 200dp map on an mdpi phone, and on an xxhdpi phone.
        assertEquals(40, boundsPadding(width = 360, height = 200))
        assertEquals(105, boundsPadding(width = 1080, height = 525))
    }
}
