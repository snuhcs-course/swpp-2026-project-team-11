package com.example.metchu.ui.start

import androidx.appcompat.app.AppCompatDelegate
import androidx.compose.foundation.Image
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
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
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
import com.example.metchu.ui.common.Wordmark
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

    val permission = rememberLocationPermission()
    var askedForLocation by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        if (!permission.granted && !askedForLocation) {
            askedForLocation = true
            permission.request()
        }
    }
    val user = rememberUserPoint(permission.granted)

    Box(Modifier.fillMaxSize().screenBackground()) {
        if (BuildConfig.HAS_MAPS_KEY) StartMap(user ?: CampusCenter)

        Column(Modifier.statusBarsPadding()) {
            Row(
                Modifier.fillMaxWidth().height(56.dp).padding(start = 20.dp, end = 20.dp, top = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp, Alignment.End)
            ) {
                LanguageButton()
                CircleIconButton(Icons.Gear, stringResource(R.string.settings), onSettings, Modifier.testTag("settings"))
            }
            Column(Modifier.padding(start = 20.dp, end = 20.dp, top = 20.dp)) {
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
                .padding(bottom = ActionCenterFromBottom - StartButtonSize / 2)
        )
        Wordmark(Modifier.align(Alignment.BottomStart).navigationBarsPadding().padding(start = 20.dp, bottom = WordmarkBottom))

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
/** The screen gradient's color where the map starts to show (48 % down). */
private val MapFadeColor = Color(0xFFFCFCFD)
private val WordmarkBottom = 34.dp
private val WordmarkHeight = 20.dp
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
    // Google's logo goes above the wordmark, 20 dp in like everything else (the SDK adds ~6 dp
    // itself). The top padding then puts the user's position under the start button's center.
    val navigation = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    val bottom = navigation + WordmarkBottom + WordmarkHeight + 8.dp - 6.dp
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
        // The screen's own gradient over the top half, then fading out where the button sits.
        Box(
            Modifier.fillMaxSize().background(
                Brush.verticalGradient(
                    0f to Color.White, 0.45f to Color.White, 0.48f to MapFadeColor, 0.85f to MapFadeColor.copy(alpha = 0f)
                )
            )
        )
    }
}

@Composable
private fun LanguageButton() {
    var open by remember { mutableStateOf(false) }
    val current = LocalConfiguration.current.locales[0].language
    Box {
        CircleIconButton(Icons.Globe, stringResource(R.string.language), { open = true })
        DropdownMenu(
            expanded = open,
            onDismissRequest = { open = false },
            shape = RoundedCornerShape(16.dp),
            containerColor = Color.White
        ) {
            listOf("ko" to R.string.language_ko, "en" to R.string.language_en).forEach { (tag, name) ->
                val on = current == tag
                DropdownMenuItem(
                    text = { Text(stringResource(name), style = if (on) MetchuType.Item.copy(fontSize = MetchuType.Button.fontSize) else MetchuType.Button) },
                    trailingIcon = if (on) {
                        { Image(Icons.Check, null, Modifier.size(20.dp), colorFilter = ColorFilter.tint(MetchuColors.Grey900)) }
                    } else null,
                    onClick = {
                        open = false
                        AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags(tag))
                    }
                )
            }
        }
    }
}
