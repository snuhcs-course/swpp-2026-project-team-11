package com.example.metchu

import android.Manifest
import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.getBoundsInRoot
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.metchu.data.location.LocationSource
import com.example.metchu.data.model.Allergen
import com.example.metchu.data.model.Reason
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.network.UserLocation
import com.example.metchu.data.repository.AllergyStore
import com.example.metchu.data.repository.AppContainer
import com.example.metchu.data.repository.RecommendRepository
import com.example.metchu.data.repository.SettingsStore
import com.example.metchu.data.repository.Setup
import com.example.metchu.ui.main.MainActivity
import com.example.metchu.ui.start.Meal
import kotlinx.coroutines.CompletableDeferred
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import androidx.compose.ui.test.swipeUp
import androidx.compose.ui.test.performTouchInput
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertSame
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.IOException

/**
 * The real screens against a fake server: what each tap sends, which screen each
 * step draws, and what the user sees when a request fails.
 */
@RunWith(AndroidJUnit4::class)
class MainActivityTest {

    @get:Rule
    val compose = createEmptyComposeRule()

    private val api = FakeApi()
    private var location: UserLocation? = null
    private lateinit var scenario: ActivityScenario<MainActivity>
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    private val question = Fixtures.state("question")
    private val guess = Fixtures.state("guess_food")
    private val groupGuess = Fixtures.state("guess_group")
    private val unavailable = Fixtures.state("unavailable_empty")

    /** Past the first launch, with no allergies and the decision tree, unless a test says otherwise. */
    @Before
    fun setUp() {
        AppContainer.repository = RecommendRepository(api)
        AppContainer.locationSource = LocationSource { location }
        // The start screen asks for location; a system dialog would cover the screen.
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        for (permission in listOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)) {
            instrumentation.uiAutomation.grantRuntimePermission(context.packageName, permission)
        }
        clearPrefs()
        SettingsStore(context).setup = Setup.DONE
        scenario = ActivityScenario.launch(MainActivity::class.java)
    }

    @After
    fun tearDown() = scenario.close()

    private fun clearPrefs() {
        for (file in listOf("profile", "settings")) {
            context.getSharedPreferences(file, Context.MODE_PRIVATE).edit().clear().commit()
        }
    }

    private fun relaunch() {
        scenario.close()
        scenario = ActivityScenario.launch(MainActivity::class.java)
    }

    private fun text(@StringRes id: Int) = context.getString(id)

    private fun tap(tag: String) = compose.onNodeWithTag(tag).performClick()

    /** A picked answer is held a moment before it is sent; that wait is not one Compose tracks. */
    private fun answer(id: String) {
        val sent = api.calls.size
        tap("answer_$id")
        compose.waitUntil(3_000) { api.calls.size > sent }
        compose.waitForIdle()
    }

    private fun tapText(@StringRes id: Int) = compose.onNodeWithText(text(id)).performClick()

    private fun pickMeal(@StringRes meal: Int) {
        tap("mealToken")
        compose.onNodeWithText(text(meal)).performClick()
    }

    /** Starts a session whose first reply is [state], then forgets the create call. */
    private fun startWith(state: SessionState) {
        api.reply(state)
        tap("start")
        compose.waitForIdle()
        api.calls.clear()
    }

    private companion object {
        init {
            val assets = InstrumentationRegistry.getInstrumentation().context.assets
            Fixtures.read = { path -> assets.open(path).bufferedReader().use { it.readText() } }
        }
    }

    // --- start ---

    @Test
    fun startSendsTheMealPickedInTheSentence() {
        for ((meal, code) in listOf(R.string.meal_breakfast to "BR", R.string.meal_lunch to "LU", R.string.meal_dinner to "DN")) {
            pickMeal(meal)
            api.reply(question)
            tap("start")
            assertEquals("create $code decision_tree en", api.calls.last())
            tap("back")
        }
    }

    @Test
    fun theMealPickedStaysAfterASession() {
        val other = Meal.entries.first { it != Meal.now() }
        pickMeal(other.label)
        api.reply(question)
        tap("start")
        tap("back")
        api.reply(question)
        tap("start")
        assertEquals("create ${other.code} decision_tree en", api.calls.last())
    }

    @Test
    fun theFirstLaunchAsksTheLanguageThenTheAllergiesThenPointsToTheSettings() {
        clearPrefs()
        relaunch()
        // The locale switch arrives a moment later, which Compose does not wait for.
        tap("language_en")
        compose.waitUntil(5_000) { compose.onAllNodesWithTag("setupNext").fetchSemanticsNodes().isNotEmpty() }
        tap("allergen_${Allergen.EGG.id}")
        tap("allergen_${Allergen.PINE_NUT.id}")
        tap("setupNext")
        compose.onNodeWithTag("setupTip").assertIsDisplayed()
        tap("setupTipDone")
        compose.onNodeWithTag("start").assertIsDisplayed()

        pickMeal(R.string.meal_lunch)
        api.reply(question)
        tap("start")
        assertEquals("create LU decision_tree egg,pine_nut en", api.calls.last())

        // Done, so the next launch goes straight to the start screen.
        relaunch()
        compose.onNodeWithTag("start").assertIsDisplayed()
        compose.onNodeWithTag("setupTip").assertDoesNotExist()
    }

    @Test
    fun pickingAnAllergyMovesNoChip() {
        tap("settings")
        val chips = Allergen.entries.map { "allergen_${it.id}" }
        fun bounds() = chips.map { compose.onNodeWithTag(it).getBoundsInRoot() }
        val before = bounds()
        tap("allergen_${Allergen.EGG.id}")
        tap("allergen_${Allergen.SOYBEAN.id}")
        assertEquals(before, bounds())
    }

    @Test
    fun startSendsWhereTheUserIsWithTheAllergies() {
        AllergyStore(context).allergies = listOf(Allergen.MILK)
        relaunch()
        location = UserLocation(37.45932, 126.95058)
        pickMeal(R.string.meal_lunch)
        api.reply(question)
        tap("start")
        assertEquals("create LU decision_tree @37.45932,126.95058 milk en", api.calls.last())
    }

    @Test
    fun theEngineChosenInTheSettingsRunsTheSession() {
        tap("settings")
        compose.onNodeWithTag("engine_llm").performScrollTo().performClick()
        tap("back")
        pickMeal(R.string.meal_lunch)
        api.reply(Fixtures.state("question_llm"))
        tap("start")
        assertEquals("create LU llm en", api.calls.last())
    }

    /** The language is the app's, not the test's: it is switched back the same way before the test ends. */
    @Test
    fun theLanguagePickedOnTheStartScreenRunsTheSession() {
        pickLanguage("Language", "한국어", "언어")
        api.reply(question)
        tap("start")
        assertEquals("ko", api.calls.last().substringAfterLast(" "))
        tap("back")
        pickLanguage("언어", "English", "Language")
    }

    /**
     * The words fade out before the locale changes, which Compose does not wait for. The
     * activity redraws in the new language instead of being recreated, which flashes black.
     */
    private fun pickLanguage(button: String, language: String, buttonAfter: String) {
        var before: MainActivity? = null
        scenario.onActivity { before = it }
        compose.onNodeWithContentDescription(button).performClick()
        compose.onNodeWithText(language).performClick()
        compose.waitUntil(5_000) {
            compose.onAllNodes(hasContentDescription(buttonAfter)).fetchSemanticsNodes().isNotEmpty()
        }
        scenario.onActivity { assertSame(before, it) }
    }

    @Test
    fun rlSelectionSurvivesRelaunchAndStartsAnRlSession() {
        tap("settings")
        compose.onNodeWithTag("engine_rl").performScrollTo().performClick()
        tap("back")
        relaunch()
        pickMeal(R.string.meal_lunch)
        api.reply(Fixtures.state("question_rl"))
        tap("start")
        assertEquals("create LU rl en", api.calls.last())
        compose.onNodeWithText(Fixtures.state("question_rl").step.text).assertIsDisplayed()
    }

    @Test
    fun aSlowStartShowsASpinnerInTheButton() {
        val gate = api.hold()
        tap("start")
        compose.waitUntil(3_000) { compose.onAllNodesWithTag("loading").fetchSemanticsNodes().isNotEmpty() }
        gate.complete(question)
        compose.onNodeWithTag("question").assertIsDisplayed()
        compose.onNodeWithTag("loading").assertDoesNotExist()
    }

    @Test
    fun anUnavailableEngineSaysSoOnTheStartScreen() {
        api.fail(Fixtures.httpError(503, Fixtures.json("error_engine_unavailable")))
        tap("start")
        compose.onNodeWithText(text(R.string.error_engine_unavailable)).assertIsDisplayed()
        compose.onNodeWithTag("start").assertIsDisplayed()
        compose.onNodeWithText(text(R.string.retry)).assertDoesNotExist()
    }

    // --- question ---

    @Test
    fun eachCircleSendsItsOwnAnswerId() {
        for (id in listOf("no", "probably_no", "any", "probably_yes", "yes", "unknown")) {
            startWith(question)
            api.reply(question)
            answer(id)
            assertEquals(listOf("answer ${question.sessionId} ${question.step.questionId} $id"), api.calls.toList())
            tap("back")
        }
    }

    @Test
    fun aSlowAnswerShowsASpinnerUnderTheBar() {
        startWith(question)
        val gate = api.hold()
        answer("yes")
        compose.waitUntil(3_000) { compose.onAllNodesWithTag("loading").fetchSemanticsNodes().isNotEmpty() }
        gate.complete(guess)
        compose.onNodeWithTag("dish").assertIsDisplayed()
    }

    @Test
    fun theQuestionTextComesFromTheServer() {
        startWith(question)
        compose.onNodeWithTag("question").assertIsDisplayed()
        compose.onNodeWithText(question.step.text).assertIsDisplayed()
        // First question: there is nothing to recommend from yet, and Back leaves the session instead of undoing.
        compose.onNodeWithTag("recommendNow").assertDoesNotExist()
        tap("back")
        compose.onNodeWithTag("start").assertIsDisplayed()
        assertEquals(emptyList<String>(), api.calls.toList())
    }

    @Test
    fun startOverLeavesAQuestion() {
        startWith(question.copy(canUndo = true, step = question.step.copy(questionCount = 1)))
        tap("home")
        compose.onNodeWithTag("start").assertIsDisplayed()
        assertEquals(emptyList<String>(), api.calls.toList())
    }

    @Test
    fun theNextQuestionTakesAnAnswerWhenTheReplyComesWithinAFrame() {
        startWith(question)
        val next = question.copy(
            canUndo = true,
            step = question.step.copy(questionId = "q:next", questionCount = 1, text = "Do you feel like noodles?")
        )
        // The fake server replies at once, so loading never shows as true to the screen.
        api.reply(next)
        answer("yes")
        api.reply(next.copy(step = next.step.copy(questionId = "q:third", questionCount = 2)))
        answer("yes")
        assertEquals("answer ${question.sessionId} q:next yes", api.calls.last())
    }

    @Test
    fun anAnsweredQuestionStaysAboveAndCanBeRevisited() {
        startWith(question)
        val next = question.copy(
            canUndo = true,
            step = question.step.copy(questionId = "q:next", questionCount = 1, text = "Do you feel like noodles?")
        )
        api.reply(next)
        answer("yes")
        compose.onNodeWithText("Do you feel like noodles?").assertIsDisplayed()
        compose.onNodeWithText(question.step.text).assertIsDisplayed()

        api.reply(question)
        val sent = api.calls.size
        compose.onNodeWithText(question.step.text).performClick()
        // The row shows itself held for a moment before it goes back.
        compose.waitUntil(3_000) { api.calls.size > sent }
        assertEquals("undo ${question.sessionId}", api.calls.last())
    }

    @Test
    fun theDishsStepNeverShowsAsAQuestionWhileTheScreenFades() {
        startWith(question)
        api.reply(guess)
        val sent = api.calls.size
        tap("answer_yes")
        compose.waitUntil(3_000) { api.calls.size > sent }
        compose.mainClock.autoAdvance = false
        compose.mainClock.advanceTimeByFrame()
        compose.onAllNodes(hasText(guess.step.text)).assertCountEquals(0)
        compose.onNodeWithTag("question").assertTextEquals(question.step.text)
        compose.mainClock.autoAdvance = true
        compose.onNodeWithTag("dish").assertIsDisplayed()
    }

    @Test
    fun backAndRecommendNowSendTheirRequests() {
        startWith(question.copy(canUndo = true, step = question.step.copy(questionCount = 1)))
        api.reply(question)
        tap("back")
        assertEquals("undo ${question.sessionId}", api.calls.last())
        tap("back")

        startWith(question.copy(canUndo = true, step = question.step.copy(questionCount = 1)))
        api.reply(guess)
        tap("recommendNow")
        assertEquals("recommend-now ${question.sessionId}", api.calls.last())
        compose.onNodeWithTag("dish").assertIsDisplayed()
    }

    // --- result ---

    @Test
    fun aGuessShowsTheDishAndItsCafeteria() {
        startWith(guess)
        val food = guess.step.food!!
        compose.onNodeWithText(food.displayName).assertIsDisplayed()
        compose.onNodeWithText(food.offers.single().restaurant).assertIsDisplayed()
    }

    @Test
    fun aGuessShowsItsReasonWhenTheServerSendsOne() {
        api.reason = Reason(guess.step.food!!.foodId, "Spicy, as you wanted.")
        startWith(guess)
        compose.onNodeWithText("Spicy, as you wanted.").assertIsDisplayed()
    }

    @Test
    fun aReasonBeingWrittenHoldsItsPlace() {
        val held = CompletableDeferred<Reason>()
        api.heldReason = held
        startWith(guess)
        compose.onNodeWithTag("reasonWriting").assertIsDisplayed()
        held.complete(Reason(guess.step.food!!.foodId, "Spicy, as you wanted."))
        compose.onNodeWithText("Spicy, as you wanted.").assertIsDisplayed()
        compose.onNodeWithTag("reasonWriting").assertDoesNotExist()
    }

    @Test
    fun aFailedReasonLeavesNoPlaceholder() {
        startWith(guess)
        compose.onNodeWithTag("dish").assertIsDisplayed()
        compose.onNodeWithTag("reasonWriting").assertDoesNotExist()
    }

    @Test
    fun aGroupGuessNamesTheGroup() {
        startWith(groupGuess)
        compose.onNodeWithTag("dish").assertIsDisplayed()
        compose.onNodeWithText(groupGuess.step.group!!.displayName).assertIsDisplayed()
    }

    @Test
    fun theDishNameMovesTheSheetLikeItsHandle() {
        startWith(guess)
        val before = compose.onNodeWithTag("dish").getBoundsInRoot().top
        compose.onNodeWithTag("dish").performClick()
        compose.waitForIdle()
        assertNotEquals(before, compose.onNodeWithTag("dish").getBoundsInRoot().top)
    }

    @Test
    fun draggingTheHeaderUpRaisesTheSheet() {
        // One cafeteria, and still the sheet rises from half to full.
        startWith(guess)
        val before = compose.onNodeWithTag("dish").getBoundsInRoot().top
        compose.onNodeWithTag("dish").performTouchInput { swipeUp(startY = centerY, endY = centerY - 300f, durationMillis = 400) }
        compose.waitForIdle()
        assertTrue(compose.onNodeWithTag("dish").getBoundsInRoot().top < before)
    }

    @Test
    fun findAnotherTurnsTheDishDownAndBackUndoes() {
        startWith(guess)
        api.reply(question)
        tapText(R.string.result_more)
        assertEquals("feedback ${guess.sessionId} ${guess.step.guessId} false", api.calls.last())
        compose.onNodeWithTag("question").assertIsDisplayed()
        tap("back")

        startWith(guess)
        api.reply(question)
        tap("back")
        assertEquals("undo ${guess.sessionId}", api.calls.last())
    }

    @Test
    fun findAnotherStaysOnEveryDishAndTurnsDownTheCurrentOne() {
        startWith(guess)
        api.reply(question)
        tapText(R.string.result_more)
        api.reply(groupGuess)
        answer("yes")
        compose.onNodeWithText(text(R.string.result_more)).assertIsDisplayed()

        // The chips list the newest first; the second is the dish turned down.
        compose.onAllNodesWithTag("dishChip")[1].performClick()
        api.reply(question)
        tapText(R.string.result_more)
        assertEquals("feedback ${groupGuess.sessionId} ${groupGuess.step.guessId} false", api.calls.last())
    }

    @Test
    fun startOverLeavesTheResultAndResumeBringsItBack() {
        startWith(guess)
        tap("home")
        compose.onNodeWithTag("start").assertIsDisplayed()
        tap("resume")
        compose.onNodeWithTag("dish").assertIsDisplayed()
        assertEquals(emptyList<String>(), api.calls.toList())
    }

    @Test
    fun nothingToRecommendSaysWhy() {
        startWith(unavailable)
        compose.onNodeWithTag("unavailable").assertIsDisplayed()
        tap("back")
        compose.onNodeWithTag("start").assertIsDisplayed()
    }

    // --- errors ---

    @Test
    fun aFailedRequestShowsABannerAndTryAgainRepeatsIt() {
        startWith(question)
        api.fail(IOException("offline"))
        answer("no")
        compose.onNodeWithText(text(R.string.error_no_server)).assertIsDisplayed()
        compose.onNodeWithTag("question").assertIsDisplayed()

        api.reply(guess)
        tapText(R.string.retry)
        assertEquals(
            List(2) { "answer ${question.sessionId} ${question.step.questionId} no" },
            api.calls.toList()
        )
        compose.onNodeWithTag("errorBanner").assertDoesNotExist()
    }
}
