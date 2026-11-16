package com.example.metchu

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.getBoundsInRoot
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.metchu.ui.group.GroupResultScreen
import com.example.metchu.ui.group.LobbyScreen
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
        compose.setContent { GroupResultScreen(long, busy = false, onDecide = {}, onHome = {}) }

        val screen = compose.onRoot().getBoundsInRoot()
        val first = compose.onNodeWithTag("pick_0").assertIsDisplayed().getBoundsInRoot()
        val second = compose.onNodeWithTag("pick_1").assertIsDisplayed().getBoundsInRoot()
        assertTrue(first.right < second.left)
        assertTrue(second.right <= screen.right)
        assertTrue(second.right - second.left >= 60.dp)
    }

    @Test
    fun startingTheRoomSpinsInTheOrangeButton() {
        val host = Fixtures.room("room_lobby").copy(me = 0)
        compose.setContent { LobbyScreen(host, busy = true, onStart = {}, onLeave = {}) }
        compose.onNodeWithTag("startRoom").assertIsNotEnabled()
        compose.onNode(hasTestTag("loading") and hasAnyAncestor(hasTestTag("startRoom")), useUnmergedTree = true).assertIsDisplayed()
    }
}
