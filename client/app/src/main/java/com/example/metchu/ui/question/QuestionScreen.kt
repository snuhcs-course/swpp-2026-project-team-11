package com.example.metchu.ui.question

import androidx.annotation.StringRes
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
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
import com.example.metchu.ui.common.Pill
import com.example.metchu.ui.common.PillDivider
import com.example.metchu.ui.common.PillSegment
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
    Level(AnswerId.NO, 70.dp, MetchuColors.Grey700, R.string.level_no, Icons.Cross),
    Level(AnswerId.PROBABLY_NO, 58.dp, MetchuColors.Grey700, R.string.level_probably_no, null),
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
            Row(
                Modifier.fillMaxWidth().height(56.dp).padding(start = 20.dp, end = 20.dp, top = 6.dp),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                CircleIconButton(Icons.Back, stringResource(R.string.back), onBack, Modifier.testTag("back"))
                // Shown from the first question, so the pill does not change when it can be used;
                // "Start over" keeps the corner it has on the result screen.
                Pill {
                    PillSegment(
                        stringResource(R.string.recommend_now), onRecommendNow, start = 18.dp, end = 14.dp,
                        enabled = count > 0, modifier = Modifier.testTag("recommendNow")
                    )
                    PillDivider()
                    PillSegment(stringResource(R.string.result_home), onHome, start = 14.dp, modifier = Modifier.testTag("home"))
                }
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

            AnswerScale(offered, active, pressing, loading, pick, press)
            ProgressBlock(session, loading)
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
private fun AnswerScale(
    offered: Set<String>,
    active: String?,
    pressing: String?,
    loading: Boolean,
    onPick: (String) -> Unit,
    onPress: (String?) -> Unit
) {
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
            Row(
                Modifier.fillMaxWidth().height(76.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Levels.forEach { level ->
                    ScaleCircle(
                        level, scale, enabled = level.id in offered, filled = active == level.id,
                        pressed = pressing == level.id, loading, onPick, onPress
                    )
                }
            }
            Spacer(Modifier.height(4.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Caption(R.string.answer_no, MetchuColors.Grey700, scale)
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

@Composable
private fun ScaleCircle(
    level: Level,
    rowScale: Float,
    enabled: Boolean,
    filled: Boolean,
    pressed: Boolean,
    loading: Boolean,
    onPick: (String) -> Unit,
    onPress: (String?) -> Unit
) {
    val fill by animateColorAsState(if (filled) level.color else Color.Transparent, tween(120), label = "fill")
    val scale by animateFloatAsState(if (pressed) 0.9f else 1f, tween(120), label = "press")
    val description = stringResource(level.label)
    Box(
        Modifier
            .size(level.size * rowScale)
            .scale(scale)
            .alpha(if (enabled) 1f else 0.3f)
            .clip(CircleShape)
            .background(fill)
            .drawBehind {
                val width = 2.5.dp.toPx()
                drawCircle(level.color, radius = (size.minDimension - width) / 2, style = Stroke(width))
            }
            .then(if (enabled) Modifier.pressPreview(level.id, loading, onPick, onPress) else Modifier)
            .semantics {
                role = Role.Button
                contentDescription = description
                if (enabled) onClick { onPick(level.id); true }
            }
            .testTag("answer_${level.id}"),
        contentAlignment = Alignment.Center
    ) {
        if (level.icon != null) {
            Image(
                level.icon, null,
                Modifier.size((if (level.icon == Icons.Check) 28.dp else 26.dp) * rowScale),
                colorFilter = ColorFilter.tint(if (filled) Color.White else level.color)
            )
        }
    }
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
