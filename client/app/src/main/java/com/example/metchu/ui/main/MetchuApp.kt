package com.example.metchu.ui.main

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.EnterExitState
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.livedata.observeAsState
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.example.metchu.BuildConfig
import com.example.metchu.R
import com.example.metchu.data.auth.GoogleTokenSource
import com.example.metchu.data.location.LocationSource
import com.example.metchu.data.model.RoomState
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.model.Step
import com.example.metchu.data.repository.AllergyStore
import com.example.metchu.data.repository.Place
import com.example.metchu.data.repository.Price
import com.example.metchu.data.repository.SettingsStore
import com.example.metchu.data.repository.Setup
import com.example.metchu.ui.account.AccountScreen
import com.example.metchu.ui.account.AccountViewModel
import com.example.metchu.ui.account.SavedList
import com.example.metchu.ui.account.SavedScreen
import com.example.metchu.ui.common.PillSegment
import com.example.metchu.ui.common.SheetEasing
import com.example.metchu.ui.common.fade
import com.example.metchu.ui.common.floating
import com.example.metchu.ui.common.setLanguage
import com.example.metchu.ui.group.GroupQuestionScreen
import com.example.metchu.ui.group.GroupResultScreen
import com.example.metchu.ui.group.GroupViewModel
import com.example.metchu.ui.group.JoinScreen
import com.example.metchu.ui.group.LeaveRoomDialog
import com.example.metchu.ui.group.LobbyScreen
import com.example.metchu.ui.group.NameDialog
import com.example.metchu.ui.question.QuestionScreen
import com.example.metchu.ui.result.ResultScreen
import com.example.metchu.ui.result.UnavailableScreen
import com.example.metchu.ui.settings.SettingsScreen
import com.example.metchu.ui.setup.AllergySetupScreen
import com.example.metchu.ui.setup.LanguageSetupScreen
import com.example.metchu.ui.start.Meal
import com.example.metchu.ui.start.StartScreen
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import kotlinx.coroutines.flow.first

/**
 * Which screen is up. Before a session: the first launch's steps, then start, settings, or
 * the account screen or the account's bookmarks or history opened from the settings. During one: the step's screen. In a group
 * room: the room's stage, ahead of everything else.
 */
private enum class Screen { LANGUAGE, ACCOUNT, ALLERGIES, START, SETTINGS, SAVED, QUESTION, RESULT, UNAVAILABLE, JOIN, LOBBY, GROUP_QUESTION, GROUP_RESULT }

/** The least time the start screen searches, so a quick first question does not cut it short. */
private const val SEARCH_MIN_MILLIS = 700

/** How long the start screen takes to whiten once the search is over. */
private const val SEARCH_WHITEN_MILLIS = 220

/** Where a session goes from the start screen. */
private val SessionScreens = setOf(Screen.QUESTION, Screen.RESULT, Screen.UNAVAILABLE)

private fun screenOf(session: SessionState?, room: RoomState?, setup: Setup, settingsOpen: Boolean, accountOpen: Boolean, savedOpen: Boolean, joinOpen: Boolean): Screen = when {
    room != null -> when (room.status) {
        RoomState.LOBBY -> Screen.LOBBY
        RoomState.ASKING -> Screen.GROUP_QUESTION
        else -> Screen.GROUP_RESULT
    }
    session == null && joinOpen -> Screen.JOIN
    else -> soloScreenOf(session, setup, settingsOpen, accountOpen, savedOpen)
}

private fun soloScreenOf(session: SessionState?, setup: Setup, settingsOpen: Boolean, accountOpen: Boolean, savedOpen: Boolean): Screen = when (session?.step?.type) {
    null -> when {
        setup == Setup.LANGUAGE -> Screen.LANGUAGE
        setup == Setup.ACCOUNT -> Screen.ACCOUNT
        setup == Setup.ALLERGIES -> Screen.ALLERGIES
        settingsOpen && accountOpen -> Screen.ACCOUNT
        settingsOpen && savedOpen -> Screen.SAVED
        settingsOpen -> Screen.SETTINGS
        else -> Screen.START
    }
    Step.QUESTION -> Screen.QUESTION
    Step.GUESS, Step.RECOMMENDATION -> Screen.RESULT
    else -> Screen.UNAVAILABLE
}

@Composable
fun MetchuApp(
    viewModel: RecommendViewModel,
    group: GroupViewModel,
    accounts: AccountViewModel,
    google: GoogleTokenSource,
    allergyStore: AllergyStore,
    settings: SettingsStore,
    location: LocationSource
) {
    val session by viewModel.session.observeAsState()
    val loading by viewModel.loading.observeAsState(false)
    val error by viewModel.error.observeAsState()
    val history by viewModel.history.observeAsState(emptyList())
    val shown by viewModel.shown.observeAsState(emptyList())
    val reasons by viewModel.reasons.observeAsState(emptyMap())
    val canResume by viewModel.canResume.observeAsState(false)
    val menus by viewModel.menus.observeAsState(emptyMap())
    val account by accounts.account.observeAsState()
    val accountBusy by accounts.busy.observeAsState(false)
    val accountError by accounts.error.observeAsState()
    val bookmarks by accounts.bookmarks.observeAsState()
    val accountHistory by accounts.history.observeAsState()
    val savedFailed by accounts.savedFailed.observeAsState(false)
    val room by group.room.observeAsState()
    val roomHistory by group.history.observeAsState(emptyList())
    val roomBusy by group.busy.observeAsState(false)
    val roomError by group.error.observeAsState()

    // Stored at once, so a launch picks up where the last one stopped.
    var setup by remember { mutableStateOf(settings.setup) }
    val advance = { next: Setup -> setup = next; settings.setup = next }
    var settingsOpen by rememberSaveable { mutableStateOf(false) }
    var accountOpen by rememberSaveable { mutableStateOf(false) }
    // The account's list opened from the settings; only while signed in.
    var savedList by rememberSaveable { mutableStateOf<SavedList?>(null) }
    LaunchedEffect(account == null) { if (account == null) savedList = null }
    // Google's account picker opens over the activity.
    val context = LocalContext.current
    val googleToken: suspend () -> String? = { google.idToken(context) }
    // Once per launch: kept here, so leaving the start screen does not bring the location notice back.
    var locationAsked by rememberSaveable { mutableStateOf(false) }
    var allergies by remember { mutableStateOf(allergyStore.allergies) }
    var engine by remember { mutableStateOf(settings.engine) }
    var place by remember { mutableStateOf(settings.place) }
    var price by remember { mutableStateOf(settings.price) }
    // Kept while the app runs, so coming back from a session keeps the meal the user picked.
    var meal by rememberSaveable { mutableStateOf(Meal.now()) }
    // The server writes its questions in the language the app is showing.
    val language = if (LocalConfiguration.current.locales[0].language == "ko") "ko" else "en"
    // "With friends" on the start screen, and the join screen opened from there.
    var together by rememberSaveable { mutableStateOf(false) }
    var joinOpen by rememberSaveable { mutableStateOf(false) }
    // A guest names themselves before creating a room; the name is offered again next time.
    var askName by rememberSaveable { mutableStateOf(false) }
    var guestName by rememberSaveable { mutableStateOf("") }
    // Nobody can come back into a room once its questions have started, so leaving one is confirmed.
    var confirmLeave by rememberSaveable { mutableStateOf(false) }
    val askToLeave = { if (room?.decided != null) group.leave() else confirmLeave = true }
    val distanceScope = if (place == Place.NEAR) "near" else "any"
    val createRoom = { name: String? ->
        group.create(account?.token, name, allergies, language, meal.code, { location.current() }, distanceScope, price.level)
    }
    LaunchedEffect(room != null) { if (room != null) joinOpen = false }

    // The start screen's search shows for a moment even when the first question comes back at
    // once, then whitens (the map does not fade with the screen) before the question fades in.
    // Both are timed as animations, so they run on the frame clock that UI tests drive.
    var searches by remember { mutableIntStateOf(0) }
    var holding by remember { mutableStateOf(false) }
    val searchTime = remember { Animatable(0f) }
    val whiten = remember { Animatable(0f) }
    LaunchedEffect(searches) {
        if (searches == 0) return@LaunchedEffect
        holding = true
        try {
            whiten.snapTo(0f)
            searchTime.snapTo(0f)
            searchTime.animateTo(1f, tween(SEARCH_MIN_MILLIS, easing = LinearEasing))
            snapshotFlow { session != null || !loading }.first { it }
            if (session != null) whiten.animateTo(1f, tween(SEARCH_WHITEN_MILLIS))
        } finally {
            holding = false
        }
    }
    val held = holding && session != null
    // Whitened only on the way out of a search; resuming a session leaves the usual way.
    val whitened = if (session != null) whiten.value else 0f
    LaunchedEffect(session == null) { if (session == null && !holding) whiten.snapTo(0f) }
    val screen = if (held) Screen.START else screenOf(session, room, setup, settingsOpen, accountOpen, savedList != null, joinOpen)
    val closeSettings = {
        allergyStore.allergies = allergies
        settingsOpen = false
        accounts.clearError()
    }
    val openAccount = { accounts.clearError(); accountOpen = true }
    val closeAccount = { accounts.clearError(); accountOpen = false }
    // Signed in on the account screen: go on to where the user was headed.
    LaunchedEffect(account != null) {
        if (account == null) return@LaunchedEffect
        if (setup == Setup.ACCOUNT) advance(Setup.ALLERGIES)
        if (accountOpen) closeAccount()
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
                    // The search has whitened the start screen: the question fades in over it.
                    initialState == Screen.START && targetState in SessionScreens && whitened == 1f ->
                        fadeIn(tween(320, easing = SheetEasing)) togetherWith ExitTransition.None
                    // Otherwise one screen fades out before the next fades in, so two never show through each other.
                    else -> fadeIn(tween(260, delayMillis = 160)) togetherWith fadeOut(tween(180))
                }
            },
            label = "screen"
        ) { target ->
            val current = session
            when (target) {
                Screen.LANGUAGE -> LanguageSetupScreen(onPick = { tag ->
                    advance(if (account == null) Setup.ACCOUNT else Setup.ALLERGIES)
                    setLanguage(tag)
                })
                Screen.ACCOUNT -> {
                    // On the first launch this is a setup step; otherwise it was opened from the settings.
                    val back = if (setup == Setup.ACCOUNT) ({ accounts.clearError(); advance(Setup.LANGUAGE) }) else closeAccount
                    BackHandler(onBack = back)
                    AccountScreen(
                        busy = accountBusy,
                        error = accountError,
                        onLogIn = accounts::logIn,
                        onSignUp = accounts::signUp,
                        onGoogle = { accounts.google(googleToken) }.takeIf { BuildConfig.HAS_GOOGLE_SIGN_IN },
                        onModeChange = accounts::clearError,
                        onBack = back,
                        onSkip = { accounts.clearError(); advance(Setup.ALLERGIES) }.takeIf { setup == Setup.ACCOUNT }
                    )
                }
                Screen.ALLERGIES -> {
                    // Signed in, there is no account step to go back to.
                    val back = { advance(if (account == null) Setup.ACCOUNT else Setup.LANGUAGE) }
                    BackHandler(onBack = back)
                    AllergySetupScreen(
                        allergies = allergies,
                        onAllergies = { allergies = it; allergyStore.allergies = it },
                        onBack = back,
                        onNext = { advance(Setup.TIP) }
                    )
                }
                Screen.START -> {
                    LaunchedEffect(meal, allergies, together) { if (!together) viewModel.prewarm(meal.code, allergies, source = "all") }
                    StartScreen(
                        meal = meal,
                        place = place,
                        // Still searching while it whitens for the question.
                        loading = loading || roomBusy || held || whitened > 0f,
                        whitened = whitened,
                        tip = setup == Setup.TIP,
                        askForLocation = !locationAsked,
                        onMeal = { meal = it },
                        onPlace = { place = it; settings.place = it },
                        price = price,
                        onPrice = { price = it; settings.price = it },
                        onSettings = { settingsOpen = true },
                        group = together,
                        onGroup = { together = it },
                        onJoin = { group.clearError(); joinOpen = true },
                        onResume = viewModel::resume.takeIf { canResume },
                        onTipDone = { advance(Setup.DONE) },
                        onLocationAsked = { locationAsked = true },
                        onStart = { meal ->
                            when {
                                !together -> {
                                    searches++
                                    viewModel.start(meal.code, engine, location, allergies, language, source = "all", distanceScope = distanceScope, priceLevel = price.level, token = account?.token)
                                }
                                account == null -> askName = true
                                else -> createRoom(null)
                            }
                        }
                    )
                }
                Screen.SETTINGS -> {
                    BackHandler(onBack = closeSettings)
                    SettingsScreen(
                        account = account,
                        accountBusy = accountBusy,
                        accountError = accountError,
                        allergies = allergies,
                        engine = engine,
                        onAccount = openAccount,
                        onLinkGoogle = { accounts.linkGoogle(googleToken) }.takeIf { BuildConfig.HAS_GOOGLE_SIGN_IN },
                        onLogOut = accounts::logOut,
                        onSaved = { list ->
                            savedList = list
                            if (list == SavedList.BOOKMARKS) accounts.loadBookmarks() else accounts.loadHistory()
                        },
                        onAllergies = { allergies = it; allergyStore.allergies = it },
                        onEngine = { engine = it; settings.engine = it },
                        onBack = closeSettings
                    )
                }
                Screen.SAVED -> savedList?.let { list ->
                    val back = { savedList = null }
                    BackHandler(onBack = back)
                    SavedScreen(
                        list = list,
                        bookmarks = bookmarks,
                        history = accountHistory,
                        failed = savedFailed,
                        onRetry = { if (list == SavedList.BOOKMARKS) accounts.loadBookmarks() else accounts.loadHistory() },
                        onBack = back
                    )
                }
                Screen.QUESTION -> if (current != null) {
                    BackHandler { if (current.canUndo) viewModel.undo() else viewModel.startOver() }
                    // Leaving for a result, this screen keeps the question just answered and the
                    // list as it was, so the dish's step never shows as a question while it fades.
                    val asked = current.takeIf { it.step.type == Step.QUESTION }
                    val kept = remember { Kept(current, history) }
                    if (asked != null) {
                        kept.session = asked
                        kept.history = history
                    }
                    QuestionScreen(
                        session = kept.session,
                        history = kept.history,
                        loading = loading || asked == null,
                        onAnswer = viewModel::answer,
                        onBack = { if (current.canUndo) viewModel.undo() else viewModel.startOver() },
                        onRecommendNow = viewModel::recommendNow,
                        onHome = viewModel::startOver,
                        onRevisit = viewModel::revisit
                    )
                }
                Screen.RESULT -> if (current != null) {
                    BackHandler { viewModel.undo() }
                    // The bookmark button shows once the account's bookmarks are known.
                    LaunchedEffect(account?.token) { if (account != null && bookmarks == null) accounts.loadBookmarks() }
                    ResultScreen(
                        session = current,
                        shown = shown,
                        reasons = reasons,
                        menus = menus,
                        place = place,
                        loading = loading,
                        onBack = viewModel::undo,
                        onHome = viewModel::startOver,
                        onMore = { viewModel.feedback(accepted = false) },
                        onMenu = viewModel::menu,
                        bookmarked = bookmarks?.takeIf { account != null }?.map { it.foodId }?.toSet(),
                        onBookmark = accounts::toggleBookmark
                    )
                }
                Screen.JOIN -> {
                    val back = { group.clearError(); joinOpen = false }
                    BackHandler(onBack = back)
                    JoinScreen(
                        guest = account == null,
                        busy = roomBusy,
                        onJoin = { code, name -> group.join(account?.token, code, name, allergies, language) },
                        onBack = back
                    )
                }
                Screen.LOBBY -> room?.let {
                    BackHandler(onBack = group::leave)
                    LobbyScreen(it, roomBusy, onStart = group::start, onLeave = group::leave)
                }
                Screen.GROUP_QUESTION -> room?.takeIf { it.question != null }?.let {
                    BackHandler(onBack = askToLeave)
                    GroupQuestionScreen(it, roomHistory, roomBusy, group::answer, group::recommendNow, askToLeave)
                }
                Screen.GROUP_RESULT -> room?.let {
                    BackHandler(onBack = askToLeave)
                    GroupResultScreen(it, roomBusy, onVote = group::vote, onDecide = group::decide, onAnother = group::another, onHome = askToLeave)
                }
                Screen.UNAVAILABLE -> if (current != null) {
                    BackHandler { viewModel.startOver() }
                    UnavailableScreen(current, hasAllergies = allergies.isNotEmpty(), priced = price != Price.ANY, onBack = viewModel::startOver)
                }
            }
        }

        ErrorBanner(roomError ?: error, onRetry = viewModel::retry, Modifier.align(Alignment.TopCenter))

        if (confirmLeave && room != null) {
            LeaveRoomDialog(
                onLeave = { confirmLeave = false; group.leave() },
                onStay = { confirmLeave = false }
            )
        }

        if (askName) {
            NameDialog(
                initial = guestName,
                onName = { guestName = it; askName = false; createRoom(it) },
                onDismiss = { askName = false }
            )
        }
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
        enter = slideInVertically(tween(200)) { -it / 4 },
        exit = slideOutVertically(tween(200)) { -it / 4 }
    ) {
        // Faded here rather than with fadeIn, whose layer would clip the banner's shadow.
        val alpha by transition.animateFloat({ tween(200) }, label = "banner") { if (it == EnterExitState.Visible) 1f else 0f }
        val shown = last ?: return@AnimatedVisibility
        val shape = RoundedCornerShape(16.dp)
        Row(
            Modifier
                .fillMaxWidth()
                .fade { alpha }
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

/** What the question screen last showed, held while it fades out. */
private class Kept(var session: SessionState, var history: List<AnsweredQuestion>)
