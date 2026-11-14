package com.example.metchu.ui.group

import androidx.compose.foundation.Image
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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
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
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.example.metchu.BuildConfig
import com.example.metchu.R
import com.example.metchu.data.model.RoomDish
import com.example.metchu.data.model.RoomPick
import com.example.metchu.data.model.RoomState
import com.example.metchu.ui.common.ActionCapsule
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.Spinner
import com.example.metchu.ui.common.TopRow
import com.example.metchu.ui.common.chipShadow
import com.example.metchu.ui.common.cssShadow
import com.example.metchu.ui.result.MapPin
import com.example.metchu.ui.result.WALK_METERS_PER_MINUTE
import com.example.metchu.ui.result.captionFor
import com.example.metchu.ui.result.distanceText
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
 * Up to two restaurants, named on chips over the map, and each member's dish at the one
 * chosen, this phone's member first. The host decides with "Go here"; everyone's screen
 * then shows where to meet.
 */
@Composable
fun GroupResultScreen(room: RoomState, busy: Boolean, onDecide: (String) -> Unit, onHome: () -> Unit) {
    val picks = room.picks.orEmpty()
    if (picks.isEmpty()) return
    var viewing by rememberSaveable { mutableStateOf(picks.first().restaurant) }
    room.decided?.let { viewing = it }
    val pick = picks.firstOrNull { it.restaurant == viewing } ?: picks.first()

    BoxWithConstraints(Modifier.fillMaxSize().background(MetchuColors.MapBlank)) {
        val sheetTop = maxHeight * 0.42f
        if (BuildConfig.HAS_MAPS_KEY) PicksMap(picks, pick.restaurant, sheetHeight = maxHeight - sheetTop) { if (room.decided == null) viewing = it }

        TopRow(Modifier.statusBarsPadding(), arrangement = Arrangement.End) {
            CircleIconButton(Icons.Home, stringResource(R.string.result_home), onHome, Modifier.testTag("home"))
        }
        Row(
            Modifier.padding(start = 20.dp, top = sheetTop - 56.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            picks.filter { room.decided == null || it.restaurant == room.decided }.forEach { p ->
                val on = p.restaurant == pick.restaurant
                Text(
                    placeName(p.restaurant),
                    Modifier
                        .height(40.dp)
                        .chipShadow()
                        .clip(CircleShape)
                        .background(if (on) MetchuColors.Grey900 else Color.White)
                        .clickable(role = Role.Tab) { if (room.decided == null) viewing = p.restaurant }
                        .padding(horizontal = 16.dp, vertical = 10.dp)
                        .testTag("pick_${p.restaurant}"),
                    style = MetchuType.Label,
                    color = if (on) Color.White else MetchuColors.Grey900,
                    maxLines = 1
                )
            }
        }

        val shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp)
        Column(
            Modifier
                .padding(top = sheetTop)
                .fillMaxSize()
                .cssShadow(shape, (-2).dp, 12.dp, 0.10f)
                .clip(shape)
                .background(Color.White)
                .verticalScroll(rememberScrollState())
                .padding(top = 20.dp, bottom = 140.dp)
        ) {
            key(pick.restaurant) { PickDetails(room, pick) }
        }

        val bottom = Modifier.align(Alignment.BottomEnd).navigationBarsPadding().padding(end = 20.dp, bottom = 16.dp)
        when {
            room.decided != null -> StatusPill(stringResource(R.string.group_meet, placeName(room.decided)), dark = true, modifier = bottom.testTag("decided"))
            room.isHost -> ActionCapsule(
                stringResource(R.string.group_decide), Icons.Check, { if (!busy) onDecide(pick.restaurant) },
                filled = true, modifier = bottom.testTag("decide")
            )
            else -> StatusPill(stringResource(R.string.group_host_picking), dark = false, modifier = bottom)
        }
    }
}

@Composable
private fun PickDetails(room: RoomState, pick: RoomPick) {
    Column(Modifier.padding(horizontal = 20.dp)) {
        Text(stringResource(captionFor(room.meal)), style = MetchuType.Caption)
        Text(placeName(pick.restaurant), Modifier.padding(top = 2.dp).testTag("restaurant"), style = MetchuType.Title)
        pick.distanceM?.let { meters ->
            val minutes = ceil(meters / WALK_METERS_PER_MINUTE).toInt().coerceAtLeast(1)
            Text(
                "${distanceText(meters)} · ${stringResource(R.string.walk_minutes, minutes)}",
                Modifier.padding(top = 2.dp), style = MetchuType.Body
            )
        }
        Text(stringResource(R.string.group_each_dish), Modifier.padding(top = 20.dp, bottom = 4.dp), style = MetchuType.Caption)
    }
    val byId = room.members.associateBy { it.id }
    pick.menus.sortedBy { if (it.memberId == room.me) -1 else it.memberId }.forEach { dish ->
        val member = byId[dish.memberId] ?: return@forEach
        val mine = member.id == room.me
        Row(
            Modifier.fillMaxWidth().heightIn(min = 68.dp).padding(horizontal = 20.dp, vertical = 10.dp).testTag("dish_${member.id}"),
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
            val price = dish.food.offers.firstOrNull { it.restaurant == pick.restaurant }?.price
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

@Composable
private fun StatusPill(text: String, dark: Boolean, modifier: Modifier = Modifier) {
    Row(
        modifier.height(48.dp).clip(CircleShape).background(if (dark) MetchuColors.Grey900 else MetchuColors.Grey100).padding(horizontal = 20.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        if (dark) Image(Icons.Pin, null, Modifier.size(18.dp), colorFilter = ColorFilter.tint(MetchuColors.Primary))
        else Spinner(MetchuColors.Grey700, 16.dp)
        Text(text, style = MetchuType.Label, color = if (dark) Color.White else MetchuColors.Grey700, maxLines = 1)
    }
}

/** The two restaurants with their name pills, framed above the sheet; the one viewed is orange. */
@Composable
private fun PicksMap(picks: List<RoomPick>, selected: String, sheetHeight: Dp, onSelect: (String) -> Unit) {
    val points = picks.mapNotNull { p -> if (p.lat != null && p.lng != null) p.restaurant to LatLng(p.lat, p.lng) else null }
    if (points.isEmpty()) return
    val camera = rememberCameraPositionState { position = CameraPosition.fromLatLngZoom(points.first().second, 16f) }
    var loaded by remember { mutableStateOf(false) }
    val density = LocalDensity.current
    LaunchedEffect(loaded) {
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
        points.forEach { (restaurant, point) ->
            val on = restaurant == selected
            key(restaurant) {
                MarkerComposable(
                    restaurant, on,
                    state = remember { MarkerState(point) },
                    anchor = Offset(0.5f, 0.93f),
                    zIndex = if (on) 1f else 0f,
                    onClick = { onSelect(restaurant); true }
                ) { MapPin(placeName(restaurant), on) }
            }
        }
    }
}

/** "자하연식당>2층" reads "자하연식당 2층"; two floors of one building stay apart. */
private fun placeName(restaurant: String): String = restaurant.replace('>', ' ')
