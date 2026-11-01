package com.example.metchu.ui.common

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathBuilder
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.example.metchu.R
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import androidx.compose.foundation.Image
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics

/** The shadow of buttons that float over the screen: 0 2 10, 16 %. */
fun Modifier.floating(shape: Shape = CircleShape, elevation: Dp = 6.dp): Modifier =
    shadow(elevation, shape, ambientColor = MetchuColors.Shadow.copy(alpha = 0.16f), spotColor = MetchuColors.Shadow.copy(alpha = 0.16f))

/** Shrinks a little while pressed, like the canvas `.go:active` and `.dot:active` rules. */
@Composable
fun Modifier.pressScale(interaction: MutableInteractionSource, pressed: Float = 0.95f): Modifier {
    val isPressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(if (isPressed) pressed else 1f, label = "press")
    return scale(scale)
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

@Composable
fun PillSegment(text: String, onClick: () -> Unit, color: Color = MetchuColors.Grey900, start: Dp = 18.dp, end: Dp = 18.dp) {
    Box(
        Modifier.height(44.dp).clickable(role = Role.Button, onClick = onClick).padding(start = start, end = end),
        contentAlignment = Alignment.Center
    ) { Text(text, style = MetchuType.Label, color = color, maxLines = 1) }
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

/** Line icons drawn on a 24-unit grid, as in the canvas. */
object Icons {
    private fun line(name: String, block: PathBuilder.() -> Unit, width: Float = 2.2f) =
        ImageVector.Builder(name, 24.dp, 24.dp, 24f, 24f).path(
            stroke = SolidColor(Color.Black), strokeLineWidth = width,
            strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round, pathBuilder = block
        ).build()

    val Back = line("back", { moveTo(15f, 5f); lineTo(8f, 12f); lineTo(15f, 19f) })
    val ChevronDown = line("down", { moveTo(7f, 10f); lineTo(12f, 15f); lineTo(17f, 10f) }, 2.4f)
    val ChevronRight = line("right", { moveTo(9f, 6f); lineTo(15f, 12f); lineTo(9f, 18f) }, 2.4f)
    val Check = line("check", { moveTo(5f, 12.5f); lineTo(9.5f, 17f); lineTo(19f, 7.5f) }, 2.4f)
    val Cross = line("cross", { moveTo(6.5f, 6.5f); lineTo(17.5f, 17.5f); moveTo(17.5f, 6.5f); lineTo(6.5f, 17.5f) }, 2.4f)
    val Globe = line("globe", {
        moveTo(21f, 12f); arcTo(9f, 9f, 0f, true, true, 3f, 12f); arcTo(9f, 9f, 0f, true, true, 21f, 12f)
        moveTo(3f, 12f); lineTo(21f, 12f)
        moveTo(12f, 3f); curveTo(14.5f, 5.6f, 15.8f, 8.6f, 15.8f, 12f); curveTo(15.8f, 15.4f, 14.5f, 18.4f, 12f, 21f)
        curveTo(9.5f, 18.4f, 8.2f, 15.4f, 8.2f, 12f); curveTo(8.2f, 8.6f, 9.5f, 5.6f, 12f, 3f)
    }, 2f)
    val Gear = line("gear", {
        moveTo(15f, 12f); arcTo(3f, 3f, 0f, true, true, 9f, 12f); arcTo(3f, 3f, 0f, true, true, 15f, 12f)
        moveTo(12f, 2.5f); lineTo(12f, 5f); moveTo(12f, 19f); lineTo(12f, 21.5f)
        moveTo(2.5f, 12f); lineTo(5f, 12f); moveTo(19f, 12f); lineTo(21.5f, 12f)
        moveTo(5.3f, 5.3f); lineTo(7.05f, 7.05f); moveTo(16.95f, 16.95f); lineTo(18.7f, 18.7f)
        moveTo(5.3f, 18.7f); lineTo(7.05f, 16.95f); moveTo(16.95f, 7.05f); lineTo(18.7f, 5.3f)
        moveTo(18f, 12f); arcTo(6f, 6f, 0f, true, true, 6f, 12f); arcTo(6f, 6f, 0f, true, true, 18f, 12f)
    }, 2.2f)
}
