package com.example.metchu

import android.Manifest
import android.content.Context
import androidx.annotation.StringRes
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.metchu.data.model.Allergen
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.repository.AllergyStore
import com.example.metchu.data.repository.AppContainer
import com.example.metchu.data.repository.RecommendRepository
import com.example.metchu.ui.main.MainActivity
import org.junit.After
import org.junit.Assert.assertEquals
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
        // The start screen asks for location; a system dialog would cover the screen.
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        for (permission in listOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)) {
            instrumentation.uiAutomation.grantRuntimePermission(context.packageName, permission)
        }
        clearPrefs()
        AllergyStore(context).allergies = emptyList()
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
            assertEquals("create $code decision_tree", api.calls.last())
            tap("back")
        }
    }

    @Test
    fun theFirstLaunchOpensTheSettingsAndEverySessionAvoidsTheAllergies() {
        clearPrefs()
        relaunch()
        tap("allergen_${Allergen.EGG.id}")
        tap("allergen_${Allergen.PINE_NUT.id}")
        tap("back")
        compose.onNodeWithTag("start").assertIsDisplayed()

        pickMeal(R.string.meal_lunch)
        api.reply(question)
        tap("start")
        assertEquals("create LU decision_tree egg,pine_nut", api.calls.last())

        // Chosen, so the next launch goes straight to the start screen.
        relaunch()
        compose.onNodeWithTag("start").assertIsDisplayed()
    }

    @Test
    fun theEngineChosenInTheSettingsRunsTheSession() {
        tap("settings")
        tap("engine_llm")
        tap("back")
        pickMeal(R.string.meal_lunch)
        api.reply(Fixtures.state("question_llm"))
        tap("start")
        assertEquals("create LU llm", api.calls.last())
    }

    @Test
    fun anUnavailableLlmEngineSaysSoOnTheStartScreen() {
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
            tap("answer_$id")
            assertEquals(listOf("answer ${question.sessionId} ${question.step.questionId} $id"), api.calls.toList())
            tap("back")
        }
    }

    @Test
    fun theQuestionTextComesFromTheServer() {
        startWith(question)
        compose.onNodeWithTag("question").assertIsDisplayed()
        compose.onNodeWithText(question.step.text).assertIsDisplayed()
        // First question: Back leaves the session instead of undoing.
        compose.onNodeWithTag("recommendNow").assertDoesNotExist()
        tap("back")
        compose.onNodeWithTag("start").assertIsDisplayed()
        assertEquals(emptyList<String>(), api.calls.toList())
    }

    @Test
    fun anAnsweredQuestionStaysAboveAndCanBeRevisited() {
        startWith(question)
        val next = question.copy(
            canUndo = true,
            step = question.step.copy(questionId = "q:next", questionCount = 1, text = "Do you feel like noodles?")
        )
        api.reply(next)
        tap("answer_yes")
        compose.onNodeWithText("Do you feel like noodles?").assertIsDisplayed()
        compose.onNodeWithText(question.step.text).assertIsDisplayed()

        api.reply(question)
        compose.onNodeWithText(question.step.text).performClick()
        compose.waitForIdle()
        assertEquals("undo ${question.sessionId}", api.calls.last())
    }

    @Test
    fun backAndRecommendNowSendTheirRequests() {
        startWith(question.copy(canUndo = true, step = question.step.copy(questionCount = 1)))
        api.reply(question)
        tap("back")
        assertEquals("undo ${question.sessionId}", api.calls.last())

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
    fun aGroupGuessNamesTheGroup() {
        startWith(groupGuess)
        compose.onNodeWithTag("dish").assertIsDisplayed()
        compose.onNodeWithText(groupGuess.step.group!!.displayName).assertIsDisplayed()
    }

    @Test
    fun findAnotherTurnsTheDishDownAndBackUndoes() {
        startWith(guess)
        api.reply(question)
        tapText(R.string.result_more)
        assertEquals("feedback ${guess.sessionId} ${guess.step.guessId} false", api.calls.last())
        compose.onNodeWithTag("question").assertIsDisplayed()

        startWith(guess)
        api.reply(question)
        tap("back")
        assertEquals("undo ${guess.sessionId}", api.calls.last())
    }

    @Test
    fun startOverLeavesTheResult() {
        startWith(guess)
        tapText(R.string.result_home)
        compose.onNodeWithTag("start").assertIsDisplayed()
        assertEquals(emptyList<String>(), api.calls.toList())
    }

    @Test
    fun nothingToRecommendSaysWhy() {
        startWith(unavailable)
        compose.onNodeWithTag("unavailable").assertIsDisplayed()
        tapText(R.string.result_home)
        compose.onNodeWithTag("start").assertIsDisplayed()
    }

    // --- errors ---

    @Test
    fun aFailedRequestShowsABannerAndTryAgainRepeatsIt() {
        startWith(question)
        api.fail(IOException("offline"))
        tap("answer_no")
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
