package com.example.metchu.ui.group

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import com.example.metchu.R
import com.example.metchu.data.model.RoomPick
import com.example.metchu.data.model.RoomState
import com.example.metchu.ui.result.Point
import com.example.metchu.ui.result.openDirections
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType

/**
 * Where the group meets, on every phone once the host decides: the restaurant and each
 * member's dish there, this phone's member first. "Start over" leaves the room.
 */
@Composable
fun DecidedDialog(room: RoomState, pick: RoomPick, onClose: () -> Unit, onHome: () -> Unit) {
    val context = LocalContext.current
    val name = placeName(pick.restaurant)
    Dialog(onDismissRequest = onClose) {
        Column(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(20.dp))
                .background(Color.White)
                .padding(top = 24.dp, bottom = 12.dp)
                .testTag("decidedDialog")
        ) {
            Column(Modifier.padding(horizontal = 24.dp)) {
                Text(stringResource(R.string.group_decided_title), style = MetchuType.Caption)
                Text(name, Modifier.padding(top = 2.dp).testTag("decidedRestaurant"), style = MetchuType.Item)
            }
            // Eight members fit by scrolling; the buttons stay below.
            Column(Modifier.padding(top = 8.dp).heightIn(max = 288.dp).verticalScroll(rememberScrollState())) {
                dishesMeFirst(room, pick).forEach { (dish, member) ->
                    MemberDish(room, pick, dish, member, "decidedDish_${member.id}", 24.dp)
                }
            }
            Row(Modifier.fillMaxWidth().padding(start = 12.dp, end = 12.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                TextButton(onHome, Modifier.testTag("decidedHome")) {
                    Text(stringResource(R.string.result_home), style = MetchuType.Button, color = MetchuColors.Grey600)
                }
                Spacer(Modifier.weight(1f))
                if (pick.lat != null && pick.lng != null) {
                    TextButton({ context.openDirections(name, Point(pick.lat, pick.lng)) }, Modifier.testTag("decidedDirections")) {
                        Text(stringResource(R.string.group_decided_directions), style = MetchuType.Button, color = MetchuColors.Primary)
                    }
                }
                TextButton(onClose, Modifier.testTag("decidedOk")) {
                    Text(stringResource(R.string.group_decided_ok), style = MetchuType.Button, color = MetchuColors.Primary)
                }
            }
        }
    }
}
