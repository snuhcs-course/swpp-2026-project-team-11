package com.example.metchu.ui.group

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.example.metchu.R
import com.example.metchu.data.model.RoomMember
import com.example.metchu.data.model.RoomState
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.LabelCapsule
import com.example.metchu.ui.common.NavigationBarFade
import com.example.metchu.ui.common.PinnedTopRow
import com.example.metchu.ui.common.Spinner
import com.example.metchu.ui.common.TopRowHeight
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import com.example.metchu.ui.theme.screenBackground

/**
 * The room's code in large digits with an invite to send, and who is here with their
 * allergies. The host starts once two people are in; everyone else waits for that.
 */
@Composable
fun LobbyScreen(room: RoomState, busy: Boolean, onStart: () -> Unit, onLeave: () -> Unit) {
    val scroll = rememberScrollState()
    val present = room.members.filterNot { it.left }
    val context = LocalContext.current
    val invite = stringResource(R.string.group_share_text, room.code)

    Box(Modifier.fillMaxSize().screenBackground()) {
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(scroll)
                .statusBarsPadding()
                .padding(top = TopRowHeight + 10.dp, bottom = 140.dp)
        ) {
            Column(Modifier.padding(horizontal = 20.dp)) {
                Text(
                    stringResource(if (room.isHost) R.string.group_lobby_title_host else R.string.group_lobby_title_member),
                    style = MetchuType.Title
                )
                Row(Modifier.fillMaxWidth().padding(top = 20.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        room.code,
                        Modifier.weight(1f).testTag("roomCode"),
                        style = MetchuType.Title.copy(fontSize = 44.sp, lineHeight = 52.sp, letterSpacing = 0.16.em)
                    )
                    LabelCapsule(stringResource(R.string.group_share), {
                        val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, invite)
                        context.startActivity(Intent.createChooser(send, null))
                    }, filled = false)
                }
                Text(stringResource(R.string.group_count, present.size), Modifier.padding(top = 28.dp, bottom = 4.dp), style = MetchuType.Caption)
            }
            present.forEach { MemberRow(it, me = it.id == room.me, host = it.id == room.host) }
            if (present.size < MAX_MEMBERS) {
                Row(
                    Modifier.fillMaxWidth().heightIn(min = 64.dp).padding(horizontal = 20.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(14.dp)
                ) {
                    Box(Modifier.padding(horizontal = 12.dp)) { Spinner(MetchuColors.Grey600, 16.dp) }
                    Text(stringResource(R.string.group_waiting_friends), style = MetchuType.Body)
                }
            }
            Text(stringResource(R.string.group_note), Modifier.padding(start = 20.dp, end = 20.dp, top = 8.dp), style = MetchuType.Caption)
        }
        PinnedTopRow(scroll) {
            CircleIconButton(Icons.Back, stringResource(R.string.group_leave), onLeave, Modifier.testTag("leave"))
        }
        NavigationBarFade(Modifier.align(Alignment.BottomCenter))

        val bottom = Modifier.align(Alignment.BottomEnd).navigationBarsPadding().padding(end = 20.dp, bottom = 16.dp)
        if (room.isHost) {
            val ready = present.size >= 2 && !busy
            LabelCapsule(
                if (present.size >= 2) stringResource(R.string.group_start, present.size) else stringResource(R.string.group_need_more),
                onStart, filled = ready, enabled = ready, modifier = bottom.testTag("startRoom")
            )
        } else {
            Row(
                bottom.height(48.dp).clip(CircleShape).background(MetchuColors.Grey100).padding(horizontal = 20.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Spinner(MetchuColors.Grey700, 16.dp)
                Text(stringResource(R.string.group_host_will_start), style = MetchuType.Label, color = MetchuColors.Grey700)
            }
        }
    }
}

@Composable
private fun MemberRow(member: RoomMember, me: Boolean, host: Boolean) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 64.dp).padding(horizontal = 20.dp, vertical = 10.dp).testTag("member_${member.id}"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        Avatar(member, 40.dp)
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(member.name, Modifier.weight(1f, fill = false), style = MetchuType.Button, maxLines = 1, overflow = TextOverflow.Ellipsis)
                val tags = listOfNotNull(stringResource(R.string.group_me).takeIf { me }, stringResource(R.string.group_host).takeIf { host })
                if (tags.isNotEmpty()) {
                    Text(
                        tags.joinToString(" · "),
                        Modifier.clip(CircleShape).background(MetchuColors.Grey100).padding(horizontal = 7.dp, vertical = 2.dp),
                        style = MetchuType.Caption.copy(fontWeight = MetchuType.Label.fontWeight),
                        color = MetchuColors.Grey700
                    )
                }
            }
            Text(allergyText(member), style = MetchuType.Caption)
        }
    }
}

const val MAX_MEMBERS = 8
