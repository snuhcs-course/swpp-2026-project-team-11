package com.example.metchu.ui.main

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.livedata.observeAsState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.example.metchu.R
import com.example.metchu.data.location.LocationSource
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.model.Step
import com.example.metchu.data.repository.AllergyStore
import com.example.metchu.data.repository.SettingsStore
import com.example.metchu.ui.common.PillSegment
import com.example.metchu.ui.common.SheetEasing
import com.example.metchu.ui.common.floating
import com.example.metchu.ui.question.QuestionScreen
import com.example.metchu.ui.result.ResultScreen
import com.example.metchu.ui.result.UnavailableScreen
import com.example.metchu.ui.settings.SettingsScreen
import com.example.metchu.ui.start.Meal
import com.example.metchu.ui.start.StartScreen
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType

/** Which screen is up. Before a session: start or settings. During one: the step's screen. */
private enum class Screen { START, SETTINGS, QUESTION, RESULT, UNAVAILABLE }

private fun screenOf(session: SessionState?, settingsOpen: Boolean): Screen = when (session?.step?.type) {
    null -> if (settingsOpen) Screen.SETTINGS else Screen.START
    Step.QUESTION -> Screen.QUESTION
    Step.GUESS, Step.RECOMMENDATION -> Screen.RESULT
    else -> Screen.UNAVAILABLE
}

@Composable
fun MetchuApp(viewModel: RecommendViewModel, allergyStore: AllergyStore, settings: SettingsStore, location: LocationSource) {
    val session by viewModel.session.observeAsState()
    val loading by viewModel.loading.observeAsState(false)
    val error by viewModel.error.observeAsState()
    val history by viewModel.history.observeAsState(emptyList())
    val shown by viewModel.shown.observeAsState(emptyList())
    val reasons by viewModel.reasons.observeAsState(emptyMap())
    val canResume by viewModel.canResume.observeAsState(false)

    // The first launch opens the settings, where the allergies are picked.
    var settingsOpen by rememberSaveable { mutableStateOf(!allergyStore.chosen) }
    var allergies by remember { mutableStateOf(allergyStore.allergies) }
    var engine by remember { mutableStateOf(settings.engine) }
    var place by remember { mutableStateOf(settings.place) }
    // Kept while the app runs, so coming back from a session keeps the meal the user picked.
    var meal by rememberSaveable { mutableStateOf(Meal.now()) }
    // The server writes its questions in the language the app is showing.
    val language = if (LocalConfiguration.current.locales[0].language == "ko") "ko" else "en"

    val screen = screenOf(session, settingsOpen)
    val closeSettings = {
        allergyStore.allergies = allergies
        settingsOpen = false
    }

    Box(Modifier.fillMaxSize().background(Color.White)) {
        AnimatedContent(
            targetState = screen,
            transitionSpec = {
                when {
                    // Question to result: the question leaves upward, then the result reveals itself.
                    initialState == Screen.QUESTION && targetState == Screen.RESULT ->
                        fadeIn(tween(160, delayMillis = 200)) togetherWith
                            (fadeOut(tween(200)) + slideOutVertically(tween(200)) { -it / 50 })
                    // Leaving a result: the map and sheet sink away first, then the next screen fades in.
                    initialState == Screen.RESULT ->
                        (fadeIn(tween(240, delayMillis = 180)) + slideInVertically(tween(300, delayMillis = 180, easing = SheetEasing)) { -it / 60 }) togetherWith
                            (fadeOut(tween(220)) + slideOutVertically(tween(260, easing = SheetEasing)) { it / 12 })
                    // Otherwise one screen fades out before the next fades in, so two never show through each other.
                    else -> fadeIn(tween(260, delayMillis = 160)) togetherWith fadeOut(tween(180))
                }
            },
            label = "screen"
        ) { target ->
            val current = session
            when (target) {
                Screen.START -> StartScreen(
                    meal = meal,
                    place = place,
                    loading = loading,
                    onMeal = { meal = it },
                    onPlace = { place = it; settings.place = it },
                    onSettings = { settingsOpen = true },
                    onResume = viewModel::resume.takeIf { canResume },
                    onStart = { meal -> viewModel.start(meal.code, engine, location, allergies, language) }
                )
                Screen.SETTINGS -> {
                    BackHandler(onBack = closeSettings)
                    SettingsScreen(
                        allergies = allergies,
                        engine = engine,
                        onAllergies = { allergies = it; allergyStore.allergies = it },
                        onEngine = { engine = it; settings.engine = it },
                        onBack = closeSettings
                    )
                }
                Screen.QUESTION -> if (current != null) {
                    BackHandler { if (current.canUndo) viewModel.undo() else viewModel.startOver() }
                    QuestionScreen(
                        session = current,
                        history = history,
                        loading = loading,
                        onAnswer = viewModel::answer,
                        onBack = { if (current.canUndo) viewModel.undo() else viewModel.startOver() },
                        onRecommendNow = viewModel::recommendNow,
                        onHome = viewModel::startOver,
                        onRevisit = viewModel::revisit
                    )
                }
                Screen.RESULT -> if (current != null) {
                    BackHandler { viewModel.undo() }
                    ResultScreen(
                        session = current,
                        shown = shown,
                        reasons = reasons,
                        place = place,
                        loading = loading,
                        onBack = viewModel::undo,
                        onHome = viewModel::startOver,
                        onMore = { viewModel.feedback(accepted = false) }
                    )
                }
                Screen.UNAVAILABLE -> if (current != null) {
                    BackHandler { viewModel.startOver() }
                    UnavailableScreen(current, hasAllergies = allergies.isNotEmpty(), onHome = viewModel::startOver)
                }
            }
        }

        ErrorBanner(error, onRetry = viewModel::retry, Modifier.align(Alignment.TopCenter))
    }
}

/** Stays until the next request: a toast would vanish before anyone read why. */
@Composable
private fun ErrorBanner(error: UiError?, onRetry: () -> Unit, modifier: Modifier = Modifier) {
    var last by remember { mutableStateOf(error) }
    if (error != null) last = error
    AnimatedVisibility(
        visible = error != null,
        modifier = modifier.statusBarsPadding().padding(start = 20.dp, end = 20.dp, top = 60.dp),
        enter = fadeIn(tween(200)) + slideInVertically(tween(200)) { -it / 4 },
        exit = fadeOut(tween(200)) + slideOutVertically(tween(200)) { -it / 4 }
    ) {
        val shown = last ?: return@AnimatedVisibility
        val shape = RoundedCornerShape(16.dp)
        Row(
            Modifier
                .fillMaxWidth()
                .floating(shape)
                .clip(shape)
                .background(Color.White)
                .padding(start = 18.dp, top = 6.dp, bottom = 6.dp)
                .testTag("errorBanner")
                .semantics { liveRegion = LiveRegionMode.Polite },
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(stringResource(shown.message), Modifier.weight(1f).padding(vertical = 8.dp), style = MetchuType.Label, color = MetchuColors.Grey900)
            if (shown.canRetry) {
                PillSegment(stringResource(R.string.retry), onRetry, color = MetchuColors.Primary, start = 14.dp)
            } else {
                Box(Modifier.padding(end = 18.dp))
            }
        }
    }
}
