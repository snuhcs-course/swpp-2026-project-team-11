package com.example.metchu.ui.start

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
import com.example.metchu.ui.common.BottomSheetPicker
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

private enum class Sheet { MEAL, PLACE }

/**
 * "Today I'll have [lunch] [nearby]": the meal and the distance are picked inside the
 * sentence, and the round button starts a session. The map behind the button fades in
 * from the background; the button stands where the user is. With [tip], a tip over the
 * screen points to the globe and the gear, where the language and the allergies change.
 * With [askForLocation] and no permission yet, a notice says why before the system asks,
 * once the tip is closed.
 */
@Composable
fun StartScreen(
    meal: Meal,
    place: Place,
    loading: Boolean,
    tip: Boolean,
    askForLocation: Boolean,
    onMeal: (Meal) -> Unit,
    onPlace: (Place) -> Unit,
    onSettings: () -> Unit,
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
    // The words fade out, change language and fade back in.
    var switching by remember { mutableStateOf(false) }
    val words by animateFloatAsState(if (switching) 0f else 1f, tween(150), label = "words")
    val language = LocalConfiguration.current.locales[0].language
    LaunchedEffect(language) { switching = false }

    Box(Modifier.fillMaxSize().screenBackground()) {
        if (BuildConfig.HAS_MAPS_KEY) StartMap(user ?: CampusCenter)

        Column(Modifier.statusBarsPadding().alpha(words)) {
            // Home tapped by mistake: the session left is one tap away.
            TopRow(arrangement = Arrangement.End) {
                if (onResume != null) ResumeButton(onResume)
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
                Text(stringResource(R.string.start_line4), style = title)
                Text(stringResource(R.string.start_sub), Modifier.padding(top = 16.dp), style = MetchuType.Lead)
            }
        }

        StartButton(
            loading = loading,
            onClick = { onStart(meal) },
            modifier = Modifier.align(Alignment.BottomCenter).navigationBarsPadding()
                .padding(bottom = ActionCenterFromBottom - StartButtonSize / 2).alpha(words)
        )
        // Things set once sit low on the left, out of the way of the sentence and the button.
        CircleIconButton(
            Icons.Gear, stringResource(R.string.settings), onSettings,
            Modifier.align(Alignment.BottomStart).navigationBarsPadding().padding(start = 74.dp, bottom = CornerButtonBottom).testTag("settings")
        )
        LanguageMenu(Modifier.align(Alignment.BottomStart).navigationBarsPadding().padding(start = 20.dp, bottom = CornerButtonBottom)) { tag ->
            scope.launch {
                switching = true
                delay(160)
                setLanguage(tag)
            }
        }

        BottomSheetPicker(
            visible = sheet != null,
            title = stringResource(if (shownSheet == Sheet.PLACE) R.string.start_place_sheet else R.string.start_meal_sheet),
            options = if (shownSheet == Sheet.PLACE) {
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

private val StartButtonSize = 140.dp
/** The language and settings buttons stand this far above the navigation bar. */
private val CornerButtonBottom = 18.dp
private val TitleLine = 39.dp

@Composable
private fun StartButton(loading: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val interaction = remember { MutableInteractionSource() }
    Box(
        modifier
            .size(StartButtonSize)
            .pressScale(interaction)
            .cssShadow(CircleShape, 6.dp, 20.dp, 0.2f)
            .clip(CircleShape)
            .background(MetchuColors.Primary)
            .clickable(interaction, indication = null, enabled = !loading, role = Role.Button, onClick = onClick)
            .testTag("start"),
        contentAlignment = Alignment.Center
    ) {
        // Finding the user and starting the session can take seconds.
        if (rememberSlow(loading)) Spinner(Color.White, 32.dp)
        else Text(stringResource(R.string.start_button), style = MetchuType.Button, color = Color.White, textAlign = TextAlign.Center)
    }
}

@Composable
private fun ResumeButton(onClick: () -> Unit) {
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
            .testTag("resume"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        Image(Icons.Resume, null, Modifier.size(20.dp), colorFilter = ColorFilter.tint(MetchuColors.Grey900))
        Text(stringResource(R.string.resume), style = MetchuType.Button.copy(fontSize = 15.sp))
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
 * upper half and showing through toward the bottom, so it has no edge.
 */
@Composable
private fun StartMap(center: Point) {
    val camera = rememberCameraPositionState {
        position = CameraPosition.fromLatLngZoom(LatLng(center.lat, center.lng), 16f)
    }
    LaunchedEffect(center) { camera.position = CameraPosition.fromLatLngZoom(LatLng(center.lat, center.lng), 16f) }
    // Google's logo sits right of the language and settings buttons, level with them (the SDK adds
    // ~6 dp itself). The top padding then puts the user's position under the start button's center.
    val navigation = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    val bottom = navigation + CornerButtonBottom + 6.dp
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val top = maxHeight + bottom - (ActionCenterFromBottom + navigation) * 2
        GoogleMap(
            modifier = Modifier.fillMaxSize(),
            cameraPositionState = camera,
            contentPadding = PaddingValues(start = 122.dp, top = top.coerceAtLeast(0.dp), bottom = bottom),
            uiSettings = MapUiSettings(
                compassEnabled = false, mapToolbarEnabled = false, myLocationButtonEnabled = false,
                rotationGesturesEnabled = false, scrollGesturesEnabled = false, tiltGesturesEnabled = false,
                zoomControlsEnabled = false, zoomGesturesEnabled = false, indoorLevelPickerEnabled = false
            )
        )
        // White over the top half, then fading out where the button sits.
        Box(
            Modifier.fillMaxSize().background(
                Brush.verticalGradient(
                    0f to Color.White, 0.45f to Color.White, 0.85f to Color.White.copy(alpha = 0f)
                )
            )
        )
    }
}

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
                Modifier.align(Alignment.BottomStart).alpha(globe).testTag("language")
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
                        Text(stringResource(name), style = if (on) MetchuType.Item.copy(fontSize = MetchuType.Button.fontSize) else MetchuType.Button)
                        if (on) Image(Icons.Check, null, Modifier.size(20.dp), colorFilter = ColorFilter.tint(MetchuColors.Grey900))
                    }
                }
            }
        }
    }
}
