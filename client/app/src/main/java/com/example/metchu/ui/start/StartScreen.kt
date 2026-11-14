package com.example.metchu.ui.start

import androidx.compose.foundation.layout.width
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.util.lerp
import com.google.android.gms.maps.CameraUpdateFactory
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.paneTitle
import androidx.compose.ui.semantics.semantics
import com.example.metchu.ui.common.TopRowHeight
import com.example.metchu.ui.common.fade
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.requiredWidth
import androidx.compose.foundation.selection.selectable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.unit.Dp
import com.example.metchu.ui.common.TopRow
import com.example.metchu.ui.common.floating
import com.example.metchu.ui.common.SheetEasing
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.metchu.BuildConfig
import com.example.metchu.R
import com.example.metchu.data.repository.Place
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.Languages
import com.example.metchu.ui.common.PickerOption
import com.example.metchu.ui.common.Spinner
import com.example.metchu.ui.common.cssShadow
import com.example.metchu.ui.common.setLanguage
import com.example.metchu.ui.common.pressScale
import com.example.metchu.ui.common.rememberLocationPermission
import com.example.metchu.ui.common.rememberSlow
import com.example.metchu.ui.common.rememberUserPoint
import com.example.metchu.ui.common.setLanguage
import com.example.metchu.ui.result.Point
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import com.example.metchu.ui.theme.screenBackground
import com.google.android.gms.maps.model.CameraPosition
import com.google.android.gms.maps.model.LatLng
import com.google.maps.android.compose.GoogleMap
import com.google.maps.android.compose.MapUiSettings
import com.google.maps.android.compose.rememberCameraPositionState

/** Where the start button's center sits above the bottom, level with the question screen's answer circles. */
val ActionCenterFromBottom = 202.dp

/** The SNU administration building (Building 60), shown until the user's position is known. */
val CampusCenter = Point(37.4600, 126.9520)

private enum class Sheet { MEAL, PLACE, WHO }

/**
 * "Today I'll have [lunch] [nearby] [for me]": the meal, the distance and whether friends
 * join ([group]) are picked inside the sentence, and the round button starts a session, or
 * with friends creates a room; "Join with a code" (top right) enters someone else's. The map behind the button fades in
 * from the background; the button stands where the user is. With [tip], a tip over the
 * screen points to the globe and the gear, where the language and the allergies change.
 * With [askForLocation] and no permission yet, a notice says why before the system asks,
 * once the tip is closed.
 *
 * [whitened] covers the whole screen in white as the search hands over to the question.
 *
 * While a session starts ([loading] alone, not with friends) the screen searches: the
 * sentence gives way to what is happening, the button shrinks into the user's dot with
 * ripples spreading from it, and the map fills the screen, zoomed out to the campus.
 */
@Composable
fun StartScreen(
    meal: Meal,
    place: Place,
    loading: Boolean,
    whitened: Float,
    tip: Boolean,
    askForLocation: Boolean,
    onMeal: (Meal) -> Unit,
    onPlace: (Place) -> Unit,
    onSettings: () -> Unit,
    group: Boolean,
    onGroup: (Boolean) -> Unit,
    onJoin: () -> Unit,
    onResume: (() -> Unit)?,
    onTipDone: () -> Unit,
    onLocationAsked: () -> Unit,
    onStart: (Meal) -> Unit
) {
    val nowMeal = remember { Meal.now() }
    var sheet by rememberSaveable { mutableStateOf<Sheet?>(null) }
    // What the picker shows; kept while it slides away so it does not switch to the other list.
    var shownSheet by rememberSaveable { mutableStateOf(Sheet.MEAL) }
    sheet?.let { shownSheet = it }
    val english = LocalConfiguration.current.locales[0].language != "ko"
    val scope = rememberCoroutineScope()

    val permission = rememberLocationPermission()
    val user = rememberUserPoint(permission.granted)
    val searching = loading && !group
    val search by animateFloatAsState(
        if (searching) 1f else 0f,
        tween(if (searching) 260 else 320, easing = SheetEasing),
        label = "search"
    )
    // Without a position there is nothing to find first.
    var phase by remember { mutableIntStateOf(0) }
    LaunchedEffect(searching) {
        if (!searching) return@LaunchedEffect
        phase = if (user != null) 0 else 1
        while (phase < SearchPhases.lastIndex) {
            delay(SEARCH_PHASE_MILLIS)
            phase++
        }
    }
    // The words fade out, change language and fade back in.
    var switching by remember { mutableStateOf(false) }
    val words by animateFloatAsState(if (switching) 0f else 1f, tween(150), label = "words")
    val language = LocalConfiguration.current.locales[0].language
    LaunchedEffect(language) { switching = false }

    Box(Modifier.fillMaxSize().screenBackground()) {
        if (BuildConfig.HAS_MAPS_KEY) StartMap(user ?: CampusCenter, search, zoomedOut = searching)

        Column(
            Modifier.statusBarsPadding().graphicsLayer {
                alpha = words * (1f - search)
                translationY = -12.dp.toPx() * search
            }
        ) {
            // Home tapped by mistake: the session left is one tap away.
            TopRow(arrangement = Arrangement.End) {
                if (group) TopPill(Icons.Keypad, stringResource(R.string.group_join_open), "joinRoom", onJoin)
                else if (onResume != null) TopPill(Icons.Resume, stringResource(R.string.resume), "resume", onResume)
            }
            Column(Modifier.padding(start = 20.dp, end = 20.dp, top = 10.dp)) {
                val title = MetchuType.Title
                Text(stringResource(R.string.start_line1), style = title)
                // Every line keeps the title's 39 dp, also the lines holding a choice.
                Row(Modifier.height(TitleLine), verticalAlignment = Alignment.CenterVertically) {
                    Token(stringResource(meal.label).let { if (english) it.uppercase() else it }, stringResource(R.string.start_meal_change), "mealToken") {
                        sheet = Sheet.MEAL
                    }
                    Text(stringResource(R.string.start_meal_particle), style = title)
                }
                Row(Modifier.height(TitleLine), verticalAlignment = Alignment.CenterVertically) {
                    Token(
                        stringResource(if (place == Place.NEAR) R.string.place_near else R.string.place_any).let { if (english) it.uppercase() else it },
                        stringResource(R.string.start_place_change), "placeToken"
                    ) { sheet = Sheet.PLACE }
                }
                Row(Modifier.height(TitleLine), verticalAlignment = Alignment.CenterVertically) {
                    Token(
                        stringResource(if (group) R.string.start_who_group else R.string.start_who_solo).let { if (english) it.uppercase() else it },
                        stringResource(R.string.start_who_change), "whoToken"
                    ) { sheet = Sheet.WHO }
                    Text(stringResource(R.string.start_line4), Modifier.padding(start = 8.dp), style = title)
                }
                Text(stringResource(if (group) R.string.start_sub_group else R.string.start_sub), Modifier.padding(top = 16.dp), style = MetchuType.Lead)
            }
        }

        SearchHeadline(
            phase.takeIf { searching },
            Modifier.statusBarsPadding().padding(start = 20.dp, end = 20.dp, top = TopRowHeight + 10.dp)
        )

        StartButton(
            label = stringResource(if (group) R.string.group_create else R.string.start_button),
            loading = loading,
            searching = searching,
            located = user != null,
            // Nothing else on screen asks for attention.
            nudging = !group && sheet == null && !tip,
            onClick = { onStart(meal) },
            modifier = Modifier.align(Alignment.BottomCenter).navigationBarsPadding()
                .padding(bottom = ActionCenterFromBottom - StartButtonSize / 2).fade { words }
        )
        // Things set once sit low on the left, out of the way of the sentence and the button.
        CircleIconButton(
            Icons.Gear, stringResource(R.string.settings), onSettings,
            Modifier.align(Alignment.BottomStart).navigationBarsPadding().padding(start = 74.dp, bottom = CornerButtonBottom)
                .fade { 1f - search }.testTag("settings")
        )
        LanguageMenu(Modifier.align(Alignment.BottomStart).navigationBarsPadding().padding(start = 20.dp, bottom = CornerButtonBottom).fade { 1f - search }) { tag ->
            scope.launch {
                switching = true
                delay(160)
                setLanguage(tag)
            }
        }

        // The faded choices stay out of reach until the search ends.
        if (searching) Box(Modifier.fillMaxSize().pointerInput(Unit) { detectTapGestures {} })

        // Under the choice it changes: the title, two lines and a 4 dp gap below the top row.
        ChoicePopup(
            visible = sheet != null,
            title = stringResource(when (shownSheet) {
                Sheet.MEAL -> R.string.start_meal_sheet
                Sheet.PLACE -> R.string.start_place_sheet
                Sheet.WHO -> R.string.start_who_sheet
            }),
            width = when (shownSheet) {
                Sheet.MEAL -> 168.dp
                Sheet.PLACE -> 248.dp
                Sheet.WHO -> 272.dp
            },
            modifier = Modifier.statusBarsPadding()
                .padding(start = 14.dp, top = TopRowHeight + 10.dp + TitleLine * (shownSheet.ordinal + 2) + 4.dp),
            options = if (shownSheet == Sheet.WHO) {
                listOf(false, true).map {
                    PickerOption(
                        stringResource(if (it) R.string.who_group_option else R.string.who_solo_option),
                        stringResource(if (it) R.string.who_group_note else R.string.who_solo_note),
                        selected = it == group
                    ) { onGroup(it); sheet = null }
                }
            } else if (shownSheet == Sheet.PLACE) {
                Place.entries.map {
                    PickerOption(
                        stringResource(if (it == Place.NEAR) R.string.place_near_option else R.string.place_any_option),
                        stringResource(if (it == Place.NEAR) R.string.place_near_note else R.string.place_any_note),
                        selected = it == place
                    ) { onPlace(it); sheet = null }
                }
            } else {
                Meal.entries.map {
                    PickerOption(
                        stringResource(it.label),
                        if (it == nowMeal) stringResource(R.string.meal_now) else null,
                        selected = it == meal
                    ) { onMeal(it); sheet = null }
                }
            },
            onDismiss = { sheet = null }
        )

        // Over everything, the map too: a map does not fade with the screen around it.
        if (whitened > 0f) Box(Modifier.fillMaxSize().fade { whitened }.background(Color.White))

        if (tip) SetupTip(onDone = onTipDone, onSettings = { onTipDone(); onSettings() })

        if (askForLocation && !permission.granted && !tip) {
            LocationNotice(
                onContinue = { onLocationAsked(); permission.request() },
                onLater = onLocationAsked
            )
        }
    }
}

/**
 * The screen dimmed but for copies of the globe and the gear, in the same place, and a
 * bubble above them. A tap anywhere, Back or "Got it" closes it; the gear also opens the settings.
 */
@Composable
private fun SetupTip(onDone: () -> Unit, onSettings: () -> Unit) {
    BackHandler(onBack = onDone)
    Box(
        Modifier.fillMaxSize().background(MetchuColors.Grey900.copy(alpha = 0.48f))
            .clickable(remember { MutableInteractionSource() }, indication = null, onClick = onDone)
            .testTag("setupTip")
    ) {
        Column(Modifier.align(Alignment.BottomStart).navigationBarsPadding().padding(start = 20.dp, bottom = CornerButtonBottom)) {
            Column(
                Modifier.widthIn(max = 280.dp).clip(RoundedCornerShape(16.dp)).background(Color.White)
                    .padding(start = 18.dp, end = 8.dp, top = 16.dp, bottom = 4.dp)
            ) {
                Text(stringResource(R.string.setup_tip_title), Modifier.padding(end = 10.dp), style = MetchuType.Label)
                Text(stringResource(R.string.setup_tip_body), Modifier.padding(top = 4.dp, end = 10.dp), style = MetchuType.Body)
                TextButton(onDone, Modifier.align(Alignment.End).testTag("setupTipDone")) {
                    Text(stringResource(R.string.setup_tip_done), style = MetchuType.Button, color = MetchuColors.Primary)
                }
            }
            // Over the gear's center: the globe, the gap and half the gear, less half the arrow.
            Canvas(Modifier.padding(start = 68.dp, bottom = 8.dp).size(16.dp, 8.dp)) {
                drawPath(Path().apply { moveTo(0f, 0f); lineTo(size.width, 0f); lineTo(size.width / 2, size.height); close() }, Color.White)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                CircleIconButton(Icons.Globe, stringResource(R.string.language), onDone)
                CircleIconButton(Icons.Gear, stringResource(R.string.settings), onSettings)
            }
        }
    }
}

@Composable
private fun LocationNotice(onContinue: () -> Unit, onLater: () -> Unit) {
    AlertDialog(
        onDismissRequest = onLater,
        confirmButton = {
            TextButton(onContinue, Modifier.testTag("locationContinue")) {
                Text(stringResource(R.string.location_ask_continue), style = MetchuType.Button, color = MetchuColors.Primary)
            }
        },
        dismissButton = {
            TextButton(onLater) {
                Text(stringResource(R.string.location_ask_later), style = MetchuType.Button, color = MetchuColors.Grey600)
            }
        },
        title = { Text(stringResource(R.string.location_ask_title), style = MetchuType.Item) },
        text = { Text(stringResource(R.string.location_ask_body), style = MetchuType.Body) },
        shape = RoundedCornerShape(20.dp),
        containerColor = Color.White
    )
}

/**
 * A small menu that grows from its top-left corner, under the word it changes, without
 * dimming the screen; it shrinks back and fades when a choice is picked or the user taps
 * elsewhere. Built like the language menu.
 */
@Composable
private fun ChoicePopup(visible: Boolean, title: String, options: List<PickerOption>, width: Dp, modifier: Modifier, onDismiss: () -> Unit) {
    val shown by animateFloatAsState(
        if (visible) 1f else 0f,
        if (visible) tween(220, easing = SheetEasing) else tween(160),
        label = "popup"
    )
    if (visible) {
        BackHandler(onBack = onDismiss)
        Box(Modifier.fillMaxSize().clickable(remember { MutableInteractionSource() }, null, onClick = onDismiss))
    }
    if (shown == 0f) return
    val shape = RoundedCornerShape(16.dp)
    Column(
        modifier
            .graphicsLayer {
                alpha = shown
                scaleX = 0.92f + 0.08f * shown
                scaleY = scaleX
                transformOrigin = TransformOrigin(0f, 0f)
                compositingStrategy = CompositingStrategy.ModulateAlpha
            }
            .width(width)
            .cssShadow(shape, 6.dp, 24.dp, 0.18f)
            .clip(shape)
            .background(Color.White)
            .padding(6.dp)
            .semantics { paneTitle = title }
    ) {
        options.forEach { option ->
            Row(
                Modifier
                    .fillMaxWidth()
                    .height(48.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .background(if (option.selected) MetchuColors.Grey100 else Color.White)
                    .selectable(option.selected, enabled = visible, role = Role.RadioButton, onClick = option.onPick)
                    .padding(horizontal = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                MenuRowContent(option.label, option.note, option.selected)
            }
        }
    }
}

/** A menu line: the label, bold with a check when it is the current one, otherwise its note on the right. */
@Composable
private fun MenuRowContent(label: String, note: String?, on: Boolean) {
    Text(label, style = if (on) MetchuType.Item.copy(fontSize = MetchuType.Button.fontSize) else MetchuType.Button, maxLines = 1)
    if (on) Image(Icons.Check, null, Modifier.size(20.dp), colorFilter = ColorFilter.tint(MetchuColors.Grey900))
    else if (note != null) Text(note, Modifier.padding(start = 12.dp), style = MetchuType.Caption, maxLines = 1)
}

private val StartButtonSize = 140.dp
/** The language and settings buttons stand this far above the navigation bar. */
private val CornerButtonBottom = 18.dp
private val TitleLine = 39.dp

/**
 * The round button. While [nudging] and idle, a soft circle keeps spreading from it.
 * [searching], it shrinks into the user's dot (ringed in white, with ripples) where it
 * stands, or away when the user's position is not [located]. Otherwise a slow [loading],
 * such as creating a room, shows a spinner inside it.
 */
@Composable
private fun StartButton(
    label: String,
    loading: Boolean,
    searching: Boolean,
    located: Boolean,
    nudging: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val interaction = remember { MutableInteractionSource() }
    val motion = tween<Dp>(420, easing = SheetEasing)
    val size by animateDpAsState(
        when {
            !searching -> StartButtonSize
            located -> DotSize
            else -> 0.dp
        },
        motion,
        label = "button"
    )
    val ring by animateDpAsState(if (searching) 1.5.dp else 0.dp, tween(300), label = "ring")
    val nudge by animateFloatAsState(if (nudging && !searching) 1f else 0f, tween(200), label = "nudge")
    val words by animateFloatAsState(if (searching) 0f else 1f, tween(120), label = "label")
    Box(modifier.size(StartButtonSize).then(if (searching) Modifier.testTag("loading") else Modifier), contentAlignment = Alignment.Center) {
        if (nudge > 0f) Nudge(Modifier.requiredSize(NudgeSize).fade { nudge })
        if (searching && located) Ripples(Modifier.requiredSize(RippleSize))
        Box(
            Modifier
                .size(size)
                .pressScale(interaction)
                .then(if (searching) Modifier.cssShadow(CircleShape, 2.dp, 8.dp, 0.3f) else Modifier.cssShadow(CircleShape, 6.dp, 20.dp, 0.2f))
                .clip(CircleShape)
                .background(MetchuColors.Primary)
                .border(ring, Color.White, CircleShape)
                .clickable(interaction, indication = null, enabled = !loading, role = Role.Button, onClick = onClick)
                .testTag("start"),
            contentAlignment = Alignment.Center
        ) {
            if (!searching && rememberSlow(loading)) Spinner(Color.White, 32.dp)
            else Text(
                label,
                Modifier.requiredWidth(StartButtonSize).fade { words },
                style = MetchuType.Button,
                color = Color.White,
                textAlign = TextAlign.Center
            )
        }
    }
}

/**
 * One circle that spreads from the button's edge and fades, then rests: it moves for the
 * first 60 % of each beat.
 */
@Composable
private fun Nudge(modifier: Modifier) {
    val beat by rememberInfiniteTransition(label = "nudge").animateFloat(
        0f, 1f, infiniteRepeatable(tween(NUDGE_MILLIS, easing = LinearEasing)), label = "beat"
    )
    Canvas(modifier) {
        val p = (beat / 0.6f).coerceAtMost(1f)
        val from = StartButtonSize.toPx() / 2
        val radius = from + (size.minDimension / 2 - from) * (1f - (1f - p) * (1f - p))
        drawCircle(MetchuColors.Primary.copy(alpha = 0.18f * (1f - p)), radius)
    }
}

/**
 * Three circles that keep spreading from the user's dot and fading, a third of a beat apart.
 * They come in once the button has mostly shrunk.
 */
@Composable
private fun Ripples(modifier: Modifier) {
    val beat by rememberInfiniteTransition(label = "ripples").animateFloat(
        0f, 1f, infiniteRepeatable(tween(RIPPLE_MILLIS, easing = LinearEasing)), label = "beat"
    )
    val shown = remember { Animatable(0f) }
    LaunchedEffect(Unit) { shown.animateTo(1f, tween(400, delayMillis = 250)) }
    Canvas(modifier.fade { shown.value }) {
        val from = DotSize.toPx() / 2
        val to = size.minDimension / 2
        repeat(3) { i ->
            val p = (beat + i / 3f) % 1f
            val radius = from + (to - from) * (1f - (1f - p) * (1f - p))
            val fade = 1f - p
            drawCircle(MetchuColors.Primary.copy(alpha = 0.14f * fade), radius)
        }
    }
}

/** Where the title stands, what the search is doing: [phase] indexes [SearchPhases], null shows nothing. */
@Composable
private fun SearchHeadline(phase: Int?, modifier: Modifier = Modifier) {
    AnimatedContent(
        targetState = phase,
        transitionSpec = {
            (fadeIn(tween(220, delayMillis = 120)) + slideInVertically(tween(320, delayMillis = 120, easing = SheetEasing)) { it / 4 }) togetherWith
                (fadeOut(tween(160)) + slideOutVertically(tween(200)) { -it / 4 })
        },
        modifier = modifier,
        label = "headline"
    ) { shown ->
        if (shown != null) Text(stringResource(SearchPhases[shown]), style = MetchuType.Title)
        else Box(Modifier.fillMaxWidth())
    }
}

private val SearchPhases = listOf(R.string.search_locating, R.string.search_menus, R.string.search_question)
private const val SEARCH_PHASE_MILLIS = 900L
private const val RIPPLE_MILLIS = 2100
private const val NUDGE_MILLIS = 2800
private val NudgeSize = 300.dp
private val DotSize = 22.dp
private val RippleSize = 380.dp

/** A white pill in the top row: "Resume" a session left, or "Join with a code". */
@Composable
private fun TopPill(icon: ImageVector, text: String, tag: String, onClick: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    Row(
        Modifier
            .height(44.dp)
            .pressScale(interaction, 0.95f)
            .floating()
            .clip(CircleShape)
            .background(Color.White)
            .clickable(interaction, indication = null, role = Role.Button, onClick = onClick)
            .padding(start = 12.dp, end = 16.dp)
            .testTag(tag),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        Image(icon, null, Modifier.size(20.dp), colorFilter = ColorFilter.tint(MetchuColors.Grey900))
        Text(text, style = MetchuType.Button.copy(fontSize = 15.sp))
    }
}

/** A choice inside the title sentence: orange, underlined up to the arrow, opens a sheet. */
@Composable
private fun Token(text: String, description: String, tag: String, onClick: () -> Unit) {
    Row(
        Modifier
            .clickable(role = Role.Button, onClickLabel = description, onClick = onClick)
            .drawBehind {
                val stroke = 2.dp.toPx()
                drawLine(MetchuColors.Primary, Offset(0f, size.height - stroke / 2), Offset(size.width, size.height - stroke / 2), stroke)
            }
            .testTag(tag),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(text, style = MetchuType.Title.copy(lineHeight = MetchuType.Title.fontSize * 1.2f), color = MetchuColors.Primary)
        Image(Icons.ChevronDown, null, Modifier.size(22.dp), colorFilter = ColorFilter.tint(MetchuColors.Primary))
    }
}

/**
 * A still map around the user behind the whole screen, hidden under the background in the
 * upper half and showing through toward the bottom, so it has no edge. As [expanded] goes
 * to 1 the white draws back to the top, and [zoomedOut] shows the whole campus.
 */
@Composable
private fun StartMap(center: Point, expanded: Float, zoomedOut: Boolean) {
    val camera = rememberCameraPositionState {
        position = CameraPosition.fromLatLngZoom(LatLng(center.lat, center.lng), MapZoom)
    }
    // Only a change zooms: on the first frame the map's own camera is not this one yet.
    var zoomed by remember { mutableStateOf(false) }
    LaunchedEffect(center) {
        camera.position = CameraPosition.fromLatLngZoom(LatLng(center.lat, center.lng), if (zoomed) CampusZoom else MapZoom)
    }
    LaunchedEffect(zoomedOut) {
        if (zoomedOut == zoomed) return@LaunchedEffect
        zoomed = zoomedOut
        camera.animate(CameraUpdateFactory.zoomTo(if (zoomedOut) CampusZoom else MapZoom), 700)
    }
    // Google's logo sits on the 20 dp margin just above the language and settings buttons (the SDK
    // adds ~6 dp itself). The top padding then puts the user's position under the start button's center.
    val navigation = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    val bottom = navigation + CornerButtonBottom + 44.dp + 4.dp
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val top = maxHeight + bottom - (ActionCenterFromBottom + navigation) * 2
        GoogleMap(
            modifier = Modifier.fillMaxSize(),
            cameraPositionState = camera,
            contentPadding = PaddingValues(start = 14.dp, top = top.coerceAtLeast(0.dp), bottom = bottom),
            uiSettings = MapUiSettings(
                compassEnabled = false, mapToolbarEnabled = false, myLocationButtonEnabled = false,
                rotationGesturesEnabled = false, scrollGesturesEnabled = false, tiltGesturesEnabled = false,
                zoomControlsEnabled = false, zoomGesturesEnabled = false, indoorLevelPickerEnabled = false
            )
        )
        // White behind the sentence, then the map shows soon below it; searching, only behind the headline.
        Box(
            Modifier.fillMaxSize().drawBehind {
                drawRect(
                    Brush.verticalGradient(
                        0f to Color.White,
                        lerp(0.36f, 0.2f, expanded) to Color.White,
                        lerp(0.9f, 0.86f, expanded) to Color.White.copy(alpha = 0f)
                    )
                )
            }
        )
    }
}

private const val MapZoom = 16f
private const val CampusZoom = 14.5f

/**
 * The globe button grows into the language menu where it stands, and shrinks back when a
 * language is picked or the user taps elsewhere.
 */
@Composable
private fun LanguageMenu(modifier: Modifier = Modifier, onPick: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    val current = LocalConfiguration.current.locales[0].language
    val motion = tween<Dp>(260, easing = SheetEasing)
    val width by animateDpAsState(if (open) 168.dp else 44.dp, motion, label = "width")
    val height by animateDpAsState(if (open) 108.dp else 44.dp, motion, label = "height")
    val corner by animateDpAsState(if (open) 16.dp else 22.dp, motion, label = "corner")
    val globe by animateFloatAsState(if (open) 0f else 1f, tween(120), label = "globe")
    val items by animateFloatAsState(if (open) 1f else 0f, tween(160, delayMillis = if (open) 100 else 0), label = "items")
    if (open) {
        Box(Modifier.fillMaxSize().clickable(remember { MutableInteractionSource() }, null) { open = false })
    }
    val shape = RoundedCornerShape(corner)
    // Closed, the globe is the gear's twin: its own shadow and press, nothing behind it.
    val morphing = open || width > 44.dp
    Box(
        modifier
            .size(width, height)
            .then(if (morphing) Modifier.cssShadow(shape, 6.dp, 24.dp, 0.18f).clip(shape).background(Color.White) else Modifier)
    ) {
        if (globe > 0f) {
            CircleIconButton(
                Icons.Globe, stringResource(R.string.language), { open = true },
                Modifier.align(Alignment.BottomStart).fade { globe }.testTag("language")
            )
        }
        if (items > 0f) {
            Column(Modifier.requiredWidth(168.dp).align(Alignment.BottomStart).padding(6.dp).alpha(items)) {
                Languages.forEach { (tag, name) ->
                    val on = current == tag
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .height(48.dp)
                            .clip(RoundedCornerShape(10.dp))
                            .background(if (on) MetchuColors.Grey100 else Color.White)
                            .selectable(on, role = Role.RadioButton) {
                                open = false
                                if (!on) onPick(tag)
                            }
                            .padding(horizontal = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        MenuRowContent(stringResource(name), null, on)
                    }
                }
            }
        }
    }
}
