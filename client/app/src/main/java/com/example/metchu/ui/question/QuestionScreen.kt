package com.example.metchu.ui.question

import androidx.annotation.StringRes
import android.os.Build
import android.view.HapticFeedbackConstants
import androidx.compose.animation.core.Animatable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.layout.layout
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.lerp
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Paint
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.lerp
import androidx.compose.runtime.SideEffect
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
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
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
import androidx.compose.ui.draw.alpha
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

/** The width of the prototype's answer row: 353 plus 2.5 on each side. */
private val ScaleRowWidth = 358.dp

/** How long a picked answer stays before it is sent and the next question can appear. */
private const val ANSWER_HOLD_MILLIS = 450L

/** One circle of the five-step scale, left (no) to right (yes). [ink] colors its texts. */
private class Level(val id: String, val size: Dp, val color: Color, @StringRes val label: Int, val icon: ImageVector?, val ink: Color = color)

private val Levels = listOf(
    Level(AnswerId.NO, 70.dp, MetchuColors.Grey800, R.string.level_no, Icons.Cross),
    Level(AnswerId.PROBABLY_NO, 58.dp, MetchuColors.Grey800, R.string.level_probably_no, null),
    // "Doesn't matter" keeps the circle's light grey in its caption, its answer line and the list.
    Level(AnswerId.ANY, 58.dp, MetchuColors.Grey400, R.string.level_any, null),
    Level(AnswerId.PROBABLY_YES, 58.dp, MetchuColors.Primary, R.string.level_probably_yes, null),
    Level(AnswerId.YES, 70.dp, MetchuColors.Primary, R.string.level_yes, Icons.Check)
)

/** The color a past question keeps: the color of its answer. */
fun answerColor(answerId: String): Color = Levels.firstOrNull { it.id == answerId }?.ink ?: MetchuColors.Grey400

@StringRes
private fun answerLabel(answerId: String): Int =
    Levels.firstOrNull { it.id == answerId }?.label ?: R.string.answer_unknown

/**
 * The current question under a list of past ones, the scale below it and a progress bar.
 * Past questions are one grey line each with their answer on the right; only they scroll,
 * the current question stays put. Tapping a past one goes back to it. Pressing a circle
 * shows its answer under the question; once picked, question and answer shrink into the
 * line they will have in the list.
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
    // Going back (Back or a tapped past question), the question returned to grows out of its
    // past line and lets go of its old answer.
    var before by remember { mutableStateOf(history) }
    val returning = remember(step.questionId, count) {
        before.getOrNull(history.size)?.takeIf { history.size < before.size && it.text == step.text }?.answerId
    }
    SideEffect { before = history }

    // Scrolled from the bottom: 0 shows the newest past question.
    val list = rememberScrollState()
    val scope = rememberCoroutineScope()
    LaunchedEffect(count) { list.animateScrollTo(0) }
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

            Column(Modifier.weight(1f).fillMaxWidth()) {
                // As tall as the past questions need, up to the room there is; it fades only at
                // an edge it can still scroll past.
                Column(
                    Modifier
                        .weight(1f, fill = false)
                        .fillMaxWidth()
                        .fadeEdges(top = list.canScrollForward, bottom = list.canScrollBackward, edge = 32.dp)
                        .verticalScroll(list, reverseScrolling = true)
                        .padding(start = 10.dp, end = 10.dp, top = 4.dp)
                ) {
                    history.forEachIndexed { index, past ->
                        key(index) { PastQuestion(past) { if (!loading) onRevisit(index) } }
                    }
                }
                key(step.questionId, count) {
                    CurrentQuestion(step.text, lastShown, shown = active != null, done = chosen != null, returning = returning)
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

/**
 * An answered question: one grey line, its answer on the right in the answer's color. A long
 * question runs on under the answer and fades out before it. Held, it shows in full and goes
 * back to that question.
 */
@Composable
private fun PastQuestion(past: AnsweredQuestion, onRevisit: () -> Unit) {
    var held by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val lit = held || pressed
    val background by animateColorAsState(if (lit) MetchuColors.Grey100 else Color.White, tween(if (lit) 150 else 0), label = "bg")
    val scale by animateFloatAsState(if (lit) 353f / 373f else 1f, tween(150), label = "scale")
    val revisit = stringResource(R.string.revisit)
    val answer = stringResource(answerLabel(past.answerId))
    Box(
        Modifier
            .fillMaxWidth()
            .scale(scale)
            .clip(RoundedCornerShape(12.dp))
            .background(background)
            .clickable(interaction, indication = null, onClickLabel = revisit, role = Role.Button) {
                held = true
                scope.launch {
                    delay(220)
                    held = false
                    onRevisit()
                }
            }
            .padding(horizontal = 10.dp, vertical = 6.dp)
    ) {
        Text(
            past.text,
            Modifier.fillMaxWidth().padding(end = if (lit) AnswerRoom else 0.dp),
            style = PastStyle,
            color = MetchuColors.Grey600,
            maxLines = if (lit) Int.MAX_VALUE else 1,
            softWrap = lit
        )
        Text(
            answer,
            Modifier.align(Alignment.TopEnd).answerFade(background).padding(start = AnswerRoom),
            style = PastAnswerStyle,
            color = answerColor(past.answerId),
            maxLines = 1
        )
    }
}

/**
 * The question being asked, in large type, with the answer under it on the right while a
 * circle is pressed. [done] (an answer picked) shrinks both, without a fade, into the
 * line the question will have in the list: the answer moves up to the question's line.
 * A question gone back to ([returning] is its old answer) grows out of that line while the
 * old answer fades out where it is.
 */
@Composable
private fun CurrentQuestion(text: String, answer: String?, shown: Boolean, done: Boolean, returning: String?) {
    val back = returning != null
    val appear = remember { Animatable(if (back) 1f else 0f) }
    LaunchedEffect(Unit) { appear.animateTo(1f, tween(300)) }
    val shrinkState = remember { Animatable(if (back) 1f else 0f) }
    LaunchedEffect(done) { shrinkState.animateTo(if (done) 1f else 0f, tween(380, easing = SheetEasing)) }
    val shrink = shrinkState.value
    val answerAlpha by animateFloatAsState(if (shown) 1f else 0f, tween(160), label = "answer")
    // The old answer fades where it stood in the list, on the question's first line.
    val oldAnswer = remember { Animatable(if (back) 1f else 0f) }
    LaunchedEffect(Unit) { oldAnswer.animateTo(0f, tween(250)) }
    val density = LocalDensity.current
    Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp).padding(top = 6.dp).alpha(appear.value)) {
        Box(Modifier.fillMaxWidth()) {
            Text(
                text,
                Modifier.fillMaxWidth().testTag("question"),
                style = lerpStyle(MetchuType.Title, PastStyle, shrink),
                color = lerp(MetchuColors.Grey900, MetchuColors.Grey600, shrink),
                maxLines = if (shrink > 0.5f) 1 else Int.MAX_VALUE,
                softWrap = shrink <= 0.5f
            )
            if (returning != null && oldAnswer.value > 0f) {
                Text(
                    stringResource(answerLabel(returning)),
                    Modifier.align(Alignment.TopEnd).alpha(oldAnswer.value).answerFade(Color.White).padding(start = AnswerRoom),
                    style = PastAnswerStyle,
                    color = answerColor(returning),
                    maxLines = 1
                )
            }
        }
        if (answer != null) {
            // 12 dp under the question at first; at the end it sits on the question's line.
            val gap = lerp(12.dp, -PastLine, shrink)
            Text(
                stringResource(answerLabel(answer)),
                Modifier
                    .align(Alignment.End)
                    .layout { measurable, constraints ->
                        val placeable = measurable.measure(constraints)
                        val dy = with(density) { gap.roundToPx() }
                        layout(placeable.width, (placeable.height + dy).coerceAtLeast(0)) { placeable.place(0, dy) }
                    }
                    .alpha(answerAlpha)
                    .answerBacking(shrink)
                    .padding(start = AnswerRoom * shrink)
                    .semantics { liveRegion = LiveRegionMode.Polite },
                style = lerpStyle(MetchuType.Title, PastAnswerStyle, shrink),
                color = answerColor(answer),
                maxLines = 1
            )
        } else {
            Spacer(Modifier.height(12.dp + 39.dp))
        }
    }
}

/** A past question's line: 15/20, medium. */
private val PastStyle = MetchuType.Label.copy(fontWeight = FontWeight.Medium)
private val PastAnswerStyle = MetchuType.Label
private val PastLine = 20.dp

/** Space before a past answer: a 28 dp fade over the question, then a clear gap. */
private val AnswerRoom = 32.dp

/** The question line fades out under the answer: transparent at the left of [AnswerRoom], [background] after 28 dp. */
private fun Modifier.answerFade(background: Color): Modifier = drawBehind {
    drawRect(Brush.horizontalGradient(listOf(background.copy(alpha = 0f), background), startX = 0f, endX = AnswerFade.toPx()))
}

/**
 * The white behind an answer moving up onto the question's line, appearing as it moves
 * ([alpha]). It reaches [BackingReach] above and below the answer and fades out there, so
 * neither edge cuts through the question on the way.
 */
private fun Modifier.answerBacking(alpha: Float): Modifier = drawBehind {
    if (alpha <= 0f) return@drawBehind
    val reach = BackingReach.toPx()
    val top = -reach
    val height = size.height + 2 * reach
    val area = Size(size.width, height)
    drawContext.canvas.saveLayer(Rect(Offset(0f, top), area), Paint())
    drawRect(
        Brush.horizontalGradient(listOf(Color.White.copy(alpha = 0f), Color.White), startX = 0f, endX = AnswerFade.toPx()),
        topLeft = Offset(0f, top), size = area, alpha = alpha
    )
    val edge = reach / height
    drawRect(
        Brush.verticalGradient(
            0f to Color.Transparent, edge to Color.Black, 1f - edge to Color.Black, 1f to Color.Transparent,
            startY = top, endY = top + height
        ),
        topLeft = Offset(0f, top), size = area, blendMode = BlendMode.DstIn
    )
    drawContext.canvas.restore()
}

private val AnswerFade = 28.dp
private val BackingReach = 24.dp

private fun lerpStyle(from: TextStyle, to: TextStyle, t: Float): TextStyle = from.copy(
    fontSize = lerp(from.fontSize, to.fontSize, t),
    lineHeight = lerp(from.lineHeight, to.lineHeight, t),
    fontWeight = if (t < 0.5f) from.fontWeight else to.fontWeight,
    letterSpacing = lerp(from.letterSpacing, to.letterSpacing, t)
)

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
                Caption(R.string.answer_any, MetchuColors.Grey400, scale, width = 140.dp)
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
                ThinIcon(level.id, iconSize(level) * rowScale, MetchuColors.Grey300)
            }
        }
    }
}

/** The colored circle that marks the answer: the only thing in the row with a shadow. */
@Composable
private fun Handle(level: Level, x: Float, diameter: Float, faded: Boolean, rowScale: Float) {
    val color by animateColorAsState(level.color, tween(160), label = "handle")
    val alpha by animateFloatAsState(if (faded) 0.35f else 1f, tween(160), label = "handleAlpha")
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
            ThinIcon(level.id, iconSize(level) * rowScale, Color.White)
        }
    }
}

/**
 * The check for yes answers, the cross for no answers, nothing for the rest, drawn with a
 * true 1.5 dp line like the rings and the track whatever the icon's [size].
 */
@Composable
private fun ThinIcon(answer: String, size: Dp, tint: Color) {
    val width = 1.5f * 24f / size.value
    val icon = remember(answer, width) {
        when (answer) {
            AnswerId.YES, AnswerId.PROBABLY_YES -> Icons.check(width)
            AnswerId.NO, AnswerId.PROBABLY_NO -> Icons.cross(width)
            else -> null
        }
    } ?: return
    Image(icon, null, Modifier.size(size), colorFilter = ColorFilter.tint(tint))
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
