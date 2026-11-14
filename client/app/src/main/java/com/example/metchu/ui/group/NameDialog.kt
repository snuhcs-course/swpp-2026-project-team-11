package com.example.metchu.ui.group

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.example.metchu.R
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType

/** Asks before leaving a room whose questions have started: nobody can come back into it. */
@Composable
fun LeaveRoomDialog(onLeave: () -> Unit, onStay: () -> Unit) {
    AlertDialog(
        onDismissRequest = onStay,
        confirmButton = {
            TextButton(onLeave, Modifier.testTag("leaveConfirm")) {
                Text(stringResource(R.string.group_leave_confirm), style = MetchuType.Button, color = MetchuColors.Primary)
            }
        },
        dismissButton = {
            TextButton(onStay) {
                Text(stringResource(R.string.group_leave_stay), style = MetchuType.Button, color = MetchuColors.Grey600)
            }
        },
        title = { Text(stringResource(R.string.group_leave_title), style = MetchuType.Item) },
        text = { Text(stringResource(R.string.group_leave_body), style = MetchuType.Body) },
        shape = RoundedCornerShape(20.dp),
        containerColor = Color.White
    )
}

/** Asks a guest, before they create a room, for the name the others will see. */
@Composable
fun NameDialog(initial: String, onName: (String) -> Unit, onDismiss: () -> Unit) {
    var name by rememberSaveable { mutableStateOf(initial) }
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton({ onName(name.trim()) }, enabled = name.isNotBlank(), modifier = Modifier.testTag("nameOk")) {
                Text(stringResource(R.string.group_name_ok), style = MetchuType.Button, color = if (name.isNotBlank()) MetchuColors.Primary else MetchuColors.Grey400)
            }
        },
        dismissButton = {
            TextButton(onDismiss) {
                Text(stringResource(R.string.group_name_cancel), style = MetchuType.Button, color = MetchuColors.Grey600)
            }
        },
        title = { Text(stringResource(R.string.group_name_title), style = MetchuType.Item) },
        text = {
            Column {
                Text(stringResource(R.string.group_name_body), style = MetchuType.Body)
                BasicTextField(
                    name, { name = it.take(MAX_NAME) },
                    Modifier
                        .padding(top = 14.dp)
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                        .background(MetchuColors.Grey100)
                        .padding(horizontal = 14.dp, vertical = 12.dp)
                        .testTag("nameField"),
                    textStyle = MetchuType.Button,
                    singleLine = true
                )
            }
        },
        shape = RoundedCornerShape(20.dp),
        containerColor = Color.White
    )
}
