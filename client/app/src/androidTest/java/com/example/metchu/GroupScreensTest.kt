package com.example.metchu

import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertHasClickAction
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.getBoundsInRoot
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.height
import androidx.compose.ui.unit.width
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.metchu.ui.group.GroupResultScreen
import com.example.metchu.ui.group.LobbyScreen
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class GroupScreensTest {
    @get:Rule
    val compose = createComposeRule()

    private companion object {
        init {
            val assets = InstrumentationRegistry.getInstrumentation().context.assets
            Fixtures.read = { path -> assets.open(path).bufferedReader().use { it.readText() } }
        }
    }

    @Test
    fun aLongRestaurantNameLeavesRoomForTheOtherChip() {
        val done = Fixtures.room("room_done").copy(decided = null)
        val picks = done.picks!!
        val long = done.copy(picks = listOf(picks[0].copy(restaurant = "샤로수길 아주 긴 이름의 이탈리안 레스토랑 서울대입구역 본점"), picks[1]))
        compose.setContent { GroupResultScreen(long, busy = false, onVote = { _, _ -> }, onDecide = {}, onAnother = {}, onHome = {}) }

        val screen = compose.onRoot().getBoundsInRoot()
        val first = compose.onNodeWithTag("pick_0").assertIsDisplayed().getBoundsInRoot()
        val second = compose.onNodeWithTag("pick_1").assertIsDisplayed().getBoundsInRoot()
        assertTrue(first.right < second.left)
        assertTrue(second.right <= screen.right)
        assertTrue(second.right - second.left >= 60.dp)
    }

    @Test
    fun theAgreeButtonStaysClearOfTheDistanceAndTakes48dpTaps() {
        // A one-letter name leaves the distance as the widest line under it.
        val done = Fixtures.room("room_done").copy(decided = null)
        val short = done.copy(picks = listOf(done.picks!![0].copy(restaurant = "곰"), done.picks!![1]))
        compose.setContent { GroupResultScreen(short, busy = false, onVote = { _, _ -> }, onDecide = {}, onAnother = {}, onHome = {}) }

        val distance = compose.onNodeWithTag("distance").assertIsDisplayed().getBoundsInRoot()
        for (tag in listOf("agree", "agree_count")) {
            val node = compose.onNodeWithTag(tag).assertIsDisplayed().getBoundsInRoot()
            assertTrue(tag, node.left >= distance.right || node.top >= distance.bottom || node.bottom <= distance.top)
        }
        val agree = compose.onNodeWithTag("agree").getBoundsInRoot()
        assertTrue(agree.width >= 48.dp && agree.height >= 48.dp)
    }

    @Test
    fun directionsFollowTheDistanceAndStayClearOfTheAgreeButton() {
        val done = Fixtures.room("room_done").copy(decided = null)
        compose.setContent { GroupResultScreen(done, busy = false, onVote = { _, _ -> }, onDecide = {}, onAnother = {}, onHome = {}) }

        val distance = compose.onNodeWithTag("distance").getBoundsInRoot()
        val directions = compose.onNodeWithTag("directionsButton").assertIsDisplayed().assertHasClickAction().getBoundsInRoot()
        val agree = compose.onNodeWithTag("agree").getBoundsInRoot()
        assertTrue(directions.left >= distance.right)
        assertTrue(directions.right <= agree.left)
    }

    @Test
    fun thePopularTagGrowsWithTheFontSize() {
        val done = Fixtures.room("room_done").copy(decided = null)
        compose.setContent {
            CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, fontScale = 1.3f)) {
                GroupResultScreen(done, busy = false, onVote = { _, _ -> }, onDecide = {}, onAnother = {}, onHome = {})
            }
        }
        // 18 sp of line height at 1.3x is about 23 dp; a fixed 18 dp would cut it.
        assertTrue(compose.onNodeWithTag("popular_1").assertIsDisplayed().getBoundsInRoot().height > 18.dp)
    }

    @Test
    fun theDecisionOpensWhereToMeetWithEveryonesDishMineFirst() {
        val done = Fixtures.room("room_done")
        compose.setContent { GroupResultScreen(done, busy = false, onVote = { _, _ -> }, onDecide = {}, onAnother = {}, onHome = {}) }

        compose.onNodeWithTag("decidedDialog").assertIsDisplayed()
        compose.onNodeWithTag("decidedRestaurant").assertTextEquals(done.picks!![done.decided!!].restaurant.replace('>', ' '))
        compose.onNodeWithTag("decidedDistance").assertIsDisplayed()
        compose.onNodeWithTag("decidedDirections").assertHasClickAction()
        val others = done.members.map { it.id }.filter { it != done.me }
        val mine = compose.onNodeWithTag("decidedDish_${done.me}").assertIsDisplayed().getBoundsInRoot()
        others.forEach { id -> assertTrue(compose.onNodeWithTag("decidedDish_$id").assertIsDisplayed().getBoundsInRoot().top >= mine.bottom) }
    }

    @Test
    fun okClosesWhereToMeetAndTheMeetPillOpensItAgain() {
        val done = Fixtures.room("room_done")
        compose.setContent { GroupResultScreen(done, busy = false, onVote = { _, _ -> }, onDecide = {}, onAnother = {}, onHome = {}) }

        compose.onNodeWithTag("decidedOk").performClick()
        compose.onNodeWithTag("decidedDialog").assertDoesNotExist()
        compose.onNodeWithTag("decided").assertHasClickAction().performClick()
        compose.onNodeWithTag("decidedDialog").assertIsDisplayed()
    }

    @Test
    fun startOverInWhereToMeetLeavesTheRoom() {
        var left = 0
        compose.setContent { GroupResultScreen(Fixtures.room("room_done"), busy = false, onVote = { _, _ -> }, onDecide = {}, onAnother = {}, onHome = { left++ }) }

        compose.onNodeWithTag("decidedHome").performClick()
        assertEquals(1, left)
        compose.onNodeWithTag("decidedDialog").assertDoesNotExist()
    }

    @Test
    fun noDialogBeforeTheHostDecides() {
        compose.setContent { GroupResultScreen(Fixtures.room("room_done").copy(decided = null), busy = false, onVote = { _, _ -> }, onDecide = {}, onAnother = {}, onHome = {}) }
        compose.onNodeWithTag("decidedDialog").assertDoesNotExist()
    }

    @Test
    fun startingTheRoomSpinsInTheOrangeButton() {
        val host = Fixtures.room("room_lobby").copy(me = 0)
        compose.setContent { LobbyScreen(host, busy = true, onStart = {}, onLeave = {}) }
        compose.onNodeWithTag("startRoom").assertIsNotEnabled()
        compose.onNode(hasTestTag("loading") and hasAnyAncestor(hasTestTag("startRoom")), useUnmergedTree = true).assertIsDisplayed()
        val loading = InstrumentationRegistry.getInstrumentation().targetContext.getString(R.string.loading)
        compose.onNodeWithTag("startRoom").assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, loading))
    }
}
