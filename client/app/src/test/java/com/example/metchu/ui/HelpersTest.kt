package com.example.metchu.ui

import com.example.metchu.Fixtures
import com.example.metchu.R
import com.example.metchu.data.model.Offer
import com.example.metchu.data.repository.Area
import com.example.metchu.ui.question.phaseText
import com.example.metchu.ui.question.progressFill
import com.example.metchu.ui.result.Point
import com.example.metchu.ui.result.cafeteriaList
import com.example.metchu.ui.result.directionsLinks
import com.example.metchu.ui.start.CampusCenter
import com.example.metchu.ui.start.Meal
import com.example.metchu.ui.start.center
import org.junit.Assert.assertEquals
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
    private val hall = Offer("220동식당", "LU", 5900, 37.46451, 126.95424)
    private val unlocated = Offer("기숙사식당", "LU", null, null, null)

    @Test
    fun cafeteriasKeepTheServersOrderAndAnUnlocatedOneHasNoPoint() {
        val list = cafeteriaList(food.copy(offers = listOf(unlocated, hall)))
        assertEquals(listOf(unlocated, hall), list.map { it.offer })
        assertEquals(listOf(null, Point(37.46451, 126.95424)), list.map { it.point })
    }

    @Test
    fun aCafeteriaServingSeveralMealsGetsALineForEach() {
        val dinner = hall.copy(meal = "DN", price = 6500)
        assertEquals(listOf(hall, dinner), cafeteriaList(food.copy(offers = listOf(hall, dinner, hall))).map { it.offer })
    }

    @Test
    fun aRestaurantSellingSeveralVariantsGetsALineForEach() {
        val variants = listOf(hall.copy(menuName = "치즈피자"), hall.copy(menuName = "페퍼로니피자", price = 7000))
        assertEquals(variants, cafeteriaList(food.copy(offers = variants)).map { it.offer })
    }
}

class AreaTest {

    @Test
    fun areaIdsAreTheServers() {
        assertEquals(listOf("campus", "snu_station", "nakseongdae", "all"), Area.entries.map { it.id })
    }

    @Test
    fun theStartMapCentersOnTheCampusOrTheStation() {
        assertEquals(CampusCenter, Area.CAMPUS.center())
        assertEquals(CampusCenter, Area.ALL.center())
        assertEquals(Point(37.481247, 126.952739), Area.SNU_STATION.center())
        assertEquals(Point(37.476930, 126.963693), Area.NAKSEONGDAE.center())
    }
}

class DirectionsTest {

    @Test
    fun naverMapIsTriedFirstThenKakaoMapThenTheWebWithOnlyTheDestination() {
        val links = directionsLinks("학생회관식당 2층", Point(37.4592, 126.9504), "com.example.metchu")
        val name = "%ED%95%99%EC%83%9D%ED%9A%8C%EA%B4%80%EC%8B%9D%EB%8B%B9%202%EC%B8%B5"
        assertEquals(
            listOf(
                "nmap://route/walk?dlat=37.4592&dlng=126.9504&dname=$name&appname=com.example.metchu",
                "kakaomap://route?ep=37.4592,126.9504&by=FOOT",
                "https://map.kakao.com/link/to/$name,37.4592,126.9504"
            ),
            links
        )
    }
}
