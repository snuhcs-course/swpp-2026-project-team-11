package com.example.metchu

import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.scrollTo
import androidx.test.espresso.assertion.ViewAssertions.doesNotExist
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.Visibility
import androidx.test.espresso.matcher.ViewMatchers.hasChildCount
import androidx.test.espresso.matcher.ViewMatchers.isChecked
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.isEnabled
import androidx.test.espresso.matcher.ViewMatchers.isNotEnabled
import androidx.test.espresso.matcher.ViewMatchers.isSelected
import androidx.test.espresso.matcher.ViewMatchers.withEffectiveVisibility
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.repository.AppContainer
import com.example.metchu.data.repository.RecommendRepository
import com.example.metchu.ui.main.MainActivity
import org.hamcrest.Matchers.allOf
import org.hamcrest.Matchers.not
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.IOException

/**
 * The real screen against a fake server: which panel is shown for each step, what
 * each tap sends, and what the user sees when a request fails.
 */
@RunWith(AndroidJUnit4::class)
class MainActivityTest {

    private val api = FakeApi()
    private lateinit var scenario: ActivityScenario<MainActivity>

    private val question = Fixtures.state("question")
    private val guess = Fixtures.state("guess_food")
    private val groupGuess = Fixtures.state("guess_group")
    private val recommendation = Fixtures.state("recommendation")
    private val unavailable = Fixtures.state("unavailable_empty")

    @Before
    fun setUp() {
        AppContainer.repository = RecommendRepository(api)
        scenario = ActivityScenario.launch(MainActivity::class.java)
    }

    @After
    fun tearDown() {
        scenario.close()
    }

    /** Starts a session whose first reply is [state], then forgets the create call. */
    private fun startWith(state: SessionState) {
        api.reply(state)
        onView(withId(R.id.btnStart)).perform(click())
        api.calls.clear()
    }

    private fun assertOnlyPanel(panel: Int) {
        val panels = listOf(
            R.id.panelStart, R.id.panelQuestion, R.id.panelGuess, R.id.panelResult, R.id.panelUnavailable
        )
        for (id in panels) {
            val expected = if (id == panel) Visibility.VISIBLE else Visibility.GONE
            onView(withId(id)).check(matches(withEffectiveVisibility(expected)))
        }
    }

    private fun assertGone(id: Int) =
        onView(withId(id)).check(matches(withEffectiveVisibility(Visibility.GONE)))

    private fun assertShown(id: Int) =
        onView(withId(id)).check(matches(withEffectiveVisibility(Visibility.VISIBLE)))

    private companion object {
        init {
            val assets = InstrumentationRegistry.getInstrumentation().context.assets
            Fixtures.read = { path -> assets.open(path).bufferedReader().use { it.readText() } }
        }
    }

    // --- start ---

    @Test
    fun startScreenIsShownFirstWithLunchSelected() {
        assertOnlyPanel(R.id.panelStart)
        onView(withId(R.id.btnMealLunch)).check(matches(isChecked()))
        assertGone(R.id.bottomBar)
        assertGone(R.id.btnQuit)
        assertGone(R.id.errorBanner)
        assertGone(R.id.tvContext)
        assertEquals(emptyList<String>(), api.calls.toList())
    }

    @Test
    fun startSendsTheSelectedMeal() {
        val meals = listOf(
            R.id.btnMealBreakfast to "BR", R.id.btnMealLunch to "LU",
            R.id.btnMealDinner to "DN", R.id.btnMealAny to "null"
        )
        for ((button, meal) in meals) {
            onView(withId(button)).perform(click())
            api.reply(question)
            onView(withId(R.id.btnStart)).perform(click())
            assertEquals("create $meal", api.calls.last())
            onView(withId(R.id.btnQuit)).perform(click())
        }
    }

    // --- question ---

    @Test
    fun questionShowsTextProgressAndEveryAnswerOption() {
        startWith(question)
        assertOnlyPanel(R.id.panelQuestion)
        onView(withId(R.id.tvQuestion)).check(matches(withText(question.step.text)))
        onView(withId(R.id.tvProgress)).check(matches(withText("Question 1 of up to 10")))
        onView(withId(R.id.tvContext)).check(matches(withText("2026-09-29 · Lunch · 193 dishes")))
        onView(withId(R.id.answers)).check(matches(hasChildCount(6)))
        for (option in question.step.options!!) {
            onView(withText(option.label)).check(matches(isDisplayed()))
        }
        assertShown(R.id.bottomBar)
        assertShown(R.id.btnRecommendNow)
        assertShown(R.id.btnQuit)
        // First question: there is nothing to go back to.
        onView(withId(R.id.btnUndo)).check(matches(isNotEnabled()))
    }

    @Test
    fun eachAnswerButtonSendsItsOwnAnswerId() {
        for (option in question.step.options!!) {
            startWith(question)
            api.reply(question)
            onView(withText(option.label)).perform(scrollTo(), click())
            assertEquals(
                listOf("answer ${question.sessionId} ${question.step.questionId} ${option.id}"),
                api.calls.toList()
            )
            onView(withId(R.id.btnQuit)).perform(click())
        }
    }

    @Test
    fun aNewQuestionReplacesTheOldAnswerButtons() {
        startWith(question)
        val next = question.copy(
            canUndo = true,
            step = question.step.copy(
                questionId = "q:next", questionCount = 1, text = "Do you feel like noodles?",
                options = question.step.options!!.take(2)
            )
        )
        api.reply(next)
        onView(withText("Yes, sounds good")).perform(click())
        onView(withId(R.id.tvQuestion)).check(matches(withText("Do you feel like noodles?")))
        onView(withId(R.id.tvProgress)).check(matches(withText("Question 2 of up to 10")))
        onView(withId(R.id.answers)).check(matches(hasChildCount(2)))
        onView(withId(R.id.btnUndo)).check(matches(isEnabled()))

        api.reply(guess)
        onView(withText("Probably yes")).perform(click())
        assertEquals("answer ${question.sessionId} q:next probably_yes", api.calls.last())
    }

    @Test
    fun withoutACapTheProgressBarIsHidden() {
        startWith(question.copy(maxQuestions = null))
        onView(withId(R.id.tvProgress)).check(matches(withText("Question 1")))
        assertGone(R.id.progressQuestions)
    }

    @Test
    fun backAndRecommendNowSendTheirRequests() {
        startWith(question.copy(canUndo = true))
        api.reply(guess)
        onView(withId(R.id.btnRecommendNow)).perform(click())
        api.reply(question)
        onView(withId(R.id.btnUndo)).perform(click())
        assertEquals(
            listOf("recommend-now ${question.sessionId}", "undo ${question.sessionId}"),
            api.calls.toList()
        )
        assertOnlyPanel(R.id.panelQuestion)
    }

    // --- guess ---

    @Test
    fun guessForOneDishShowsTheDishAndWhereToGetIt() {
        startWith(guess)
        val food = guess.step.food!!
        val offer = food.offers.single()
        assertOnlyPanel(R.id.panelGuess)
        onView(withId(R.id.tvGuessPrompt)).check(matches(withText(guess.step.text)))
        onView(withId(R.id.tvGuessKind)).check(matches(withText("Dish")))
        onView(withId(R.id.tvGuessName)).check(matches(withText(food.displayName)))
        onView(withId(R.id.tvGuessOffers)).check(
            matches(withText("${offer.restaurant} · Lunch · ${"%,d".format(offer.price)} won"))
        )
        assertGone(R.id.tvGuessExampleLabel)
        assertGone(R.id.tvGuessExample)
        assertGone(R.id.tvGuessMembers)
        onView(withId(R.id.btnAccept)).check(matches(withText("Yes, I'll have this")))
        // A guess is already a proposal.
        assertGone(R.id.btnRecommendNow)
        onView(withId(R.id.btnUndo)).check(matches(isEnabled()))
    }

    @Test
    fun guessForAGroupShowsTheGroupAnExampleAndOtherMembers() {
        startWith(groupGuess)
        val step = groupGuess.step
        val others = step.group!!.members.filter { it.foodId != step.food!!.foodId }
        onView(withId(R.id.tvGuessKind)).check(matches(withText("Kind of dish")))
        onView(withId(R.id.tvGuessName)).check(matches(withText("국수")))
        assertShown(R.id.tvGuessExampleLabel)
        onView(withId(R.id.tvGuessExample)).check(matches(withText("냉모밀")))
        onView(withId(R.id.tvGuessMembers)).check(
            matches(withText("Also on the menu: ${others.take(5).joinToString(", ") { it.displayName }} and 2 more"))
        )
        onView(withId(R.id.btnAccept)).check(matches(withText("Yes, I'll have this one")))
    }

    @Test
    fun aSmallGroupListsEveryOtherMemberWithoutACount() {
        val step = groupGuess.step
        val members = step.group!!.members.filter { it.foodId == step.food!!.foodId } +
            step.group!!.members.filter { it.foodId != step.food!!.foodId }.take(2)
        startWith(groupGuess.copy(step = step.copy(group = step.group!!.copy(members = members))))
        onView(withId(R.id.tvGuessMembers)).check(
            matches(withText("Also on the menu: ${members.drop(1).joinToString(", ") { it.displayName }}"))
        )
    }

    @Test
    fun aGroupWhoseOnlyRemainingMemberIsTheExampleHidesTheMemberLine() {
        val step = groupGuess.step
        val only = step.group!!.members.filter { it.foodId == step.food!!.foodId }
        startWith(groupGuess.copy(step = step.copy(group = step.group!!.copy(members = only))))
        assertGone(R.id.tvGuessMembers)
        assertShown(R.id.tvGuessExample)
    }

    @Test
    fun acceptAndRejectSendFeedbackForTheGuessOnScreen() {
        startWith(groupGuess)
        api.reply(guess)
        onView(withId(R.id.btnReject)).perform(scrollTo(), click())
        api.reply(recommendation)
        onView(withId(R.id.btnAccept)).perform(scrollTo(), click())
        assertEquals(
            listOf(
                "feedback ${groupGuess.sessionId} ${groupGuess.step.guessId} false",
                "feedback ${guess.sessionId} ${guess.step.guessId} true"
            ),
            api.calls.toList()
        )
        assertOnlyPanel(R.id.panelResult)
    }

    @Test
    fun aDishWithNoPriceOrSeveralCafeteriasIsListedLineByLine() {
        val food = guess.step.food!!
        val offers = listOf(
            food.offers.single().copy(restaurant = "학생회관식당", meal = "BR", price = null),
            food.offers.single().copy(restaurant = "301동식당", meal = "DN", price = 12500)
        )
        startWith(guess.copy(step = guess.step.copy(food = food.copy(offers = offers))))
        onView(withId(R.id.tvGuessOffers)).check(
            matches(withText("학생회관식당 · Breakfast · price not listed\n301동식당 · Dinner · 12,500 won"))
        )
    }

    // --- recommendation and unavailable ---

    @Test
    fun recommendationShowsTheDishAndEndsTheSession() {
        startWith(recommendation)
        val food = recommendation.step.food!!
        assertOnlyPanel(R.id.panelResult)
        onView(withId(R.id.tvResultPrompt)).check(matches(withText(recommendation.step.text)))
        onView(withId(R.id.tvResultName)).check(matches(withText(food.displayName)))
        assertGone(R.id.bottomBar)
        assertShown(R.id.btnStartOver)

        onView(withId(R.id.btnStartOver)).perform(scrollTo(), click())
        assertOnlyPanel(R.id.panelStart)
        assertGone(R.id.btnStartOver)
        assertEquals("Start over must not call the server", emptyList<String>(), api.calls.toList())
    }

    @Test
    fun fullMenuNameIsShownOnlyWhenItAddsSomething() {
        val food = recommendation.step.food!!
        startWith(recommendation.copy(step = recommendation.step.copy(
            food = food.copy(name = "닭갈비볶음밥&고구마맛탕", displayName = "닭갈비볶음밥"))))
        onView(withId(R.id.tvResultFullName)).check(matches(withText("닭갈비볶음밥&고구마맛탕")))
        onView(withId(R.id.btnQuit)).perform(click())

        startWith(recommendation.copy(step = recommendation.step.copy(
            food = food.copy(name = "육개장", displayName = "육개장"))))
        assertGone(R.id.tvResultFullName)
    }

    @Test
    fun emptyMenuExplainsWhichDayAndMealHadNothing() {
        startWith(unavailable)
        assertOnlyPanel(R.id.panelUnavailable)
        onView(withId(R.id.tvUnavailable)).check(
            matches(withText("There is no menu for 2026-01-01 (All day). Try another meal."))
        )
        onView(withId(R.id.tvContext)).check(matches(withText("2026-01-01 · All day · 0 dishes")))
        assertGone(R.id.bottomBar)
        assertShown(R.id.btnStartOver)
    }

    @Test
    fun exhaustedMenuHasItsOwnMessage() {
        startWith(unavailable.copy(
            candidateCount = 1, step = unavailable.step.copy(reason = "candidates_exhausted")))
        onView(withId(R.id.tvUnavailable)).check(
            matches(withText("You have turned down every dish on today's menu. Start over to see them again."))
        )
        onView(withId(R.id.tvContext)).check(matches(withText("2026-01-01 · All day · 1 dish")))
    }

    // --- loading and failures ---

    @Test
    fun whileARequestRunsTheScreenIgnoresTaps() {
        startWith(question.copy(canUndo = true))
        val gate = api.hold()
        onView(withText("No")).perform(click())
        assertShown(R.id.progressLoading)
        onView(withText("Yes, sounds good")).check(matches(isNotEnabled()))
        onView(withId(R.id.btnUndo)).check(matches(isNotEnabled()))
        onView(withId(R.id.btnRecommendNow)).check(matches(isNotEnabled()))
        assertEquals(1, api.calls.size)

        gate.complete(question)
        onView(withText("Yes, sounds good")).check(matches(isEnabled()))
        onView(withId(R.id.progressLoading)).check(matches(withEffectiveVisibility(Visibility.INVISIBLE)))
        // Back was only disabled for the request, but this reply says there is nothing to undo.
        onView(withId(R.id.btnUndo)).check(matches(isNotEnabled()))
    }

    @Test
    fun theTappedAnswerStaysHighlightedUntilItsRequestEnds() {
        startWith(question)
        onView(withText("Probably yes")).check(matches(not(isSelected())))
        val gate = api.hold()
        onView(withText("Probably yes")).perform(click())
        onView(withText("Probably yes")).check(matches(isSelected()))
        for (other in listOf("Yes, sounds good", "Doesn't matter", "Probably not", "No", "Not sure")) {
            onView(withText(other)).check(matches(allOf(not(isSelected()), isNotEnabled())))
        }
        onView(withId(R.id.btnRecommendNow)).check(matches(not(isSelected())))

        // The same question comes back: nothing may stay highlighted.
        gate.complete(question)
        onView(withText("Probably yes")).check(matches(allOf(not(isSelected()), isEnabled())))
    }

    @Test
    fun theTappedGuessButtonIsHighlightedAndReleasedOnFailure() {
        startWith(guess)
        val gate = api.hold()
        onView(withId(R.id.btnReject)).perform(scrollTo(), click())
        onView(withId(R.id.btnReject)).check(matches(isSelected()))
        onView(withId(R.id.btnAccept)).check(matches(allOf(not(isSelected()), isNotEnabled())))

        gate.completeExceptionally(IOException("timeout"))
        onView(withId(R.id.btnReject)).check(matches(allOf(not(isSelected()), isEnabled())))
        onView(withId(R.id.btnAccept)).check(matches(isEnabled()))
        assertShown(R.id.errorBanner)

        // Try again is highlighted in turn, and the first button is not.
        val retry = api.hold()
        onView(withId(R.id.btnRetry)).perform(click())
        onView(withId(R.id.btnRetry)).check(matches(isSelected()))
        onView(withId(R.id.btnReject)).check(matches(not(isSelected())))
        retry.complete(question)
        assertOnlyPanel(R.id.panelQuestion)
    }

    @Test
    fun aTapThatSendsNothingLeavesNoHighlightBehind() {
        startWith(question)
        onView(withId(R.id.btnQuit)).perform(click())
        val gate = api.hold()
        onView(withId(R.id.btnStart)).perform(click())
        onView(withId(R.id.btnStart)).check(matches(isSelected()))
        onView(withId(R.id.btnQuit)).check(matches(not(isSelected())))
        gate.complete(question)
        onView(withId(R.id.btnQuit)).perform(click())
        onView(withId(R.id.btnStart)).check(matches(allOf(not(isSelected()), isEnabled())))
    }

    @Test
    fun aFailedStartShowsTheBannerAndTryAgainStartsTheSession() {
        api.fail(IOException("Failed to connect"))
        onView(withId(R.id.btnMealDinner)).perform(click())
        onView(withId(R.id.btnStart)).perform(click())
        assertOnlyPanel(R.id.panelStart)
        onView(withId(R.id.tvError)).check(matches(allOf(isDisplayed(), withText(R.string.error_no_server))))

        api.reply(question)
        onView(withId(R.id.btnRetry)).perform(click())
        assertEquals(listOf("create DN", "create DN"), api.calls.toList())
        assertOnlyPanel(R.id.panelQuestion)
        assertGone(R.id.errorBanner)
    }

    @Test
    fun aFailedAnswerKeepsTheQuestionAndTryAgainResendsIt() {
        startWith(question)
        api.fail(IOException("timeout"))
        onView(withText("Probably not")).perform(click())
        assertOnlyPanel(R.id.panelQuestion)
        onView(withId(R.id.tvQuestion)).check(matches(withText(question.step.text)))
        assertShown(R.id.errorBanner)
        onView(withText("Probably not")).check(matches(isEnabled()))

        api.reply(guess)
        onView(withId(R.id.btnRetry)).perform(click())
        val call = "answer ${question.sessionId} ${question.step.questionId} probably_no"
        assertEquals(listOf(call, call), api.calls.toList())
        assertOnlyPanel(R.id.panelGuess)
        assertGone(R.id.errorBanner)
    }

    @Test
    fun aStaleReplyRedrawsFromTheServerWithoutABanner() {
        startWith(question)
        api.fail(Fixtures.httpError(409, Fixtures.json("error_stale_step")))
        onView(withText("No")).perform(click())
        assertOnlyPanel(R.id.panelGuess)
        assertGone(R.id.errorBanner)
    }

    @Test
    fun aLostSessionReturnsToStartWithAMessageAndNoRetry() {
        startWith(guess)
        api.fail(Fixtures.httpError(404, Fixtures.json("error_session_not_found")))
        onView(withId(R.id.btnAccept)).perform(scrollTo(), click())
        assertOnlyPanel(R.id.panelStart)
        onView(withId(R.id.tvError)).check(matches(withText(R.string.error_session_lost)))
        assertGone(R.id.btnRetry)
        assertGone(R.id.btnQuit)

        api.reply(question)
        onView(withId(R.id.btnStart)).perform(click())
        assertOnlyPanel(R.id.panelQuestion)
        assertGone(R.id.errorBanner)
    }

    @Test
    fun aServerErrorShowsItsOwnMessage() {
        startWith(question)
        api.fail(Fixtures.httpError(500, "<html>Server Error</html>"))
        onView(withId(R.id.btnRecommendNow)).perform(click())
        onView(withId(R.id.tvError)).check(matches(withText(R.string.error_server)))
        assertShown(R.id.btnRetry)
        assertOnlyPanel(R.id.panelQuestion)
    }

    @Test
    fun startOverFromTheHeaderDropsTheErrorAndTheSession() {
        startWith(question)
        api.fail(IOException("timeout"))
        onView(withText("No")).perform(click())
        onView(withId(R.id.btnQuit)).perform(click())
        assertOnlyPanel(R.id.panelStart)
        assertGone(R.id.errorBanner)
        onView(withText(question.step.text)).check(matches(not(isDisplayed())))
        assertEquals(1, api.calls.size)
    }

    // --- lifecycle ---

    @Test
    fun rotationKeepsTheSessionAndDoesNotCallTheServerAgain() {
        startWith(groupGuess)
        scenario.recreate()
        assertOnlyPanel(R.id.panelGuess)
        onView(withId(R.id.tvGuessName)).check(matches(withText("국수")))
        assertEquals(emptyList<String>(), api.calls.toList())

        api.reply(recommendation)
        onView(withId(R.id.btnAccept)).perform(scrollTo(), click())
        assertEquals("feedback ${groupGuess.sessionId} ${groupGuess.step.guessId} true", api.calls.last())
        scenario.recreate()
        assertOnlyPanel(R.id.panelResult)
    }

    @Test
    fun rotationKeepsTheErrorBanner() {
        api.fail(IOException("refused"))
        onView(withId(R.id.btnStart)).perform(click())
        scenario.recreate()
        onView(withId(R.id.tvError)).check(matches(allOf(isDisplayed(), withText(R.string.error_no_server))))
        api.reply(question)
        onView(withId(R.id.btnRetry)).perform(click())
        assertOnlyPanel(R.id.panelQuestion)
    }

    @Test
    fun noAnswerButtonsLeakIntoTheNextSession() {
        startWith(question)
        onView(withId(R.id.btnQuit)).perform(click())
        onView(withText("Yes, sounds good")).check(matches(not(isDisplayed())))
        startWith(guess)
        onView(withText(question.step.text)).check(matches(not(isDisplayed())))
        onView(withText("no such text")).check(doesNotExist())
    }
}
