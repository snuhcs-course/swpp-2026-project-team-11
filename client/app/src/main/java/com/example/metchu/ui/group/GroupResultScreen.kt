package com.example.metchu.ui.group

import androidx.compose.foundation.Image
import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.metchu.BuildConfig
import com.example.metchu.R
import com.example.metchu.data.model.RoomDish
import com.example.metchu.data.model.RoomMember
import com.example.metchu.data.model.RoomPick
import com.example.metchu.data.model.RoomState
import com.example.metchu.ui.common.ActionCapsule
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.Spinner
import com.example.metchu.ui.common.TopRow
import com.example.metchu.ui.common.chipShadow
import com.example.metchu.ui.common.cssShadow
import com.example.metchu.ui.common.rememberLocationPermission
import com.example.metchu.ui.common.rememberUserPoint
import com.example.metchu.ui.result.MapPin
import com.example.metchu.ui.result.Point
import com.example.metchu.ui.result.RowIconButton
import com.example.metchu.ui.result.WALK_METERS_PER_MINUTE
import com.example.metchu.ui.result.captionFor
import com.example.metchu.ui.result.distanceText
import com.example.metchu.ui.result.openDirections
import com.example.metchu.ui.result.priceText
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import com.google.android.gms.maps.CameraUpdateFactory
import com.google.android.gms.maps.model.CameraPosition
import com.google.android.gms.maps.model.LatLng
import com.google.android.gms.maps.model.LatLngBounds
import com.google.maps.android.compose.GoogleMap
import com.google.maps.android.compose.MapUiSettings
import com.google.maps.android.compose.MarkerComposable
import com.google.maps.android.compose.MarkerState
import com.google.maps.android.compose.rememberCameraPositionState
import kotlin.math.ceil

/**
 * Every restaurant the room has been shown, named on chips over the map with the newest find
 * first, and each member's dish at the one chosen, this phone's member first. Until the host
 * decides, everyone may agree with any of them; each chip shows how many agree and, with two or
 * more restaurants, every one with the most votes is marked popular. The host decides with
 * "Go here"; every phone then opens [DecidedDialog] once, and the "Meet at" pill opens it again.
 * While the room has [RoomState.more], the host's "Find other places" adds restaurants the room
 * has not been shown, and every phone moves to the first new one.
 */
@Composable
fun GroupResultScreen(
    room: RoomState,
    busy: Boolean,
    onVote: (Int, Boolean) -> Unit,
    onDecide: (Int) -> Unit,
    onAnother: () -> Unit,
    onHome: () -> Unit
) {
    val picks = room.picks.orEmpty()
    if (picks.isEmpty()) return
    // Picks are told apart by position: two branches of one chain share a name. Votes change the
    // picks without changing the restaurants, so the view and the scroll follow the restaurants:
    // when a find adds some, every phone moves to the first new one.
    val restaurants = picks.map { Triple(it.restaurant, it.lat, it.lng) }
    var viewing by rememberSaveable(restaurants) { mutableIntStateOf(newestFirst(picks)) }
    room.decided?.let { viewing = it }
    val shownAt = viewing.coerceIn(picks.indices)
    val pick = picks[shownAt]
    val popular = popularPicks(room)
    val user = rememberUserPoint(rememberLocationPermission().granted)
    // The decision opens the dialog once per room: the host's from the decide reply, the others' from their next poll.
    var decidedOpen by rememberSaveable(room.code) { mutableStateOf(false) }
    var decidedSeen by rememberSaveable(room.code) { mutableStateOf(false) }
    LaunchedEffect(room.decided) {
        if (room.decided != null && !decidedSeen) {
            decidedSeen = true
            decidedOpen = true
        }
    }

    BoxWithConstraints(Modifier.fillMaxSize().background(MetchuColors.MapBlank)) {
        val sheetTop = maxHeight * 0.42f
        if (BuildConfig.HAS_MAPS_KEY) PicksMap(picks, shownAt, sheetHeight = maxHeight - sheetTop) { if (room.decided == null) viewing = it }

        TopRow(Modifier.statusBarsPadding(), arrangement = Arrangement.End) {
            CircleIconButton(Icons.Home, stringResource(R.string.result_home), onHome, Modifier.testTag("home"))
        }
        PickChips(
            picks, chipOrder(picks).filter { room.decided == null || it == room.decided }, shownAt, popular,
            Modifier.fillMaxWidth().padding(top = sheetTop - 56.dp - ChipInset)
        ) { if (room.decided == null) viewing = it }

        val shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp)
        Column(
            Modifier
                .padding(top = sheetTop)
                .fillMaxSize()
                .cssShadow(shape, (-2).dp, 12.dp, 0.10f)
                .clip(shape)
                .background(Color.White)
                .verticalScroll(remember(restaurants) { ScrollState(0) })
                .padding(top = 20.dp, bottom = 140.dp)
        ) {
            key(shownAt) {
                PickDetails(room, pick, user) {
                    AgreeButton(pick, enabled = room.decided == null && !busy, onToggle = { onVote(shownAt, !pick.voted) })
                }
            }
        }

        val bottom = Modifier.align(Alignment.BottomEnd).navigationBarsPadding().padding(end = 20.dp, bottom = 16.dp)
        when {
            room.decided != null -> StatusPill(
                stringResource(R.string.group_meet, placeName(pick.restaurant)), dark = true, modifier = bottom.testTag("decided"),
                onClick = { decidedOpen = true }
            )
            room.isHost -> Row(bottom, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                if (room.more) {
                    ActionCapsule(
                        stringResource(R.string.group_more), Icons.Plus, { if (!busy) onAnother() },
                        filled = false, modifier = Modifier.testTag("more")
                    )
                }
                ActionCapsule(
                    stringResource(R.string.group_decide), Icons.Check, { if (!busy) onDecide(shownAt) },
                    filled = true, modifier = Modifier.testTag("decide")
                )
            }
            else -> StatusPill(stringResource(R.string.group_host_picking), dark = false, modifier = bottom)
        }
    }
    room.decided?.let { decided ->
        if (decidedOpen) {
            DecidedDialog(
                room, picks[decided.coerceIn(picks.indices)], user,
                onClose = { decidedOpen = false },
                onHome = { decidedOpen = false; onHome() }
            )
        }
    }
}

/**
 * [vote] sits at the right of the restaurant's name. Directions start from this phone's
 * position [user], not the host's, which the distance is measured from.
 */
@Composable
private fun PickDetails(room: RoomState, pick: RoomPick, user: Point?, vote: @Composable () -> Unit) {
    Column(Modifier.padding(horizontal = 20.dp)) {
        Box(Modifier.fillMaxWidth()) {
            Column {
                Text(stringResource(captionFor(room.meal)), style = MetchuType.Caption)
                Text(placeName(pick.restaurant), Modifier.padding(top = 2.dp, end = 56.dp).testTag("restaurant"), style = MetchuType.Title)
                Row(Modifier.padding(top = 2.dp, end = 56.dp), verticalAlignment = Alignment.CenterVertically) {
                    pick.distanceM?.let { meters ->
                        Text(walkLine(meters), Modifier.padding(end = 8.dp).testTag("distance"), style = MetchuType.Body)
                    }
                    if (pick.lat != null && pick.lng != null) {
                        val context = LocalContext.current
                        val name = placeName(pick.restaurant)
                        RowIconButton(Icons.Directions, stringResource(R.string.result_directions), "directionsButton") {
                            context.openDirections(name, Point(pick.lat, pick.lng), user)
                        }
                    }
                }
            }
            Box(Modifier.align(Alignment.TopEnd).padding(top = 12.dp)) { vote() }
        }
        Text(stringResource(R.string.group_each_dish), Modifier.padding(top = 20.dp, bottom = 4.dp), style = MetchuType.Caption)
    }
    dishesMeFirst(room, pick).forEach { (dish, member) -> MemberDish(room, pick, dish, member, "dish_${member.id}", 20.dp) }
    if (pick.others.isNotEmpty()) {
        Text(stringResource(R.string.group_other_dishes), Modifier.padding(start = 20.dp, end = 20.dp, top = 20.dp, bottom = 4.dp), style = MetchuType.Caption)
        pick.others.forEach { dish ->
            Row(
                Modifier.fillMaxWidth().heightIn(min = 56.dp).padding(horizontal = 20.dp).testTag("other_${dish.foodId}"),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Text(dish.displayName, Modifier.weight(1f), style = MetchuType.Button, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(priceText(dish.price), style = MetchuType.Label)
            }
        }
    }
}

/** Each member's dish at [pick] with the member, this phone's member first. */
internal fun dishesMeFirst(room: RoomState, pick: RoomPick): List<Pair<RoomDish, RoomMember>> {
    val byId = room.members.associateBy { it.id }
    return pick.menus.sortedBy { if (it.memberId == room.me) -1 else it.memberId }
        .mapNotNull { dish -> byId[dish.memberId]?.let { dish to it } }
}

/** One member's dish at [pick]: who, their allergies, the price there and how well it fits them. */
@Composable
internal fun MemberDish(room: RoomState, pick: RoomPick, dish: RoomDish, member: RoomMember, tag: String, inset: Dp) {
    val mine = member.id == room.me
    Row(
        Modifier.fillMaxWidth().heightIn(min = 68.dp).padding(horizontal = inset, vertical = 10.dp).testTag(tag),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        Avatar(member, 40.dp, ring = MetchuColors.Primary.takeIf { mine })
        Column(Modifier.weight(1f)) {
            Text(dish.food.displayName, style = MetchuType.Button, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val who = if (mine) "${stringResource(R.string.group_me)} · ${member.name}" else member.name
            Text(
                if (member.allergies.isEmpty()) who else "$who · ${allergyText(member)}",
                style = MetchuType.Caption, maxLines = 1, overflow = TextOverflow.Ellipsis
            )
        }
        val price = dish.food.offers.firstOrNull { it.restaurant == pick.restaurant && it.lat == pick.lat && it.lng == pick.lng }?.price
        Column(horizontalAlignment = Alignment.End) {
            Text(priceText(price), style = MetchuType.Label)
            val great = dish.fit == RoomDish.GREAT
            Text(
                stringResource(if (great) R.string.group_fit_great else R.string.group_fit_good),
                style = MetchuType.Caption, color = if (great) MetchuColors.Primary else MetchuColors.Grey600
            )
        }
    }
}

/** "350 m · 5 min walk". */
@Composable
internal fun walkLine(meters: Int): String {
    val minutes = ceil(meters / WALK_METERS_PER_MINUTE).toInt().coerceAtLeast(1)
    return "${distanceText(meters)} · ${stringResource(R.string.walk_minutes, minutes)}"
}

/** A round thumb that is orange while this member agrees, over "Agree n". It takes taps 48 dp wide. */
@Composable
private fun AgreeButton(pick: RoomPick, enabled: Boolean, onToggle: () -> Unit) {
    val action = stringResource(R.string.group_agree_action)
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Box(
            Modifier
                .size(48.dp)
                .clip(CircleShape)
                .toggleable(pick.voted, enabled = enabled, role = Role.Checkbox) { onToggle() }
                .semantics { contentDescription = action }
                .testTag("agree"),
            contentAlignment = Alignment.Center
        ) {
            Box(
                Modifier.size(44.dp).clip(CircleShape).background(if (pick.voted) MetchuColors.Primary else MetchuColors.Grey100),
                contentAlignment = Alignment.Center
            ) {
                Image(Icons.ThumbUp, null, Modifier.size(20.dp), colorFilter = ColorFilter.tint(if (pick.voted) Color.White else MetchuColors.Grey900))
            }
        }
        Text(
            stringResource(R.string.group_agree, pick.votes),
            Modifier.testTag("agree_count"),
            style = MetchuType.Caption.copy(fontWeight = FontWeight.SemiBold),
            color = if (pick.voted) MetchuColors.Primary else MetchuColors.Grey700,
            maxLines = 1
        )
    }
}

@Composable
private fun PopularBadge(modifier: Modifier = Modifier) {
    Text(
        stringResource(R.string.group_popular),
        modifier.heightIn(min = 18.dp).clip(CircleShape).background(MetchuColors.Primary).padding(horizontal = 6.dp),
        style = MetchuType.Caption.copy(fontSize = 11.sp, lineHeight = 18.sp, fontWeight = FontWeight.Bold),
        color = Color.White,
        maxLines = 1
    )
}

/** A pill at the bottom; [onClick], when given, makes it a button. */
@Composable
private fun StatusPill(text: String, dark: Boolean, modifier: Modifier = Modifier, onClick: (() -> Unit)? = null) {
    Row(
        modifier.height(48.dp).clip(CircleShape)
            .then(if (onClick != null) Modifier.clickable(role = Role.Button, onClick = onClick) else Modifier)
            .background(if (dark) MetchuColors.Grey900 else MetchuColors.Grey100).padding(horizontal = 20.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        if (dark) Image(Icons.Pin, null, Modifier.size(18.dp), colorFilter = ColorFilter.tint(MetchuColors.Primary))
        else Spinner(MetchuColors.Grey700, 16.dp)
        Text(text, style = MetchuType.Label, color = if (dark) Color.White else MetchuColors.Grey700, maxLines = 1)
    }
}

/** The restaurants with their name pills, framed above the sheet again when they change; the one viewed is orange. */
@Composable
private fun PicksMap(picks: List<RoomPick>, selected: Int, sheetHeight: Dp, onSelect: (Int) -> Unit) {
    val points = picks.mapIndexedNotNull { i, p -> if (p.lat != null && p.lng != null) i to LatLng(p.lat, p.lng) else null }
    if (points.isEmpty()) return
    val camera = rememberCameraPositionState { position = CameraPosition.fromLatLngZoom(points.first().second, 16f) }
    var loaded by remember { mutableStateOf(false) }
    val density = LocalDensity.current
    LaunchedEffect(loaded, points) {
        if (!loaded) return@LaunchedEffect
        val update = if (points.size == 1) CameraUpdateFactory.newLatLngZoom(points.single().second, 16f)
            else CameraUpdateFactory.newLatLngBounds(LatLngBounds.builder().apply { points.forEach { include(it.second) } }.build(), with(density) { 64.dp.roundToPx() })
        camera.animate(update, 600)
    }
    GoogleMap(
        modifier = Modifier.fillMaxSize().testTag("map"),
        cameraPositionState = camera,
        contentPadding = PaddingValues(start = 14.dp, top = 120.dp, bottom = sheetHeight + 56.dp),
        uiSettings = MapUiSettings(mapToolbarEnabled = false, myLocationButtonEnabled = false, zoomControlsEnabled = false),
        onMapLoaded = { loaded = true }
    ) {
        points.forEach { (index, point) ->
            val on = index == selected
            key(index, point) {
                MarkerComposable(
                    index, on, picks[index].restaurant,
                    state = remember { MarkerState(point) },
                    anchor = Offset(0.5f, 0.93f),
                    zIndex = if (on) 1f else 0f,
                    onClick = { onSelect(index); true }
                ) { MapPin(placeName(picks[index].restaurant), on) }
            }
        }
    }
}

/** Room around the chips inside their row, so the popular tag over a chip's corner is not cut off. */
private val ChipInset = 10.dp

/**
 * The chips of the picks in [order], in a row that scrolls sideways: the name, how many agree
 * (hidden at none) and the popular tag. New picks scroll the row back to its start.
 */
@Composable
private fun PickChips(picks: List<RoomPick>, order: List<Int>, viewing: Int, popular: Set<Int>, modifier: Modifier, onView: (Int) -> Unit) {
    val row = rememberLazyListState()
    LaunchedEffect(picks.size) { row.animateScrollToItem(0) }
    LazyRow(
        modifier.testTag("pickChips"),
        state = row,
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = ChipInset),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        items(order, key = { it }) { index ->
            val p = picks[index]
            val on = index == viewing
            Box {
                Row(
                    Modifier
                        .height(40.dp)
                        .widthIn(max = 240.dp)
                        .chipShadow()
                        .clip(CircleShape)
                        .background(if (on) MetchuColors.Grey900 else Color.White)
                        .clickable(role = Role.Tab) { onView(index) }
                        .padding(horizontal = 16.dp)
                        .testTag("pick_$index"),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Text(
                        placeName(p.restaurant),
                        Modifier.weight(1f, fill = false),
                        style = MetchuType.Label,
                        color = if (on) Color.White else MetchuColors.Grey900,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    if (p.votes > 0) {
                        val agree = stringResource(R.string.group_agree, p.votes)
                        Row(
                            Modifier.testTag("chipVotes_$index").clearAndSetSemantics { contentDescription = agree },
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(2.dp)
                        ) {
                            Image(Icons.ThumbUp, null, Modifier.size(14.dp), colorFilter = ColorFilter.tint(MetchuColors.Primary))
                            Text("${p.votes}", style = MetchuType.Label, color = MetchuColors.Primary, maxLines = 1)
                        }
                    }
                }
                if (index in popular) PopularBadge(Modifier.offset(x = (-6).dp, y = (-9).dp).testTag("popular_$index"))
            }
        }
    }
}

/** The chips' order: the newest find first, each find as the server listed it. Votes never move a chip. */
internal fun chipOrder(picks: List<RoomPick>): List<Int> =
    picks.indices.sortedWith(compareByDescending<Int> { picks[it].batch }.thenBy { it })

/** The first restaurant of the newest find, which every phone shows when a find adds restaurants. */
internal fun newestFirst(picks: List<RoomPick>): Int = chipOrder(picks).firstOrNull() ?: 0

/** The positions of the picks with the most votes, all of them on a tie; none while fewer than two
 *  picks are open or nobody has voted. */
internal fun popularPicks(room: RoomState): Set<Int> {
    val picks = room.picks.orEmpty()
    val top = picks.maxOfOrNull { it.votes } ?: 0
    if (room.decided != null || picks.size < 2 || top == 0) return emptySet()
    return picks.indices.filter { picks[it].votes == top }.toSet()
}

/** "자하연식당>2층" reads "자하연식당 2층"; two floors of one building stay apart. */
internal fun placeName(restaurant: String): String = restaurant.replace('>', ' ')
