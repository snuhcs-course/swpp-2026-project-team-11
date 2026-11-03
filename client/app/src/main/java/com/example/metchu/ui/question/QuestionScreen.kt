package com.example.metchu.ui.question

import androidx.annotation.StringRes
import android.os.Build
import android.view.HapticFeedbackConstants
import androidx.compose.animation.core.Animatable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.IntOffset
import com.example.metchu.ui.common.cssShadow
import kotlin.math.abs
import kotlin.math.roundToInt
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
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
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.BlurredEdgeTreatment
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.example.metchu.R
import com.example.metchu.data.model.AnswerId
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.model.Step
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.ActionCapsule
import com.example.metchu.ui.common.TopRow
import com.example.metchu.ui.common.SheetEasing
import com.example.metchu.ui.common.Spinner
import com.example.metchu.ui.common.fadeEdges
import com.example.metchu.ui.common.rememberSlow
import com.example.metchu.ui.main.AnsweredQuestion
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import com.example.metchu.ui.theme.screenBackground
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** The answer line under the current question: 12 dp gap and one 39 dp line. */
private val AnswerLineHeight = 51.dp

/** The width of the prototype's answer row: 353 plus 2.5 on each side. */
private val ScaleRowWidth = 358.dp

/** How long the answer takes to fade before the next question comes in. */
private const val ANSWER_FADE_MILLIS = 250L

/** How long a picked answer stays before it is sent and the next question can appear. */
private const val ANSWER_HOLD_MILLIS = 450L

/** One circle of the five-step scale, left (no) to right (yes). [ink] colors its texts. */
private class Level(val id: String, val size: Dp, val color: Color, @StringRes val label: Int, val icon: ImageVector?, val ink: Color = color)

private val Levels = listOf(
    Level(AnswerId.NO, 70.dp, MetchuColors.Grey800, R.string.level_no, Icons.Cross),
    Level(AnswerId.PROBABLY_NO, 58.dp, MetchuColors.Grey800, R.string.level_probably_no, null),
    Level(AnswerId.ANY, 58.dp, MetchuColors.Grey400, R.string.level_any, null, ink = MetchuColors.Grey600),
    Level(AnswerId.PROBABLY_YES, 58.dp, MetchuColors.Primary, R.string.level_probably_yes, null),
    Level(AnswerId.YES, 70.dp, MetchuColors.Primary, R.string.level_yes, Icons.Check)
)

/** The color a past question keeps: the color of its answer. */
fun answerColor(answerId: String): Color = Levels.firstOrNull { it.id == answerId }?.ink ?: MetchuColors.Grey600

@StringRes
private fun answerLabel(answerId: String): Int =
    Levels.firstOrNull { it.id == answerId }?.label ?: R.string.answer_unknown

/**
 * The current question at the bottom of a list of past ones, the scale below it and
 * a progress bar. Past questions fade, blur and keep their answer's color; tapping one
 * goes back to it. Pressing a circle previews its answer under the question.
 */
@Composable
fun QuestionScreen(
    session: SessionState,
    history: List<AnsweredQuestion>,
    loading: Boolean,
    onAnswer: (String, Step) -> Unit,
    onBack: () -> Unit,
    onRecommendNow: () -> Unit,
    onHome: () -> Unit,
    onRevisit: (Int) -> Unit
) {
    val step = session.step
    val count = step.questionCount
    val offered = step.options.orEmpty().map { it.id }.toSet()
    // What the user is pressing or has picked on this question; the answer line shows it.
    var pressing by remember(step.questionId, count) { mutableStateOf<String?>(null) }
    var chosen by remember(step.questionId, count) { mutableStateOf<String?>(null) }
    var lastShown by remember(step.questionId, count) { mutableStateOf<String?>(null) }
    LaunchedEffect(loading) { if (!loading) chosen = null }
    val active = chosen ?: pressing
    if (active != null) lastShown = active

    // Scrolled from the bottom: 0 shows the current question, and new content keeps it in view.
    val list = rememberScrollState()
    val scope = rememberCoroutineScope()
    // After an answer the old line fades first; only then does the new question take its place.
    var settled by remember { mutableIntStateOf(count) }
    LaunchedEffect(count) {
        if (count == settled + 1) delay(ANSWER_FADE_MILLIS)
        settled = count
        list.animateScrollTo(0)
    }
    // The picked answer stays on screen a moment before the next question replaces it. It
    // names the question it answers, so it is dropped if Back moved the session meanwhile.
    val pick = { id: String ->
        if (!loading && chosen == null) {
            chosen = id
            scope.launch {
                delay(ANSWER_HOLD_MILLIS)
                onAnswer(id, step)
            }
        }
    }
    val press = { id: String? ->
        pressing = id
        if (id != null) scope.launch { list.animateScrollTo(0) }
    }

    Box(Modifier.fillMaxSize().screenBackground()) {
        Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
            // Back on the left, home far from it on the right, where a slip is least likely.
            TopRow {
                CircleIconButton(Icons.Back, stringResource(R.string.back), onBack, Modifier.testTag("back"))
                CircleIconButton(Icons.Home, stringResource(R.string.result_home), onHome, Modifier.testTag("home"))
            }

            Column(
                Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .fadeEdges(top = list.canScrollForward, bottom = list.canScrollBackward)
                    .verticalScroll(list, reverseScrolling = true)
                    .padding(start = 10.dp, end = 10.dp, top = 4.dp, bottom = 8.dp)
            ) {
                // One call site for current and past questions, keyed by position, so a question
                // keeps its state (and animates) when it moves from current to past.
                for (index in 0..count) {
                    val current = index == count
                    val past = history.getOrNull(index)
                    if (!current && past == null) continue
                    key(index) {
                        AnimatedVisibility(
                            visible = !current || settled == count,
                            enter = fadeIn(tween(300)) + expandVertically(tween(300, easing = SheetEasing), expandFrom = Alignment.Top)
                        ) {
                            QuestionItem(
                                text = if (current) step.text else past!!.text,
                                current = current,
                                color = if (current) MetchuColors.Grey900 else answerColor(past!!.answerId),
                                answer = if (current) lastShown else past!!.answerId,
                                answerVisible = current && active != null,
                                // The question just answered keeps its line until the next one comes in.
                                answerOpen = current || index >= settled,
                                onRevisit = if (current) null else ({ if (!loading) onRevisit(index) })
                            )
                        }
                    }
                }
            }

            // A new question starts with a fresh slider.
            key(step.questionId, count) { AnswerScale(offered, loading, pick, press) }
            ProgressBlock(session, loading)
        }
        // Answering is the main thing here, so "Recommend now" is the quieter white capsule,
        // and only once there is an answer to recommend from.
        AnimatedVisibility(
            visible = count > 0,
            modifier = Modifier.align(Alignment.BottomEnd).navigationBarsPadding().padding(end = 20.dp, bottom = 16.dp),
            enter = fadeIn(tween(300)),
            exit = fadeOut(tween(200))
        ) {
            ActionCapsule(
                stringResource(R.string.recommend_now), Icons.FastForward, { if (!loading) onRecommendNow() },
                filled = false, modifier = Modifier.testTag("recommendNow")
            )
        }
    }
}

@Composable
private fun QuestionItem(
    text: String,
    current: Boolean,
    color: Color,
    answer: String?,
    answerVisible: Boolean,
    answerOpen: Boolean,
    onRevisit: (() -> Unit)?,
    modifier: Modifier = Modifier
) {
    // A past question lights up while pressed, then the screen goes back to it.
    var held by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val lit = held || (!current && onRevisit != null && pressed)
    val alpha by animateFloatAsState(if (current || lit) 1f else 0.35f, tween(300), label = "alpha")
    val blur by animateDpAsState(if (current || lit) 0.dp else 2.dp, tween(300), label = "blur")
    val ink by animateColorAsState(color, tween(300), label = "ink")
    val background by animateColorAsState(if (lit) MetchuColors.Grey100 else Color.Transparent, tween(if (lit) 150 else 0), label = "bg")
    val scale by animateFloatAsState(if (lit) 353f / 373f else 1f, tween(150), label = "scale")
    val revisit = stringResource(R.string.revisit)

    Column(
        modifier
            .fillMaxWidth()
            .scale(scale)
            .clip(RoundedCornerShape(12.dp))
            .background(background)
            .then(
                if (onRevisit != null) Modifier.clickable(interaction, indication = null, onClickLabel = revisit, role = Role.Button) {
                    held = true
                    scope.launch {
                        delay(220)
                        held = false
                        onRevisit()
                    }
                } else Modifier
            )
            .padding(horizontal = 10.dp, vertical = 6.dp)
            .alpha(alpha)
            .blur(blur, BlurredEdgeTreatment.Unbounded)
    ) {
        Text(text, style = MetchuType.Title, color = ink, modifier = if (current) Modifier.testTag("question") else Modifier)
        // The answer line: its text fades first; the empty line closes as the next question opens.
        val shown by animateFloatAsState(if (answerVisible) 1f else 0f, tween(ANSWER_FADE_MILLIS.toInt()), label = "answer")
        AnimatedVisibility(
            visible = answerOpen,
            enter = expandVertically(tween(300, easing = SheetEasing), expandFrom = Alignment.Top),
            exit = shrinkVertically(tween(300, easing = SheetEasing), shrinkTowards = Alignment.Top)
        ) {
            Box(Modifier.fillMaxWidth().height(AnswerLineHeight)) {
                Box(Modifier.padding(top = 12.dp).fillMaxWidth().height(39.dp).alpha(shown)) {
                    Box(Modifier.offset(y = 19.dp).width(22.dp).height(1.5.dp).background(MetchuColors.Grey300))
                    if (answer != null) {
                        Text(
                            stringResource(answerLabel(answer)),
                            Modifier.padding(start = 32.dp).semantics { liveRegion = LiveRegionMode.Polite },
                            style = MetchuType.Title,
                            color = answerColor(answer),
                            maxLines = 1
                        )
                    }
                }
            }
        }
    }
}

/** "I'm not sure", the five circles and their three captions. */
@Composable
private fun AnswerScale(offered: Set<String>, loading: Boolean, onPick: (String) -> Unit, onPress: (String?) -> Unit) {
    // The prototype's row is 358 wide (353 + 2.5 on each side) on a 393 screen; circles,
    // icons and captions scale with the row so narrower phones keep the same gaps.
    BoxWithConstraints(Modifier.fillMaxWidth().padding(start = 17.5.dp, end = 17.5.dp, bottom = 20.dp)) {
        val scale = (maxWidth / ScaleRowWidth).coerceAtMost(1.15f)
        Column(Modifier.fillMaxWidth()) {
            val unsure = stringResource(R.string.answer_unknown)
            Box(Modifier.fillMaxWidth().height(32.dp).offset(y = 10.dp), contentAlignment = Alignment.Center) {
                if (AnswerId.UNKNOWN in offered) {
                    Text(
                        unsure,
                        Modifier
                            .heightIn(min = 32.dp)
                            .pressPreview(AnswerId.UNKNOWN, loading, onPick, onPress)
                            .semantics { role = Role.Button; contentDescription = unsure; onClick { onPick(AnswerId.UNKNOWN); true } }
                            .padding(horizontal = 12.dp, vertical = 6.dp)
                            .testTag("answer_${AnswerId.UNKNOWN}"),
                        style = MetchuType.Caption.copy(textDecoration = TextDecoration.Underline),
                        color = MetchuColors.Grey600
                    )
                }
            }
            Spacer(Modifier.height(4.dp))
            AnswerSlider(offered, scale, loading, onPick, onPress)
            Spacer(Modifier.height(4.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Caption(R.string.answer_no, MetchuColors.Grey800, scale)
                // Twice as wide, so "Doesn't matter" is not cut off; the outer captions keep it centered.
                Caption(R.string.answer_any, MetchuColors.Grey600, scale, width = 140.dp)
                Caption(R.string.answer_yes, MetchuColors.Primary, scale)
            }
        }
    }
}

@Composable
private fun Caption(@StringRes text: Int, color: Color, scale: Float, width: Dp = 70.dp) {
    Text(stringResource(text), Modifier.width(width * scale), style = MetchuType.Label, color = color, textAlign = TextAlign.Center, maxLines = 1, softWrap = false)
}

/**
 * Shows the answer while held, picks it on release. The gesture outlives a question when
 * `loading` never shows as true (a reply within a frame), so it reads the current callbacks.
 */
@Composable
private fun Modifier.pressPreview(id: String, loading: Boolean, onPick: (String) -> Unit, onPress: (String?) -> Unit): Modifier {
    val pick by rememberUpdatedState(onPick)
    val press by rememberUpdatedState(onPress)
    return pointerInput(id, loading) {
        if (loading) return@pointerInput
        detectTapGestures(
            onPress = {
                press(id)
                tryAwaitRelease()
                press(null)
            },
            onTap = { pick(id) }
        )
    }
}

/** How the handle moves between answers: quick, easing out, no overshoot. */
private val HandleMotion = tween<Float>(260, easing = SheetEasing)

/** Letting go this far above or below the row picks nothing. */
private val CancelDistance = 60.dp

/**
 * The five answers as one slider. Touching the row brings a colored handle out of the
 * middle circle to the answer under the finger; it follows the finger from answer to answer
 * with a tick, and letting go picks where it is, with a firmer tap. Letting go far off the
 * row picks nothing. The three middle circles shrink to dots meanwhile. Each circle stays a
 * button for TalkBack and keyboards.
 */
@Composable
private fun AnswerSlider(offered: Set<String>, scale: Float, loading: Boolean, onPick: (String) -> Unit, onPress: (String?) -> Unit) {
    val density = LocalDensity.current
    val view = LocalView.current
    val scope = rememberCoroutineScope()
    val pick by rememberUpdatedState(onPick)
    val press by rememberUpdatedState(onPress)
    var handleOn by remember { mutableStateOf(false) }
    var under by remember { mutableStateOf<Int?>(null) }
    var shown by remember { mutableIntStateOf(Levels.indexOfFirst { it.id == AnswerId.ANY }) }
    var picked by remember { mutableStateOf(false) }
    val x = remember { Animatable(0f) }
    val diameter = remember { Animatable(0f) }
    val allowed = Levels.indices.filter { Levels[it].id in offered }

    BoxWithConstraints(Modifier.fillMaxWidth().height(76.dp)) {
        val sizes = Levels.map { with(density) { (it.size * scale).toPx() } }
        val centers = scaleCenters(constraints.maxWidth.toFloat(), sizes)
        val middle = Levels.indexOfFirst { it.id == AnswerId.ANY }
        val moveTo = { index: Int ->
            shown = index
            scope.launch { x.animateTo(centers[index], HandleMotion) }
            scope.launch { diameter.animateTo(sizes[index], HandleMotion) }
        }
        val bringOut = { index: Int ->
            handleOn = true
            scope.launch { x.snapTo(centers[middle]); diameter.snapTo(sizes[middle]); moveTo(index) }
        }
        val commit = { index: Int ->
            picked = true
            view.performHapticFeedback(if (Build.VERSION.SDK_INT >= 30) HapticFeedbackConstants.CONFIRM else HapticFeedbackConstants.VIRTUAL_KEY)
            pick(Levels[index].id)
        }

        // The track, behind the circles.
        Box(
            Modifier.fillMaxSize().drawBehind {
                val y = size.height / 2
                drawLine(MetchuColors.Grey300, Offset(centers.first(), y), Offset(centers.last(), y), 1.5.dp.toPx())
            }
        )
        Row(
            Modifier
                .fillMaxSize()
                .pointerInput(loading, picked, centers, allowed) {
                    if (loading || picked) return@pointerInput
                    awaitEachGesture {
                        val down = awaitFirstDown()
                        val first = nearestLevel(down.position.x, centers, allowed) ?: return@awaitEachGesture
                        under = first
                        bringOut(first)
                        press(Levels[first].id)
                        view.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
                        val limit = CancelDistance.toPx()
                        while (true) {
                            val change = awaitPointerEvent().changes.firstOrNull { it.id == down.id } ?: break
                            if (!change.pressed) break
                            change.consume()
                            val next = if (abs(change.position.y - size.height / 2) > limit) null
                                else nearestLevel(change.position.x, centers, allowed)
                            if (next != under) {
                                if (next != null) {
                                    moveTo(next)
                                    view.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
                                }
                                under = next
                                press(next?.let { Levels[it].id })
                            }
                        }
                        val last = under
                        if (last != null) commit(last) else { handleOn = false; press(null) }
                    }
                },
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Levels.forEachIndexed { index, level ->
                val end = index == 0 || index == Levels.lastIndex
                ScaleCircle(level, scale, enabled = level.id in offered, dot = handleOn && !end) {
                    if (!loading && !picked) { bringOut(index); commit(index) }
                }
            }
        }
        if (handleOn) Handle(Levels[shown], x.value, diameter.value, faded = under == null, scale)
    }
}

/** One answer at rest: a white circle with a light ring, or a 10 dp dot while the handle is out. */
@Composable
private fun ScaleCircle(level: Level, rowScale: Float, enabled: Boolean, dot: Boolean, onPick: () -> Unit) {
    val slot = level.size * rowScale
    val size by animateDpAsState(if (dot) 10.dp else slot, tween(220, easing = SheetEasing), label = "dot")
    val description = stringResource(level.label)
    Box(
        Modifier
            .size(slot)
            .alpha(if (enabled) 1f else 0.3f)
            .semantics {
                role = Role.Button
                contentDescription = description
                if (enabled) onClick { onPick(); true }
            }
            .testTag("answer_${level.id}"),
        contentAlignment = Alignment.Center
    ) {
        Box(
            Modifier.size(size).clip(CircleShape).background(Color.White).drawBehind {
                val width = 1.5.dp.toPx()
                drawCircle(MetchuColors.Grey300, radius = (this.size.minDimension - width) / 2, style = Stroke(width))
            },
            contentAlignment = Alignment.Center
        ) {
            if (level.icon != null && !dot) {
                Image(level.icon, null, Modifier.size(iconSize(level) * rowScale), colorFilter = ColorFilter.tint(MetchuColors.Grey300))
            }
        }
    }
}

/** The colored circle that marks the answer: the only thing in the row with a shadow. */
@Composable
private fun Handle(level: Level, x: Float, diameter: Float, faded: Boolean, rowScale: Float) {
    val color by animateColorAsState(level.color, tween(160), label = "handle")
    val alpha by animateFloatAsState(if (faded) 0.35f else 1f, tween(160), label = "handleAlpha")
    val icon = when (level.id) {
        AnswerId.YES, AnswerId.PROBABLY_YES -> Icons.Check
        AnswerId.NO, AnswerId.PROBABLY_NO -> Icons.Cross
        else -> null
    }
    val size = with(LocalDensity.current) { diameter.toDp() }
    Box(
        Modifier
            .offset { IntOffset((x - diameter / 2).roundToInt(), 0) }
            .fillMaxHeight()
            .width(size),
        contentAlignment = Alignment.Center
    ) {
        Box(
            Modifier
                .size(size)
                .alpha(alpha)
                .cssShadow(CircleShape, 6.dp, 18.dp, 0.3f)
                .clip(CircleShape)
                .background(color),
            contentAlignment = Alignment.Center
        ) {
            if (icon != null) Image(icon, null, Modifier.size(iconSize(level) * rowScale), colorFilter = ColorFilter.tint(Color.White))
        }
    }
}

/** The outer answers carry a full icon; the "a little" ones a smaller one on the handle. */
private fun iconSize(level: Level): Dp = when (level.id) {
    AnswerId.YES -> 28.dp
    AnswerId.NO -> 26.dp
    else -> 20.dp
}

/**
 * The grey bar and the phase under it; it fills fast at first and slower later. A spinner
 * at the end of the phase line shows that the next step is on its way.
 */
@Composable
private fun ProgressBlock(session: SessionState, loading: Boolean) {
    val fill = progressFill(session.step.questionCount, session.maxQuestions)
    val width by animateFloatAsState(fill, tween(450, easing = SheetEasing), label = "progress")
    val label = stringResource(R.string.progress)
    Column(Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, bottom = 90.dp)) {
        Box(
            Modifier
                .fillMaxWidth()
                .height(6.dp)
                .clip(CircleShape)
                .background(MetchuColors.Grey300)
                .semantics {
                    contentDescription = label
                    progressBarRangeInfo = ProgressBarRangeInfo(fill, 0f..1f)
                }
        ) {
            Box(Modifier.fillMaxHeight().fillMaxWidth(width).background(MetchuColors.Grey400))
        }
        Spacer(Modifier.height(6.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                stringResource(phaseText(fill)),
                Modifier.weight(1f).semantics { liveRegion = LiveRegionMode.Polite }.testTag("phase"),
                style = MetchuType.Caption
            )
            if (rememberSlow(loading)) Spinner(MetchuColors.Grey600, 14.dp)
        }
    }
}
