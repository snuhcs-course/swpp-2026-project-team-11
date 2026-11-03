package com.example.metchu.ui.common

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.draw.clip
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.sp
import com.example.metchu.R
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType

/** One choice in a picker: its label, a note shown beside it when not picked, and what picking it does. */
class PickerOption(val label: String, val note: String?, val selected: Boolean, val onPick: () -> Unit)

/** Rounded on top like the result sheet. */
private val SheetShape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp)

/** The sheet's entrance curve, shared with the result sheet. */
val SheetEasing = CubicBezierEasing(0.2f, 0.8f, 0.2f, 1f)

/**
 * A panel that rises from the bottom over a dimmed screen, built like the result sheet: its
 * handle, a grey [caption] over the [title], then [description] where the result sheet puts
 * its reason. [content] spans the full width. A tap on the handle or outside calls [onDismiss].
 */
@Composable
fun BottomSheet(
    visible: Boolean,
    caption: String,
    title: String,
    description: String?,
    onDismiss: () -> Unit,
    content: @Composable ColumnScope.() -> Unit
) {
    Box(Modifier.fillMaxSize()) {
        AnimatedVisibility(visible, enter = fadeIn(tween(200)), exit = fadeOut(tween(200))) {
            Box(
                Modifier.fillMaxSize().background(MetchuColors.Grey900.copy(alpha = 0.48f))
                    .clickable(remember { MutableInteractionSource() }, indication = null, onClick = onDismiss)
            )
        }
        AnimatedVisibility(
            visible,
            modifier = Modifier.align(Alignment.BottomCenter),
            enter = slideInVertically(tween(320, easing = SheetEasing)) { it },
            exit = slideOutVertically(tween(240)) { it }
        ) {
            val close = stringResource(R.string.sheet_close)
            Column(
                Modifier
                    .fillMaxWidth()
                    .cssShadow(SheetShape, (-2).dp, 12.dp, 0.10f)
                    .clip(SheetShape)
                    .background(Color.White)
                    .navigationBarsPadding()
                    .padding(bottom = 24.dp)
            ) {
                Box(
                    Modifier
                        .fillMaxWidth()
                        .height(20.dp)
                        .clickable(remember { MutableInteractionSource() }, indication = null, role = Role.Button, onClickLabel = close, onClick = onDismiss)
                        .semantics { contentDescription = close },
                    contentAlignment = Alignment.Center
                ) {
                    Box(Modifier.width(38.dp).height(3.5.dp).clip(CircleShape).background(MetchuColors.Grey300))
                }
                Column(Modifier.padding(start = 20.dp, end = 20.dp, bottom = 20.dp)) {
                    Text(caption, Modifier.padding(bottom = 2.dp), style = MetchuType.Caption)
                    Text(title, style = MetchuType.Title, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (description != null) Text(description, Modifier.padding(top = 10.dp), style = MetchuType.Body.copy(fontSize = 14.sp, lineHeight = 20.sp))
                }
                content()
            }
        }
    }
}
