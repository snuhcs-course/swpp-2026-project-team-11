package com.example.metchu.ui.group

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.metchu.R
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.LabelCapsule
import com.example.metchu.ui.common.TopRow
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import com.example.metchu.ui.theme.screenBackground

const val CODE_LENGTH = 4
const val MAX_NAME = 20

/**
 * Four boxes filled from the app's own number pad, and for a [guest] the name the others
 * will see. "Join" turns orange once both are there.
 */
@Composable
fun JoinScreen(guest: Boolean, busy: Boolean, onJoin: (code: String, name: String?) -> Unit, onBack: () -> Unit) {
    var code by rememberSaveable { mutableStateOf("") }
    var name by rememberSaveable { mutableStateOf("") }
    val ready = code.length == CODE_LENGTH && (!guest || name.isNotBlank()) && !busy

    Box(Modifier.fillMaxSize().screenBackground()) {
        Column(Modifier.statusBarsPadding()) {
            TopRow { CircleIconButton(Icons.Back, stringResource(R.string.back), onBack, Modifier.testTag("back")) }
            Column(Modifier.padding(start = 20.dp, end = 20.dp, top = 10.dp)) {
                Text(stringResource(R.string.group_join_title), style = MetchuType.Title)
                Text(stringResource(R.string.group_join_sub), Modifier.padding(top = 8.dp), style = MetchuType.Lead)
                CodeBoxes(code, Modifier.padding(top = 28.dp))
                if (guest) NameField(name, { name = it.take(MAX_NAME) }, Modifier.padding(top = 20.dp))
            }
        }
        Column(Modifier.align(Alignment.BottomCenter).navigationBarsPadding()) {
            LabelCapsule(
                stringResource(R.string.group_join),
                { onJoin(code, name.trim().takeIf { guest }) },
                filled = ready,
                enabled = ready,
                modifier = Modifier.align(Alignment.End).padding(end = 20.dp, bottom = 16.dp).testTag("join")
            )
            Keypad(
                onDigit = { if (code.length < CODE_LENGTH) code += it },
                onDelete = { code = code.dropLast(1) }
            )
        }
    }
}

@Composable
private fun CodeBoxes(code: String, modifier: Modifier = Modifier) {
    val description = stringResource(R.string.group_code)
    Row(
        modifier.fillMaxWidth().semantics { contentDescription = "$description $code" }.testTag("code"),
        horizontalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        repeat(CODE_LENGTH) { i ->
            val digit = code.getOrNull(i)
            val active = i == code.length
            val shape = RoundedCornerShape(14.dp)
            Box(
                Modifier
                    .weight(1f)
                    .height(68.dp)
                    .border(if (active || digit != null) 2.dp else 1.5.dp, when {
                        active -> MetchuColors.Primary
                        digit != null -> MetchuColors.Grey900
                        else -> MetchuColors.Grey300
                    }, shape),
                contentAlignment = Alignment.Center
            ) {
                Text(digit?.toString().orEmpty(), style = MetchuType.Title.copy(fontSize = 32.sp, lineHeight = 40.sp))
            }
        }
    }
}

@Composable
private fun NameField(name: String, onName: (String) -> Unit, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(stringResource(R.string.group_name_hint), style = MetchuType.Caption)
        BasicTextField(
            name, onName,
            Modifier
                .padding(top = 6.dp)
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(MetchuColors.Grey100)
                .padding(horizontal = 14.dp, vertical = 12.dp)
                .testTag("name"),
            textStyle = MetchuType.Button,
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done)
        )
    }
}

/** 1–9, then 0 and delete on the bottom row, like a phone's dial pad. */
@Composable
private fun Keypad(onDigit: (Char) -> Unit, onDelete: () -> Unit) {
    val rows = listOf("123", "456", "789", " 0<")
    Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp)) {
        rows.forEach { row ->
            Row(Modifier.fillMaxWidth()) {
                row.forEach { key ->
                    val interaction = remember { MutableInteractionSource() }
                    val pressed by interaction.collectIsPressedAsState()
                    Box(
                        Modifier
                            .weight(1f)
                            .height(58.dp)
                            .clip(RoundedCornerShape(12.dp))
                            .background(if (pressed) MetchuColors.Grey100 else MetchuColors.Grey100.copy(alpha = 0f))
                            .then(
                                if (key == ' ') Modifier
                                else Modifier.clickable(interaction, indication = null, role = Role.Button) {
                                    if (key == '<') onDelete() else onDigit(key)
                                }
                            )
                            .testTag("key_$key"),
                        contentAlignment = Alignment.Center
                    ) {
                        when (key) {
                            ' ' -> Unit
                            '<' -> Image(
                                Icons.Back, stringResource(R.string.group_keypad_delete), Modifier.size(24.dp),
                                colorFilter = ColorFilter.tint(MetchuColors.Grey900)
                            )
                            else -> Text(key.toString(), style = MetchuType.Item.copy(fontSize = 24.sp))
                        }
                    }
                }
            }
        }
    }
}
