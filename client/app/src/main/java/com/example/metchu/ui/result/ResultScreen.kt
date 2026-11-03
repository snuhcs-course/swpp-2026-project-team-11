package com.example.metchu.ui.result

import androidx.annotation.StringRes
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.animation.core.Animatable
import kotlinx.coroutines.launch
import com.example.metchu.ui.start.CampusCenter
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.example.metchu.BuildConfig
import com.example.metchu.R
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.model.Step
import com.example.metchu.data.repository.Place
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.NavigationBarFade
import com.example.metchu.ui.common.Pill
import com.example.metchu.ui.common.PillDivider
import com.example.metchu.ui.common.PillSegment
import com.example.metchu.ui.common.SheetEasing
import com.example.metchu.ui.common.chipShadow
import com.example.metchu.ui.common.cssShadow
import com.example.metchu.ui.common.rememberLocationPermission
import com.example.metchu.ui.common.rememberUserPoint
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import com.google.android.gms.maps.CameraUpdateFactory
import com.google.android.gms.maps.model.CameraPosition
import com.google.android.gms.maps.model.LatLng
import com.google.android.gms.maps.model.LatLngBounds
import com.google.maps.android.compose.GoogleMap
import com.google.maps.android.compose.MapProperties
import com.google.maps.android.compose.MapUiSettings
import com.google.maps.android.compose.MarkerComposable
import com.google.maps.android.compose.rememberCameraPositionState
import com.google.maps.android.compose.MarkerState
import java.text.NumberFormat
import java.util.Locale
import kotlin.math.abs

/**
 * The proposed dish over a Google map of the cafeterias that serve it. "Find another"
 * turns the dish down and asks on; back returns to the last question. Chips switch
 * between the dishes proposed so far in this session; "Find another" stays on all of
 * them and always turns down the server's current guess.
 */
@Composable
fun ResultScreen(
    session: SessionState,
    shown: List<Step>,
    reasons: Map<String, String?>,
    place: Place,
    loading: Boolean,
    onBack: () -> Unit,
    onHome: () -> Unit,
    onMore: () -> Unit
) {
    val current = session.step
    var viewing by remember(shown.size, current.guessId) { mutableIntStateOf(shown.indexOfFirst { it.guessId == current.guessId }) }
    val step = shown.getOrNull(viewing) ?: current
    val food = step.food ?: return

    val permission = rememberLocationPermission()
    val user = rememberUserPoint(permission.granted)
    val cafeterias = remember(food, user, place) { cafeteriaList(food, user, place) }
    // By restaurant: the list re-sorts as the user moves, and one restaurant can have several lines.
    var selected by remember(food) { mutableStateOf(cafeterias.cafeterias.firstOrNull()?.offer?.restaurant) }

    // Everything enters in a short sequence each time a dish is shown.
    val key = step.guessId ?: food.foodId.toString()
    var revealed by remember(key) { mutableStateOf(false) }
    LaunchedEffect(key) { revealed = true }

    BoxWithConstraints(Modifier.fillMaxSize().background(MetchuColors.MapBlank)) {
        val height = maxHeight
        val density = LocalDensity.current
        val heightPx = constraints.maxHeight.toFloat()
        val scope = rememberCoroutineScope()
        var stop by remember(key) { mutableStateOf(SheetStop.MIDDLE) }
        val top = remember(key) { Animatable(SheetStop.MIDDLE.fraction * heightPx) }
        val sheetTop = with(density) { top.value.toDp() }
        val settle: (SheetStop) -> Unit = { next ->
            stop = next
            scope.launch { top.animateTo(next.fraction * heightPx, tween(380, easing = SheetEasing)) }
        }
        val drag: (Float) -> Unit = { dy ->
            scope.launch { top.snapTo((top.value + dy).coerceIn(SheetStop.HIGH.fraction * heightPx, SheetStop.LOW.fraction * heightPx)) }
        }

        val mapIn by animateFloatAsState(if (revealed) 1f else 0f, tween(380, easing = SheetEasing), label = "map")
        Box(Modifier.fillMaxSize().graphicsLayer { alpha = mapIn; scaleX = 1.06f - 0.06f * mapIn; scaleY = scaleX }) {
            if (BuildConfig.HAS_MAPS_KEY) {
                // The padding follows the resting sheet, not the finger, so the map does not slide while dragging.
                CafeteriaMap(
                    cafeterias.cafeterias.distinctBy { it.offer.restaurant }, selected, permission.granted,
                    start = cafeterias.cafeterias.firstNotNullOfOrNull { it.point } ?: user ?: CampusCenter,
                    // Above the dish chips when they are shown, so they never cover the logo.
                    bottomInset = height * (1f - stop.fraction) + if (shown.size > 1) ChipRowHeight else 0.dp
                ) { selected = it }
            }
        }

        val topIn by animateFloatAsState(if (revealed) 1f else 0f, tween(220, delayMillis = 400), label = "top")
        Column(Modifier.statusBarsPadding().alpha(topIn)) {
            Row(
                Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, top = 6.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                CircleIconButton(Icons.Back, stringResource(R.string.back), { if (!loading) onBack() }, Modifier.testTag("back"))
                // "Start over" keeps the corner whether or not "Find another" is offered.
                Pill {
                    val more = current.type == Step.GUESS
                    if (more) {
                        PillSegment(stringResource(R.string.result_more), { if (!loading) onMore() }, start = 18.dp, end = 14.dp)
                        PillDivider()
                    }
                    PillSegment(stringResource(R.string.result_home), onHome, start = if (more) 14.dp else 18.dp, modifier = Modifier.testTag("home"))
                }
            }
        }

        // The dishes shown so far ride just above the sheet.
        if (shown.size > 1) {
            ShownChips(shown, viewing, Modifier.offset(y = sheetTop - ChipRowHeight).alpha(topIn)) { viewing = it }
        }

        ResultSheet(
            step = step,
            reason = reasons[step.proposalId],
            writingReason = step.proposalId in reasons && reasons[step.proposalId] == null,
            caption = captionFor(session.meal),
            cafeterias = cafeterias,
            place = place,
            selected = selected,
            onSelect = { selected = it },
            revealed = revealed,
            stop = stop,
            onStop = settle,
            onDrag = drag,
            onRelease = { moved ->
                // Snap to the nearest stop, but always move on once the finger has gone far enough.
                val nearest = SheetStop.entries.minBy { abs(it.fraction * heightPx - top.value) }
                settle(if (nearest == stop && abs(moved) > with(density) { 40.dp.toPx() }) stop.step(moved > 0) else nearest)
            },
            modifier = Modifier.offset(y = sheetTop).height(height - sheetTop)
        )
        NavigationBarFade(Modifier.align(Alignment.BottomCenter))
    }
}

@StringRes
private fun captionFor(meal: String?): Int = when (meal) {
    "BR" -> R.string.result_caption_breakfast
    "LU" -> R.string.result_caption_lunch
    "DN" -> R.string.result_caption_dinner
    else -> R.string.result_caption_any
}

/** Where the result sheet rests: high (expanded), middle (as designed) or low (title only). */
private enum class SheetStop(val fraction: Float) {
    HIGH(0.197f), MIDDLE(0.474f), LOW(0.74f);

    /** The next stop down ([down]) or up, or this one at the end. */
    fun step(down: Boolean): SheetStop = entries.getOrElse(ordinal + if (down) 1 else -1) { this }
}

/** 36 dp chips with room for their shadow above and below. */
private val ChipRowHeight = 60.dp

/** The dishes shown so far, newest first; [viewing] and [onView] use indices into [shown]. */
@Composable
private fun ShownChips(shown: List<Step>, viewing: Int, modifier: Modifier = Modifier, onView: (Int) -> Unit) {
    val row = rememberLazyListState()
    LaunchedEffect(shown.size) { row.animateScrollToItem(0) }
    LazyRow(
        modifier.height(ChipRowHeight),
        state = row,
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        items(shown.indices.reversed().toList(), key = { shown[it].guessId ?: it.toString() }) { index ->
            val step = shown[index]
            val on = index == viewing
            val background by animateColorAsState(if (on) MetchuColors.Grey900 else Color.White, label = "chip")
            Box(
                Modifier
                    .height(36.dp)
                    .chipShadow()
                    .clip(CircleShape)
                    .background(background)
                    .clickable(role = Role.Tab) { onView(index) }
                    .padding(horizontal = 14.dp)
                    .testTag("dishChip"),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    step.group?.displayName ?: step.food?.displayName.orEmpty(),
                    style = MetchuType.Label,
                    color = if (on) Color.White else MetchuColors.Grey900
                )
            }
        }
    }
}

@Composable
private fun ResultSheet(
    step: Step,
    reason: String?,
    writingReason: Boolean,
    @StringRes caption: Int,
    cafeterias: CafeteriaList,
    place: Place,
    selected: String?,
    onSelect: (String) -> Unit,
    revealed: Boolean,
    stop: SheetStop,
    onStop: (SheetStop) -> Unit,
    onDrag: (Float) -> Unit,
    onRelease: (Float) -> Unit,
    modifier: Modifier = Modifier
) {
    val food = step.food ?: return
    val group = step.group
    val density = LocalDensity.current
    val slide by animateFloatAsState(if (revealed) 0f else 1f, tween(420, delayMillis = 60, easing = SheetEasing), label = "sheetIn")
    val titleIn by animateFloatAsState(if (revealed) 1f else 0f, tween(300, delayMillis = 260), label = "title")
    val listIn by animateFloatAsState(if (revealed) 1f else 0f, tween(300, delayMillis = 320), label = "list")
    val toggle = stringResource(R.string.result_sheet_toggle)

    Column(
        modifier
            .fillMaxWidth()
            .graphicsLayer { translationY = size.height * slide }
            .cssShadow(RectangleShape, (-6).dp, 20.dp, 0.12f)
            .background(Color.White)
    ) {
        var moved by remember { mutableFloatStateOf(0f) }
        Box(
            Modifier
                .fillMaxWidth()
                .height(36.dp)
                .clickable(role = Role.Button, onClickLabel = toggle) {
                    onStop(if (stop == SheetStop.MIDDLE) SheetStop.HIGH else SheetStop.MIDDLE)
                }
                .pointerInput(Unit) {
                    detectVerticalDragGestures(
                        onDragStart = { moved = 0f },
                        onDragEnd = { onRelease(moved) },
                        onDragCancel = { onRelease(moved) }
                    ) { change, dy ->
                        change.consume()
                        moved += dy
                        onDrag(dy)
                    }
                }
                .semantics { contentDescription = toggle },
            contentAlignment = Alignment.Center
        ) {
            Box(Modifier.width(56.dp).height(4.dp).clip(CircleShape).background(MetchuColors.Grey300))
        }
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState(), enabled = stop == SheetStop.HIGH)
                .padding(start = 20.dp, end = 20.dp, bottom = 24.dp)
                .navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(24.dp)
        ) {
            Column(Modifier.rise(titleIn, density), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(stringResource(caption), style = MetchuType.Caption.copy(fontWeight = MetchuType.Label.fontWeight), color = MetchuColors.Primary)
                Text(group?.displayName ?: food.displayName, Modifier.testTag("dish"), style = MetchuType.Title)
                val description = when {
                    group != null -> listOfNotNull(
                        stringResource(R.string.result_group_example, food.displayName),
                        group.members.filter { it.foodId != food.foodId }.take(MEMBER_PREVIEW)
                            .joinToString(", ") { it.displayName }.ifEmpty { null }
                            ?.let { stringResource(R.string.result_group_members, it) }
                    ).joinToString(". ")
                    food.name != food.displayName -> food.name
                    else -> null
                }
                if (description != null) Text(description, Modifier.padding(top = 6.dp), style = MetchuType.Body)
                // The reason comes after the dish is drawn: a pulsing line holds its place, then it fades in.
                val reasonIn by animateFloatAsState(if (reason != null) 1f else 0f, tween(300), label = "reason")
                if (reason != null) {
                    Text(reason, Modifier.padding(top = 8.dp).graphicsLayer { alpha = reasonIn }.testTag("reason"), style = MetchuType.Body)
                } else if (writingReason) {
                    val pulse by rememberInfiniteTransition(label = "writing")
                        .animateFloat(1f, 0.4f, infiniteRepeatable(tween(700), RepeatMode.Reverse), label = "pulse")
                    Text(
                        stringResource(R.string.reason_writing),
                        Modifier.padding(top = 8.dp).graphicsLayer { alpha = pulse }.testTag("reasonWriting"),
                        style = MetchuType.Body,
                        color = MetchuColors.Grey600
                    )
                }
            }

            Column(Modifier.rise(listIn, density)) {
                Text(
                    stringResource(if (place == Place.NEAR && cafeterias.allListed == null) R.string.result_nearby else R.string.result_all),
                    Modifier.padding(bottom = 6.dp).testTag("cafeteriaHeading"),
                    style = MetchuType.Caption
                )
                val note = when (cafeterias.allListed) {
                    AllListed.NONE_NEAR -> R.string.result_none_near
                    AllListed.NO_LOCATION -> R.string.result_no_location
                    null -> null
                }
                if (note != null) Text(stringResource(note), Modifier.padding(bottom = 6.dp), style = MetchuType.Caption)
                if (cafeterias.cafeterias.isEmpty()) Text(stringResource(R.string.offer_none), style = MetchuType.Body)
                cafeterias.cafeterias.forEach { cafeteria ->
                    CafeteriaRow(cafeteria, cafeteria.offer.restaurant == selected) { onSelect(cafeteria.offer.restaurant) }
                }
            }
        }
    }
}

private fun Modifier.rise(progress: Float, density: Density): Modifier =
    graphicsLayer { alpha = progress; translationY = with(density) { 12.dp.toPx() } * (1f - progress) }

@Composable
private fun CafeteriaRow(cafeteria: Cafeteria, on: Boolean, onClick: () -> Unit) {
    val ink by animateColorAsState(if (on) MetchuColors.Primary else MetchuColors.Grey600, tween(300), label = "row")
    val offer = cafeteria.offer
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 64.dp)
            .clip(RoundedCornerShape(12.dp))
            .clickable(role = Role.Button, onClick = onClick)
            .padding(vertical = 8.dp)
            .testTag("cafeteria"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(offer.restaurant, style = MetchuType.Item, color = ink)
            Text(stringResource(R.string.offer_meta, mealName(offer.meal), priceText(offer.price)), style = MetchuType.Caption)
        }
        val meters = cafeteria.meters
        if (meters != null) {
            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(distanceText(meters), style = MetchuType.Item, color = ink)
                Text(stringResource(R.string.walk_minutes, cafeteria.walkMinutes ?: 1), style = MetchuType.Caption)
            }
        }
    }
}

@Composable
private fun mealName(meal: String): String = stringResource(
    when (meal) {
        "BR" -> R.string.meal_breakfast
        "LU" -> R.string.meal_lunch
        "DN" -> R.string.meal_dinner
        else -> R.string.meal_any
    }
)

@Composable
private fun priceText(price: Int?): String =
    price?.let { stringResource(R.string.price_won, NumberFormat.getIntegerInstance(Locale.US).format(it)) }
        ?: stringResource(R.string.price_unknown)

@Composable
private fun distanceText(meters: Int): String =
    if (meters < 1000) stringResource(R.string.distance_m, meters)
    else stringResource(R.string.distance_km, meters / 1000.0)

/**
 * Google's own map style, with a label pill over each cafeteria. The chosen one is orange.
 * The camera opens at street level over [start] and then fits the cafeterias, keeping
 * them clear of the sheet, [bottomInset] high. Google's logo stays visible and unchanged
 * just above the sheet, as the Maps terms require; the SDK offers no way to recolor it.
 */
@Composable
private fun CafeteriaMap(
    cafeterias: List<Cafeteria>,
    selected: String?,
    showUser: Boolean,
    start: Point,
    bottomInset: Dp,
    onSelect: (String) -> Unit
) {
    val camera = rememberCameraPositionState {
        position = CameraPosition.fromLatLngZoom(LatLng(start.lat, start.lng), 16f)
    }
    var loaded by remember { mutableStateOf(false) }
    val points = cafeterias.mapNotNull { it.point?.let { p -> LatLng(p.lat, p.lng) } }
    val density = LocalDensity.current
    // The SDK draws Google's logo in the padded corner, a few dp in; this lines it up with the 20 dp screen margin.
    val padding = PaddingValues(start = 14.dp, top = 120.dp, bottom = bottomInset + 6.dp)

    LaunchedEffect(loaded, points) {
        if (!loaded || points.isEmpty()) return@LaunchedEffect
        val update = if (points.size == 1) {
            CameraUpdateFactory.newLatLngZoom(points.single(), 16f)
        } else {
            val bounds = LatLngBounds.builder().apply { points.forEach(::include) }.build()
            CameraUpdateFactory.newLatLngBounds(bounds, with(density) { 48.dp.roundToPx() })
        }
        camera.animate(update, 600)
    }
    LaunchedEffect(selected) {
        val point = cafeterias.firstOrNull { it.offer.restaurant == selected }?.point ?: return@LaunchedEffect
        if (loaded && points.size > 1) camera.animate(CameraUpdateFactory.newLatLng(LatLng(point.lat, point.lng)), 400)
    }

    GoogleMap(
        modifier = Modifier.fillMaxSize().testTag("map"),
        cameraPositionState = camera,
        contentPadding = padding,
        properties = MapProperties(isMyLocationEnabled = showUser),
        uiSettings = MapUiSettings(mapToolbarEnabled = false, myLocationButtonEnabled = false, zoomControlsEnabled = false),
        onMapLoaded = { loaded = true }
    ) {
        cafeterias.forEach { cafeteria ->
            val point = cafeteria.point ?: return@forEach
            val on = cafeteria.offer.restaurant == selected
            // Keyed by the cafeteria, so switching dishes moves each pin rather than relabeling another.
            key(cafeteria.offer.restaurant, point) {
                MarkerComposable(
                    cafeteria.offer.restaurant, on, cafeteria.meters ?: -1,
                    state = remember { MarkerState(LatLng(point.lat, point.lng)) },
                    anchor = Offset(0.5f, 0.93f),
                    zIndex = if (on) 1f else 0f,
                    onClick = { onSelect(cafeteria.offer.restaurant); true }
                ) {
                    MapPin(cafeteria, on)
                }
            }
        }
    }
}

@Composable
private fun MapPin(cafeteria: Cafeteria, on: Boolean) {
    // Padding leaves room for the shadows inside the marker's bitmap.
    Column(
        Modifier.padding(start = 10.dp, end = 10.dp, top = 8.dp, bottom = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        Box(
            Modifier
                .chipShadow()
                .clip(CircleShape)
                .background(if (on) MetchuColors.Primary else Color.White)
                .padding(horizontal = 10.dp, vertical = 6.dp)
        ) {
            val name = cafeteria.offer.restaurant.substringBefore('>')
            val label = cafeteria.meters?.let { "$name · ${distanceText(it)}" } ?: name
            Text(label, style = MetchuType.Caption.copy(fontWeight = MetchuType.Item.fontWeight), color = if (on) Color.White else MetchuColors.Grey900)
        }
        Box(
            Modifier
                .size(18.dp)
                .cssShadow(CircleShape, 2.dp, 6.dp, 0.24f)
                .clip(CircleShape)
                .background(Color.White)
                .padding(3.dp)
                .clip(CircleShape)
                .background(if (on) MetchuColors.Primary else MetchuColors.Grey600)
        )
    }
}

/** How many other dishes of a group the description names. */
private const val MEMBER_PREVIEW = 5

