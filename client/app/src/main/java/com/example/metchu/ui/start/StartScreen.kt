package com.example.metchu.ui.start

import androidx.appcompat.app.AppCompatDelegate
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
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
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.os.LocaleListCompat
import com.example.metchu.BuildConfig
import com.example.metchu.R
import com.example.metchu.data.repository.Place
import com.example.metchu.ui.common.BottomSheetPicker
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.PickerOption
import com.example.metchu.ui.common.Spinner
import com.example.metchu.ui.common.cssShadow
import com.example.metchu.ui.common.pressScale
import com.example.metchu.ui.common.rememberLocationPermission
import com.example.metchu.ui.common.rememberSlow
import com.example.metchu.ui.common.rememberUserPoint
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

/** The middle of the SNU campus, for when the user's position is unknown. */
val CampusCenter = Point(37.4600, 126.9520)

private enum class Sheet { MEAL, PLACE }

/**
 * "Today I'll have [lunch] [nearby]": the meal and the distance are picked inside the
 * sentence, and the round button starts a session. The map behind the button fades in
 * from the background; the button stands where the user is.
 */
@Composable
fun StartScreen(
    meal: Meal,
    place: Place,
    loading: Boolean,
    onMeal: (Meal) -> Unit,
    onPlace: (Place) -> Unit,
    onSettings: () -> Unit,
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
    var askedForLocation by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        if (!permission.granted && !askedForLocation) {
            askedForLocation = true
            permission.request()
        }
    }
    val user = rememberUserPoint(permission.granted)
    // A new language recreates the screen; the words fade out first instead of jumping.
    var switching by remember { mutableStateOf(false) }
    val words by animateFloatAsState(if (switching) 0f else 1f, tween(150), label = "words")

    Box(Modifier.fillMaxSize().screenBackground()) {
        if (BuildConfig.HAS_MAPS_KEY) StartMap(user ?: CampusCenter)

        Column(Modifier.statusBarsPadding().alpha(words)) {
            TopRow(arrangement = Arrangement.End) {}
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
                AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags(tag))
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
    }
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
    Box(
        modifier
            .size(width, height)
            .then(if (open) Modifier.cssShadow(shape, 6.dp, 24.dp, 0.18f) else Modifier.floating(shape))
            .clip(shape)
            .background(Color.White)
    ) {
        if (globe > 0f) {
            CircleIconButton(
                Icons.Globe, stringResource(R.string.language), { open = true },
                Modifier.align(Alignment.BottomStart).alpha(globe).testTag("language")
            )
        }
        if (items > 0f) {
            Column(Modifier.requiredWidth(168.dp).align(Alignment.BottomStart).padding(6.dp).alpha(items)) {
                listOf("ko" to R.string.language_ko, "en" to R.string.language_en).forEach { (tag, name) ->
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
