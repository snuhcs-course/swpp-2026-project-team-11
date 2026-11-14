package com.example.metchu.ui.group

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.metchu.R
import com.example.metchu.data.model.RoomMember
import com.example.metchu.data.model.RoomState
import com.example.metchu.ui.common.ActionCapsule
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.SheetEasing
import com.example.metchu.ui.common.Spinner
import com.example.metchu.ui.common.TopRow
import com.example.metchu.ui.common.fadeEdges
import com.example.metchu.ui.main.AnsweredQuestion
import com.example.metchu.ui.question.AnswerScale
import com.example.metchu.ui.question.answerColor
import com.example.metchu.ui.question.answerLabel
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import com.example.metchu.ui.theme.screenBackground
import kotlinx.coroutines.delay
import kotlin.math.ceil

/**
 * Everyone's question of this round. The circles across the top show who has answered,
 * never what. An answer is final: after it the scale rests and the screen waits for the
 * others, or for the countdown, after which the server counts silence as "doesn't matter".
 * Only the host can stop early with "Recommend now", once a round is over.
 */
@Composable
fun GroupQuestionScreen(
    room: RoomState,
    history: List<AnsweredQuestion>,
    busy: Boolean,
    onAnswer: (String) -> Unit,
    onRecommendNow: () -> Unit,
    onLeave: () -> Unit
) {
    val question = room.question ?: return
    val present = room.members.filterNot { it.left }
    val me = present.firstOrNull { it.id == room.me }
    val others = present.filter { it.id != room.me }
    val answered = room.myAnswer != null

    Box(Modifier.fillMaxSize().screenBackground()) {
        Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
            TopRow {
                AnsweredRow(listOfNotNull(me) + others)
                CircleIconButton(Icons.Home, stringResource(R.string.group_leave), onLeave, Modifier.testTag("leave"))
            }

            Column(Modifier.weight(1f).fillMaxWidth().padding(horizontal = 20.dp)) {
                val list = rememberScrollState()
                LaunchedEffect(history.size) { list.animateScrollTo(0) }
                Column(
                    Modifier
                        .weight(1f, fill = false)
                        .fadeEdges(top = list.canScrollForward, bottom = false, edge = 32.dp)
                        .verticalScroll(list, reverseScrolling = true)
                        .padding(top = 4.dp)
                ) {
                    history.forEach { PastLine(it) }
                }
                Text(question.text, Modifier.padding(top = 6.dp).testTag("groupQuestion"), style = MetchuType.Title)
                Text(
                    room.myAnswer?.let { stringResource(answerLabel(it)) }.orEmpty(),
                    Modifier.align(Alignment.End).padding(top = 12.dp).height(39.dp).testTag("myAnswer"),
                    style = MetchuType.Title,
                    color = room.myAnswer?.let(::answerColor) ?: MetchuColors.Grey400
                )
                val waiting = others.filterNot { it.answered }
                if (answered && waiting.isNotEmpty()) {
                    Row(
                        Modifier.align(Alignment.End).padding(top = 6.dp).semantics { liveRegion = LiveRegionMode.Polite },
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Spinner(MetchuColors.Grey600, 14.dp)
                        Text(
                            if (waiting.size == 1) stringResource(R.string.group_waiting_one, waiting.single().name)
                            else stringResource(R.string.group_waiting_many, waiting.size),
                            style = MetchuType.Caption
                        )
                    }
                }
            }

            // A new question brings back a scale that can be answered.
            key(question.questionId) {
                AnswerScale(question.options.map { it.id }.toSet(), loading = busy || answered, onPick = onAnswer, onPress = {})
            }
            RoundProgress(room)
        }

        if (room.isHost && room.round > 0) {
            ActionCapsule(
                stringResource(R.string.recommend_now), Icons.FastForward, { if (!busy) onRecommendNow() },
                filled = false,
                modifier = Modifier.align(Alignment.BottomEnd).navigationBarsPadding().padding(end = 20.dp, bottom = 16.dp).testTag("recommendNow")
            )
        }
    }
}

/** This phone's member first, then the others; an orange ring and a check once they have answered. */
@Composable
private fun AnsweredRow(members: List<RoomMember>) {
    val description = stringResource(R.string.group_answered, members.count { it.answered }, members.size)
    Row(Modifier.semantics { contentDescription = description }.testTag("answered")) {
        members.forEachIndexed { i, member ->
            Box(Modifier.offset(x = (-AvatarOverlap * i))) {
                Avatar(member, AvatarSize, Modifier.alpha(if (member.answered) 1f else 0.5f), ring = MetchuColors.Primary.takeIf { member.answered })
                if (member.answered) {
                    Box(
                        Modifier.align(Alignment.BottomEnd).size(16.dp).clip(CircleShape).background(MetchuColors.Primary),
                        contentAlignment = Alignment.Center
                    ) {
                        Image(Icons.check(3.4f), null, Modifier.size(10.dp), colorFilter = ColorFilter.tint(Color.White))
                    }
                }
            }
        }
    }
}

/** Eight circles and the home button fit a 360 dp screen. */
private val AvatarSize = 32.dp
private val AvatarOverlap = 6.dp

@Composable
private fun PastLine(past: AnsweredQuestion) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(
            past.text, Modifier.weight(1f).padding(end = 12.dp),
            style = MetchuType.Label.copy(fontWeight = MetchuType.Body.fontWeight), color = MetchuColors.Grey600,
            maxLines = 1, overflow = TextOverflow.Ellipsis
        )
        Text(stringResource(answerLabel(past.answerId)), style = MetchuType.Label, color = answerColor(past.answerId))
    }
}

/**
 * The rounds so far (the engine may stop before the last one) and the seconds left in
 * this round, counted down on the phone between the server's replies.
 */
@Composable
private fun RoundProgress(room: RoomState) {
    val fill by animateFloatAsState(room.round.toFloat() / room.maxRounds, tween(450, easing = SheetEasing), label = "rounds")
    var left by remember { mutableFloatStateOf(room.secondsLeft?.toFloat() ?: 0f) }
    LaunchedEffect(room.question?.questionId, room.secondsLeft) {
        left = room.secondsLeft?.toFloat() ?: return@LaunchedEffect
        while (left > 0f) {
            delay(TICK_MILLIS)
            left = (left - TICK_MILLIS / 1000f).coerceAtLeast(0f)
        }
    }
    Column(Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, bottom = 90.dp)) {
        Box(Modifier.fillMaxWidth().height(6.dp).clip(CircleShape).background(MetchuColors.Grey300)) {
            Box(Modifier.fillMaxHeight().fillMaxWidth(fill).background(MetchuColors.Grey400))
        }
        Spacer(Modifier.height(6.dp))
        Row {
            Text(stringResource(R.string.group_round, room.round + 1, room.maxRounds), Modifier.weight(1f), style = MetchuType.Caption)
            val seconds = ceil(left).toInt()
            Text(
                stringResource(R.string.group_seconds, seconds),
                Modifier.testTag("secondsLeft"),
                style = MetchuType.Caption,
                color = if (seconds <= URGENT_SECONDS) MetchuColors.Primary else MetchuColors.Grey600,
                textAlign = TextAlign.End
            )
        }
    }
}

private const val TICK_MILLIS = 200L
private const val URGENT_SECONDS = 3
