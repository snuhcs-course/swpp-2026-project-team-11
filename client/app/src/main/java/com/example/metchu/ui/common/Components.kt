package com.example.metchu.ui.common

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.Image
import androidx.compose.foundation.IndicationNodeFactory
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.InteractionSource
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.Paint
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawOutline
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.node.DelegatableNode
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.example.metchu.R
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import kotlinx.coroutines.delay

/**
 * A CSS box-shadow (`0 [offsetY] [blur] rgba(26, 31, 38, [alpha])`) behind [shape].
 * Android's elevation shadows come out much fainter than the canvas, so the blur is
 * drawn directly. Put it before `clip` so the shadow is not cut off.
 */
fun Modifier.cssShadow(shape: Shape, offsetY: Dp, blur: Dp, alpha: Float): Modifier = drawBehind {
    val outline = shape.createOutline(size, layoutDirection, this)
    val paint = Paint()
    paint.asFrameworkPaint().apply {
        color = android.graphics.Color.WHITE
        // A CSS blur of B is a Gaussian of sigma B / 2; Skia's radius r is sigma ≈ 0.58 r.
        setShadowLayer(blur.toPx() * 0.87f, 0f, offsetY.toPx(), MetchuColors.Shadow.copy(alpha = alpha).toArgb())
    }
    drawIntoCanvas { it.drawOutline(outline, paint) }
}

/** The shadow of buttons that float over the screen: 0 2 10, 16 %. */
fun Modifier.floating(shape: Shape = CircleShape): Modifier = cssShadow(shape, 2.dp, 10.dp, 0.16f)

/** The shadow of chips and map pins: 0 2 8, 14 %. */
fun Modifier.chipShadow(shape: Shape = CircleShape): Modifier = cssShadow(shape, 2.dp, 8.dp, 0.14f)

/** No ripple anywhere: pressed things shrink or turn grey instead, as in the canvas. */
object NoIndication : IndicationNodeFactory {
    override fun create(interactionSource: InteractionSource): DelegatableNode = object : Modifier.Node() {}
    override fun equals(other: Any?) = other === this
    override fun hashCode() = 0
}

/** Shrinks a little while pressed, like the canvas `.go:active` and `.dot:active` rules. */
@Composable
fun Modifier.pressScale(interaction: MutableInteractionSource, pressed: Float = 0.95f): Modifier {
    val isPressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(if (isPressed) pressed else 1f, label = "press")
    return scale(scale)
}

/** True once [loading] has lasted a moment, so a quick reply does not flash a spinner. */
@Composable
fun rememberSlow(loading: Boolean): Boolean {
    var slow by remember { mutableStateOf(false) }
    LaunchedEffect(loading) {
        slow = false
        if (loading) {
            delay(300)
            slow = true
        }
    }
    return slow
}

/** The spinner shown while a request runs. */
@Composable
fun Spinner(color: Color, size: Dp, modifier: Modifier = Modifier) {
    CircularProgressIndicator(modifier.size(size).testTag("loading"), color = color, strokeWidth = size / 9)
}

/** A white 44 dp circle with a shadow, holding a 20 dp icon. */
@Composable
fun CircleIconButton(icon: ImageVector, description: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val interaction = remember { MutableInteractionSource() }
    Box(
        modifier
            .size(44.dp)
            .pressScale(interaction, 0.92f)
            .floating()
            .clip(CircleShape)
            .background(Color.White)
            .clickable(interaction, indication = null, role = Role.Button, onClickLabel = description, onClick = onClick)
            .semantics { contentDescription = description },
        contentAlignment = Alignment.Center
    ) {
        Image(icon, contentDescription = null, Modifier.size(20.dp), colorFilter = ColorFilter.tint(MetchuColors.Grey900))
    }
}

/** One white pill with a shadow, holding one or more [PillSegment]s split by thin lines. */
@Composable
fun Pill(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Row(
        modifier.height(44.dp).floating().clip(CircleShape).background(Color.White),
        verticalAlignment = Alignment.CenterVertically
    ) { content() }
}

/** A disabled segment stays in place, greyed, so the pill never changes shape under a finger. */
@Composable
fun PillSegment(
    text: String,
    onClick: () -> Unit,
    color: Color = MetchuColors.Grey900,
    start: Dp = 18.dp,
    end: Dp = 18.dp,
    enabled: Boolean = true,
    modifier: Modifier = Modifier
) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    Box(
        modifier
            .height(44.dp)
            .background(if (pressed) MetchuColors.Grey100 else Color.Transparent)
            .clickable(interaction, indication = null, enabled = enabled, role = Role.Button, onClick = onClick)
            .padding(start = start, end = end),
        contentAlignment = Alignment.Center
    ) { Text(text, style = MetchuType.Label, color = if (enabled) color else MetchuColors.Grey400, maxLines = 1) }
}

@Composable
fun PillDivider() {
    Box(Modifier.width(1.dp).height(20.dp).background(MetchuColors.Grey200))
}

/** The light lowercase name in the bottom-left corner of every screen except the result. */
@Composable
fun Wordmark(modifier: Modifier = Modifier) {
    Text(
        stringResource(R.string.wordmark),
        modifier.clearAndSetSemantics {},
        style = MetchuType.Label.copy(fontWeight = FontWeight.Bold),
        color = MetchuColors.Grey300
    )
}

/** Fades the top and/or bottom [edge] of a scrolling area into the background. */
fun Modifier.fadeEdges(top: Boolean, bottom: Boolean, edge: Dp = 56.dp): Modifier =
    graphicsLayer { compositingStrategy = CompositingStrategy.Offscreen }
        .drawWithContent {
            drawContent()
            val px = edge.toPx() / size.height
            if (top) drawRect(Brush.verticalGradient(0f to Color.Transparent, px to Color.Black), blendMode = BlendMode.DstIn)
            if (bottom) drawRect(Brush.verticalGradient(1f - px to Color.Black, 1f to Color.Transparent), blendMode = BlendMode.DstIn)
        }

/** The canvas's line icons, from their SVG paths on a 24-unit grid. */
object Icons {
    private fun line(name: String, pathData: String, width: Float, round: Boolean = true) =
        ImageVector.Builder(name, 24.dp, 24.dp, 24f, 24f).addPath(
            pathData = addPathNodes(pathData),
            stroke = SolidColor(Color.Black), strokeLineWidth = width,
            strokeLineCap = if (round) StrokeCap.Round else StrokeCap.Butt, strokeLineJoin = StrokeJoin.Round
        ).build()

    val Back = line("back", "M15 5l-7 7 7 7", 2.2f)
    val ChevronDown = line("down", "M7 10l5 5 5-5", 2.4f)
    val Check = line("check", "M5 12.5l4.5 4.5L19 7.5", 2.4f)
    val Cross = line("cross", "M6.5 6.5l11 11M17.5 6.5l-11 11", 2.4f)
    val Globe = line(
        "globe",
        "M21 12a9 9 0 1 1-18 0 9 9 0 1 1 18 0M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z",
        2f
    )
    val Gear = line(
        "gear",
        "M15 12a3 3 0 1 1-6 0 3 3 0 1 1 6 0" +
            "M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21" +
            "a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8" +
            " 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8" +
            "l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3" +
            "l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
        2.4f, round = false
    )
}
