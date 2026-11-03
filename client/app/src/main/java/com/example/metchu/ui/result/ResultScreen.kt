package com.example.metchu.ui.result

import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.requiredSize
import com.example.metchu.ui.common.fade
import androidx.activity.compose.BackHandler
import androidx.annotation.StringRes
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.CompositingStrategy
import com.example.metchu.ui.common.floating
import com.example.metchu.ui.common.pressScale
import com.example.metchu.ui.common.rememberHeading
import com.google.maps.android.compose.CameraMoveStartedReason
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.statusBars
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.role
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.Spacer
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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.animation.core.Animatable
import kotlinx.coroutines.launch
import com.example.metchu.ui.start.CampusCenter
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.example.metchu.BuildConfig
import com.example.metchu.R
import com.example.metchu.data.model.Ban
import com.example.metchu.data.model.MenuDish
import com.example.metchu.data.model.Offer
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.model.Step
import com.example.metchu.data.repository.Place
import com.example.metchu.ui.common.BottomSheet
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.NavigationBarFade
import com.example.metchu.ui.common.ActionCapsule
import com.example.metchu.ui.common.TopRow
import com.example.metchu.ui.common.SheetEasing
import com.example.metchu.ui.common.Spinner
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
 * them and always turns down the server's current guess. "Menu" on a cafeteria lists
 * what else it serves at that meal; [menus] holds those lists, null while one loads.
 * Under the dish, [onBan] keeps its group out of the rest of the session once the group
 * makes up two of the last three proposals; a dish without a group can be banned alone at
 * any time. A ban in [banned] can be lifted the same way.
 */
@Composable
fun ResultScreen(
    session: SessionState,
    shown: List<Step>,
    reasons: Map<String, String?>,
    menus: Map<String, List<MenuDish>?>,
    banned: Set<Ban>,
    place: Place,
    loading: Boolean,
    onBack: () -> Unit,
    onHome: () -> Unit,
    onMore: () -> Unit,
    onMenu: (restaurant: String) -> Unit,
    onBan: (Ban, banned: Boolean) -> Unit
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
    // Counts taps on a cafeteria, so tapping the one already chosen brings the map back to it.
    var focus by remember { mutableIntStateOf(0) }

    var menuOf by remember(food) { mutableStateOf<Offer?>(null) }
    BackHandler(menuOf != null) { menuOf = null }

    // Gson leaves a missing group null.
    val kind = food.foodGroup.orEmpty().ifBlank { null }
    val ban = if (kind != null) Ban(foodGroup = kind) else Ban(foodId = food.foodId)
    val isBanned = ban in banned
    val banLabel = when {
        kind == null -> stringResource(if (isBanned) R.string.result_unban else R.string.result_ban)
        isBanned -> stringResource(R.string.result_unban_group, kind)
        (maxOf(viewing - 2, 0) until viewing).any { shown[it].food?.foodGroup == kind } ->
            stringResource(R.string.result_ban_group, kind)
        else -> null
    }

    // Everything enters in a short sequence each time a dish is shown.
    val key = step.guessId ?: food.foodId.toString()
    var revealed by remember(key) { mutableStateOf(false) }
    LaunchedEffect(key) { revealed = true }

    BoxWithConstraints(Modifier.fillMaxSize().background(MetchuColors.MapBlank)) {
        val height = maxHeight
        val density = LocalDensity.current
        val heightPx = constraints.maxHeight.toFloat()
        val statusPx = WindowInsets.statusBars.getTop(density).toFloat()
        val navPx = WindowInsets.navigationBars.getBottom(density).toFloat()
        // Full stops under the top row; peek leaves two lines above the navigation bar.
        val topOf = { stop: SheetStop ->
            with(density) {
                when (stop) {
                    SheetStop.FULL -> statusPx + 73.dp.toPx()
                    SheetStop.HALF -> heightPx * 0.474f
                    SheetStop.PEEK -> heightPx - navPx - 80.dp.toPx()
                }
            }
        }
        val scope = rememberCoroutineScope()
        var stop by remember(key) { mutableStateOf(SheetStop.HALF) }
        val top = remember(key) { Animatable(topOf(SheetStop.HALF)) }
        val sheetTop = with(density) { top.value.toDp() }
        val settle: (SheetStop) -> Unit = { next ->
            stop = next
            scope.launch { top.animateTo(topOf(next), tween(380, easing = SheetEasing)) }
        }
        val drag: (Float) -> Unit = { dy ->
            scope.launch { top.snapTo((top.value + dy).coerceIn(topOf(SheetStop.FULL), topOf(SheetStop.PEEK))) }
        }
        val chips = shown.size > 1 && stop != SheetStop.FULL
        // The locate button: off the user, centered on the user, or turned to where the phone faces.
        var locate by remember { mutableStateOf(Locate.FREE) }
        val heading = rememberHeading(locate == Locate.HEADING)

        val mapIn by animateFloatAsState(if (revealed) 1f else 0f, tween(380, easing = SheetEasing), label = "map")
        Box(Modifier.fillMaxSize().graphicsLayer { alpha = mapIn; scaleX = 1.06f - 0.06f * mapIn; scaleY = scaleX }) {
            if (BuildConfig.HAS_MAPS_KEY) {
                // The padding follows the resting sheet, not the finger, so the map does not slide while dragging.
                CafeteriaMap(
                    cafeterias.cafeterias.distinctBy { it.offer.restaurant }, selected, focus,
                    start = cafeterias.cafeterias.firstNotNullOfOrNull { it.point } ?: user ?: CampusCenter,
                    user = user,
                    locate = locate,
                    heading = heading,
                    // Above the dish chips when they are shown, so they never cover the logo.
                    bottomInset = with(density) { (heightPx - topOf(stop)).toDp() } + if (chips) ChipRowHeight else 0.dp,
                    onMovedByHand = { locate = Locate.FREE }
                ) { selected = it; focus++; locate = Locate.FREE }
            }
        }

        val topIn by animateFloatAsState(if (revealed) 1f else 0f, tween(220, delayMillis = 400), label = "top")
        Column(Modifier.statusBarsPadding().fade { topIn }) {
            TopRow {
                CircleIconButton(Icons.Back, stringResource(R.string.back), { if (!loading) onBack() }, Modifier.testTag("back"))
                CircleIconButton(Icons.Home, stringResource(R.string.result_home), onHome, Modifier.testTag("home"))
            }
        }

        // What rides on the sheet fades out as it rises from half to full, following the finger.
        val above = ((top.value - topOf(SheetStop.FULL)) / (topOf(SheetStop.HALF) - topOf(SheetStop.FULL))).coerceIn(0f, 1f)
        // The dishes shown so far ride just above the sheet, centered 40 dp over it.
        if (shown.size > 1 && above > 0f) {
            ShownChips(shown, viewing, Modifier.offset(y = sheetTop - ChipRowHeight - 10.dp).fade { topIn * above }) { viewing = it }
        }
        if (above > 0f && BuildConfig.HAS_MAPS_KEY) {
            LocateButton(
                locate,
                Modifier.align(Alignment.TopEnd).offset(y = sheetTop - 64.dp).padding(end = 20.dp).fade { topIn * above }
            ) {
                when {
                    !permission.granted -> permission.request()
                    else -> locate = when (locate) {
                        Locate.FREE, Locate.HEADING -> Locate.CENTER
                        Locate.CENTER -> Locate.HEADING
                    }
                }
            }
        }

        val peek = stop == SheetStop.PEEK
        val chosen = cafeterias.cafeterias.firstOrNull { it.offer.restaurant == selected } ?: cafeterias.cafeterias.firstOrNull()
        ResultSheet(
            step = step,
            reason = reasons[step.proposalId],
            writingReason = step.proposalId in reasons && reasons[step.proposalId] == null,
            caption = captionFor(session.meal),
            banLabel = banLabel,
            onBan = { if (!loading) onBan(ban, !isBanned) },
            cafeterias = cafeterias,
            chosen = chosen,
            selected = selected,
            onSelect = { selected = it; focus++; locate = Locate.FREE },
            onMenu = { offer ->
                onMenu(offer.restaurant)
                menuOf = offer
            },
            revealed = revealed,
            stop = stop,
            onTap = { settle(tappedStop(stop)) },
            onDrag = drag,
            onRelease = { moved ->
                val nearest = SheetStop.entries.minBy { abs(topOf(it) - top.value) }
                settle(draggedStop(stop, nearest, down = moved > 0, far = abs(moved) > with(density) { 40.dp.toPx() }))
            },
            modifier = Modifier.offset(y = sheetTop).height(height - sheetTop)
        )
        val fade by animateFloatAsState(if (peek) 0f else 1f, tween(200), label = "fade")
        NavigationBarFade(Modifier.align(Alignment.BottomCenter).alpha(fade))
        // Folded, the sheet's right half tells where and how far, next to the + button.
        val factsIn by animateFloatAsState(if (peek && chosen != null) 1f else 0f, tween(200), label = "facts")
        if (chosen != null && factsIn > 0f) {
            PeekFacts(chosen, Modifier.align(Alignment.BottomEnd).navigationBarsPadding().padding(end = 80.dp, bottom = 20.dp).alpha(factsIn))
        }
        // "Find another" comes in a little after the dish, so the dish is read first.
        if (current.type == Step.GUESS) {
            val moreIn by animateFloatAsState(if (revealed) 1f else 0f, tween(320, delayMillis = 600, easing = SheetEasing), label = "more")
            ActionCapsule(
                stringResource(R.string.result_more), Icons.Plus, { if (!loading) onMore() }, filled = true,
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    .navigationBarsPadding()
                    .padding(end = 20.dp, bottom = 16.dp)
                    .graphicsLayer { alpha = moreIn; translationY = 12.dp.toPx() * (1f - moreIn); compositingStrategy = CompositingStrategy.ModulateAlpha }
                    .testTag("more"),
                expanded = !peek
            )
        }

        MenuSheet(menuOf, menus, food.foodId) { menuOf = null }
    }
}

/** The chosen cafeteria and how far it is, right-aligned beside the folded + button. */
@Composable
private fun PeekFacts(cafeteria: Cafeteria, modifier: Modifier = Modifier) {
    Column(modifier, horizontalAlignment = Alignment.End) {
        Text(cafeteria.offer.restaurant, style = MetchuType.Label.copy(lineHeight = 22.sp), maxLines = 1)
        val meters = cafeteria.meters
        if (meters != null) {
            Text(
                "${distanceText(meters)} · ${stringResource(R.string.walk_minutes, cafeteria.walkMinutes ?: 1)}",
                style = PeekSecondStyle,
                color = MetchuColors.Grey600
            )
        }
    }
}

@StringRes
private fun captionFor(meal: String?): Int = when (meal) {
    "BR" -> R.string.result_caption_breakfast
    "LU" -> R.string.result_caption_lunch
    "DN" -> R.string.result_caption_dinner
    else -> R.string.result_caption_any
}

/** 40 dp chips with room for their shadow above and below. */
private val ChipRowHeight = 60.dp

/** The dishes shown so far, newest first; [viewing] and [onView] use indices into [shown]. */
@Composable
private fun ShownChips(shown: List<Step>, viewing: Int, modifier: Modifier = Modifier, onView: (Int) -> Unit) {
    val row = rememberLazyListState()
    LaunchedEffect(shown.size) { row.animateScrollToItem(0) }
    LazyRow(
        modifier
            .height(ChipRowHeight)
            .graphicsLayer { compositingStrategy = CompositingStrategy.Offscreen }
            .drawWithContent {
                drawContent()
                val fade = 104.dp.toPx()
                drawRect(
                    Brush.horizontalGradient(listOf(Color.Black, Color.Transparent), startX = size.width - fade, endX = size.width - 68.dp.toPx()),
                    blendMode = BlendMode.DstIn
                )
            },
        state = row,
        contentPadding = PaddingValues(start = 20.dp, end = 84.dp, top = 10.dp, bottom = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        items(shown.indices.reversed().toList(), key = { shown[it].guessId ?: it.toString() }) { index ->
            val step = shown[index]
            val on = index == viewing
            val background by animateColorAsState(if (on) MetchuColors.Grey900 else Color.White, label = "chip")
            Box(
                Modifier
                    .height(40.dp)
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
    banLabel: String?,
    onBan: () -> Unit,
    cafeterias: CafeteriaList,
    chosen: Cafeteria?,
    selected: String?,
    onSelect: (String) -> Unit,
    onMenu: (Offer) -> Unit,
    revealed: Boolean,
    stop: SheetStop,
    onTap: () -> Unit,
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
    val shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp)
    val peek = stop == SheetStop.PEEK

    Column(
        modifier
            .fillMaxWidth()
            .graphicsLayer { translationY = size.height * slide }
            .cssShadow(shape, (-2).dp, 12.dp, 0.10f)
            .clip(shape)
            .background(Color.White)
    ) {
        // The handle and everything above the cafeterias move the sheet: drag it, or tap for the next stop.
        val tap by rememberUpdatedState(onTap)
        val drag by rememberUpdatedState(onDrag)
        val release by rememberUpdatedState(onRelease)
        var moved by remember { mutableFloatStateOf(0f) }
        val grip = Modifier
            .pointerInput(Unit) { detectTapGestures { tap() } }
            .pointerInput(Unit) {
                detectVerticalDragGestures(
                    onDragStart = { moved = 0f },
                    onDragEnd = { release(moved) },
                    onDragCancel = { release(moved) }
                ) { change, dy ->
                    change.consume()
                    moved += dy
                    drag(dy)
                }
            }
        Box(
            grip
                .fillMaxWidth()
                .height(20.dp)
                .semantics {
                    contentDescription = toggle
                    role = Role.Button
                    onClick(toggle) { onTap(); true }
                },
            contentAlignment = Alignment.Center
        ) {
            Box(Modifier.width(38.dp).height(3.5.dp).clip(CircleShape).background(MetchuColors.Grey300))
        }
        val dish = group?.displayName ?: food.displayName
        if (peek) {
            // Folded: what and how much on the left, clear of the facts and the + button on the right.
            Column(grip.fillMaxWidth().padding(start = 20.dp, end = 200.dp).testTag("dish")) {
                Text(dish, style = MetchuType.Item.copy(fontSize = 18.sp, lineHeight = 22.sp), maxLines = 1, overflow = TextOverflow.Ellipsis)
                chosen?.let { Text(priceText(it.offer.price), style = PeekSecondStyle, color = MetchuColors.Grey700) }
            }
            return@Column
        }
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState(), enabled = stop == SheetStop.FULL)
                .padding(bottom = 16.dp)
                .navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(20.dp)
        ) {
            Column(grip.fillMaxWidth().padding(horizontal = 20.dp).rise(titleIn, density)) {
                Text(stringResource(caption), Modifier.padding(bottom = 2.dp), style = MetchuType.Caption)
                Text(dish, Modifier.testTag("dish"), style = MetchuType.Title)
                if (group != null) {
                    val description = listOfNotNull(
                        stringResource(R.string.result_group_example, food.displayName),
                        group.members.filter { it.foodId != food.foodId }.take(MEMBER_PREVIEW)
                            .joinToString(", ") { it.displayName }.ifEmpty { null }
                            ?.let { stringResource(R.string.result_group_members, it) }
                    ).joinToString(". ")
                    Text(description, Modifier.padding(top = 10.dp), style = ReasonStyle)
                }
                // The reason comes after the dish is drawn: a pulsing line holds its place, then it fades in.
                val reasonIn by animateFloatAsState(if (reason != null) 1f else 0f, tween(300), label = "reason")
                if (reason != null) {
                    Text(reason, Modifier.padding(top = 10.dp).graphicsLayer { alpha = reasonIn }.testTag("reason"), style = ReasonStyle)
                } else if (writingReason) {
                    val pulse by rememberInfiniteTransition(label = "writing")
                        .animateFloat(1f, 0.4f, infiniteRepeatable(tween(700), RepeatMode.Reverse), label = "pulse")
                    Text(
                        stringResource(R.string.reason_writing),
                        Modifier.padding(top = 10.dp).graphicsLayer { alpha = pulse }.testTag("reasonWriting"),
                        style = ReasonStyle,
                        color = MetchuColors.Grey600
                    )
                }
                if (banLabel != null) {
                    Text(
                        banLabel,
                        Modifier
                            .padding(top = 2.dp)
                            .clickable(role = Role.Button, onClick = onBan)
                            .padding(vertical = 6.dp)
                            .testTag("ban"),
                        style = MetchuType.Caption.copy(textDecoration = TextDecoration.Underline),
                        color = MetchuColors.Grey600
                    )
                }
            }

            Column(Modifier.rise(listIn, density)) {
                val count = cafeterias.cafeterias.distinctBy { it.offer.restaurant }.size
                // One cafeteria needs no heading; several are counted, nearest first.
                if (count > 1) {
                    Text(
                        stringResource(R.string.result_places, count),
                        Modifier.padding(start = 20.dp, end = 20.dp, bottom = 4.dp).testTag("cafeteriaHeading"),
                        style = MetchuType.Caption
                    )
                }
                val note = when (cafeterias.allListed) {
                    AllListed.NONE_NEAR -> R.string.result_none_near
                    AllListed.NO_LOCATION -> R.string.result_no_location
                    null -> null
                }
                if (note != null) Text(stringResource(note), Modifier.padding(start = 20.dp, end = 20.dp, bottom = 4.dp), style = MetchuType.Caption)
                if (cafeterias.cafeterias.isEmpty()) Text(stringResource(R.string.offer_none), Modifier.padding(horizontal = 20.dp), style = MetchuType.Body)
                cafeterias.cafeterias.forEach { cafeteria ->
                    CafeteriaRow(
                        cafeteria, on = cafeteria.offer.restaurant == selected || count == 1,
                        onClick = { onSelect(cafeteria.offer.restaurant) },
                        onMenu = { onMenu(cafeteria.offer) }
                    )
                }
                // One empty row at the end, for the logo, so "find another" never covers the last cafeteria.
                Spacer(Modifier.height(CafeteriaRowHeight))
            }
        }
    }
}

private fun Modifier.rise(progress: Float, density: Density): Modifier =
    graphicsLayer { alpha = progress; translationY = with(density) { 12.dp.toPx() } * (1f - progress) }

private val CafeteriaRowHeight = 72.dp

/** The reason and the group's description: 14/20. */
private val ReasonStyle = MetchuType.Body.copy(fontSize = 14.sp, lineHeight = 20.sp)

/** The second line of the folded sheet, left and right: 13/18. */
private val PeekSecondStyle = MetchuType.Body.copy(fontSize = 13.sp, lineHeight = 18.sp, fontWeight = FontWeight.Medium)

/**
 * A Material two-line list item, edge to edge: a pin in a 40 dp circle (orange for the chosen
 * cafeteria), the name over the meal and price, and the distance over the walk on the right.
 */
@Composable
private fun CafeteriaRow(cafeteria: Cafeteria, on: Boolean, onClick: () -> Unit, onMenu: () -> Unit) {
    val badge by animateColorAsState(if (on) MetchuColors.Primary else MetchuColors.Grey100, tween(200), label = "badge")
    val pin by animateColorAsState(if (on) Color.White else MetchuColors.Grey600, tween(200), label = "pin")
    val offer = cafeteria.offer
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = CafeteriaRowHeight)
            .clickable(role = Role.Button, onClick = onClick)
            .padding(horizontal = 20.dp, vertical = 12.dp)
            .testTag("cafeteria"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Box(Modifier.size(40.dp).clip(CircleShape).background(badge), contentAlignment = Alignment.Center) {
            Image(Icons.Pin, null, Modifier.size(20.dp), colorFilter = ColorFilter.tint(pin))
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(offer.restaurant, style = MetchuType.Label.copy(fontSize = 17.sp, lineHeight = 24.sp))
            Text(stringResource(R.string.offer_meta, mealName(offer.meal), priceText(offer.price)), style = MetchuType.Caption)
        }
        val meters = cafeteria.meters
        if (meters != null) {
            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(distanceText(meters), style = MetchuType.Label)
                Text(stringResource(R.string.walk_minutes, cafeteria.walkMinutes ?: 1), style = MetchuType.Caption)
            }
        }
        // A 24 dp icon at the row's end, its 40 dp touch circle reaching into the margin.
        Box(Modifier.padding(start = 4.dp).size(24.dp), contentAlignment = Alignment.Center) {
            val interaction = remember { MutableInteractionSource() }
            val pressed by interaction.collectIsPressedAsState()
            val label = stringResource(R.string.result_menu)
            Box(
                Modifier
                    .requiredSize(40.dp)
                    .clip(CircleShape)
                    .background(if (pressed) MetchuColors.Grey100 else Color.Transparent)
                    .clickable(interaction, indication = null, role = Role.Button, onClickLabel = label, onClick = onMenu)
                    .semantics { contentDescription = label }
                    .testTag("menuButton"),
                contentAlignment = Alignment.Center
            ) {
                Image(Icons.Menu, null, Modifier.size(24.dp), colorFilter = ColorFilter.tint(MetchuColors.Grey600))
            }
        }
    }
}

/**
 * What [offer]'s cafeteria serves at its meal, from [menus]: a spinner while the list
 * loads, a note if it could not. The list holds only the session's candidates, which
 * the note under the title says. The dish on screen, [foodId], is orange.
 */
@Composable
private fun MenuSheet(offer: Offer?, menus: Map<String, List<MenuDish>?>, foodId: Int, onDismiss: () -> Unit) {
    // Kept while the sheet slides away.
    var last by remember { mutableStateOf(offer) }
    if (offer != null) last = offer
    val shown = last
    val title = shown?.let { stringResource(R.string.result_menu_title, it.restaurant, mealName(it.meal)) }.orEmpty()
    BottomSheet(offer != null, title, onDismiss) {
        Text(stringResource(R.string.result_menu_note), Modifier.padding(bottom = 4.dp), style = MetchuType.Caption)
        if (shown != null) {
            val dishes = menus[shown.restaurant]
            when {
                shown.restaurant !in menus -> Text(stringResource(R.string.result_menu_failed), style = MetchuType.Body)
                dishes == null -> Spinner(MetchuColors.Primary, 28.dp, Modifier.align(Alignment.CenterHorizontally))
                else -> Column(Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState()).testTag("menu")) {
                    dishes.filter { it.meal == shown.meal }.forEach { dish ->
                        Row(
                            Modifier.fillMaxWidth().heightIn(min = 48.dp).padding(vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(14.dp)
                        ) {
                            Text(
                                dish.displayName, Modifier.weight(1f), style = MetchuType.Item,
                                color = if (dish.foodId == foodId) MetchuColors.Primary else MetchuColors.Grey900
                            )
                            Text(priceText(dish.price), style = MetchuType.Caption)
                        }
                    }
                }
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
 * The camera opens at street level over [start] and then fits the cafeterias and the user
 * (see [framedPoints]), keeping them clear of the sheet, [bottomInset] high. Google's logo
 * stays visible and unchanged just above the sheet, as the Maps terms require; the SDK
 * offers no way to recolor it.
 */
@Composable
private fun CafeteriaMap(
    cafeterias: List<Cafeteria>,
    selected: String?,
    focus: Int,
    start: Point,
    user: Point?,
    locate: Locate,
    heading: Float?,
    bottomInset: Dp,
    onMovedByHand: () -> Unit,
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

    // Fits again when the first fix arrives, not on every later one, so the camera does not undo the user's panning.
    // Keyed on the set: a later fix that only reorders the cafeterias by distance does not fit again either.
    LaunchedEffect(loaded, points.toSet(), user != null) {
        val framed = framedPoints(cafeterias, user).map { LatLng(it.lat, it.lng) }
        if (!loaded || framed.isEmpty()) return@LaunchedEffect
        val update = if (framed.size == 1) {
            CameraUpdateFactory.newLatLngZoom(framed.single(), 16f)
        } else {
            val bounds = LatLngBounds.builder().apply { framed.forEach(::include) }.build()
            CameraUpdateFactory.newLatLngBounds(bounds, with(density) { 48.dp.roundToPx() })
        }
        camera.animate(update, 600)
    }
    // A tapped cafeteria glides to the middle of the map above the sheet, again on every tap.
    LaunchedEffect(focus) {
        val point = cafeterias.firstOrNull { it.offer.restaurant == selected }?.point ?: return@LaunchedEffect
        if (loaded && focus > 0) camera.animate(CameraUpdateFactory.newCameraPosition(CameraPosition(LatLng(point.lat, point.lng), 16f, 0f, 0f)), 750)
    }
    // Centered on the user, north up or turned with the phone.
    LaunchedEffect(loaded, locate, user, heading) {
        if (!loaded || user == null || locate == Locate.FREE) return@LaunchedEffect
        val bearing = if (locate == Locate.HEADING) heading ?: camera.position.bearing else 0f
        camera.animate(CameraUpdateFactory.newCameraPosition(CameraPosition(LatLng(user.lat, user.lng), camera.position.zoom, 0f, bearing)), 400)
    }
    LaunchedEffect(camera.isMoving) {
        if (camera.isMoving && camera.cameraMoveStartedReason == CameraMoveStartedReason.GESTURE) onMovedByHand()
    }

    GoogleMap(
        modifier = Modifier.fillMaxSize().testTag("map"),
        cameraPositionState = camera,
        contentPadding = padding,
        properties = MapProperties(isMyLocationEnabled = user != null),
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

/** What the locate button has done to the map. */
private enum class Locate { FREE, CENTER, HEADING }

/**
 * Like Google Maps' button: grey while the map shows something else, blue once it is
 * centered on the user, and an arrow once the map turns with the phone. Each tap moves on.
 */
@Composable
private fun LocateButton(mode: Locate, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val description = stringResource(if (mode == Locate.CENTER) R.string.locate_heading else R.string.locate_me)
    val interaction = remember { MutableInteractionSource() }
    Box(
        modifier
            .size(48.dp)
            .pressScale(interaction, 0.92f)
            .floating()
            .clip(CircleShape)
            .background(Color.White)
            .clickable(interaction, indication = null, role = Role.Button, onClickLabel = description, onClick = onClick)
            .semantics { contentDescription = description }
            .testTag("locate"),
        contentAlignment = Alignment.Center
    ) {
        val tint = if (mode == Locate.FREE) MetchuColors.Grey700 else MetchuColors.LocationBlue
        if (mode == Locate.HEADING) {
            Image(Icons.Heading, null, Modifier.size(22.dp), colorFilter = ColorFilter.tint(tint))
        } else {
            Image(Icons.Locate, null, Modifier.size(24.dp), colorFilter = ColorFilter.tint(tint))
            if (mode == Locate.CENTER) Box(Modifier.size(6.dp).clip(CircleShape).background(tint))
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

