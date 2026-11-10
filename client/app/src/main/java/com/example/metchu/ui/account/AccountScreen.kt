package com.example.metchu.ui.account

import androidx.annotation.StringRes
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import com.example.metchu.R
import com.example.metchu.ui.common.ActionCapsule
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.LabelCapsule
import com.example.metchu.ui.common.PinnedTopRow
import com.example.metchu.ui.common.Spinner
import com.example.metchu.ui.common.TopRowHeight
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import com.example.metchu.ui.theme.screenBackground

/**
 * Logging in or signing up with a username and password, or with Google. An account is
 * optional: on the first launch [onSkip] goes on without one; from the settings there is
 * only Back. [onGoogle] is null when this build has no Google client ID.
 */
@Composable
fun AccountScreen(
    busy: Boolean,
    @StringRes error: Int?,
    onLogIn: (username: String, password: String) -> Unit,
    onSignUp: (username: String, password: String, confirmation: String) -> Unit,
    onGoogle: (() -> Unit)?,
    onModeChange: () -> Unit,
    onBack: () -> Unit,
    onSkip: (() -> Unit)? = null
) {
    var signUp by rememberSaveable { mutableStateOf(false) }
    var username by rememberSaveable { mutableStateOf("") }
    // Passwords are not saved with the screen's state.
    var password by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf("") }
    val submit = { if (signUp) onSignUp(username, password, confirmation) else onLogIn(username, password) }
    val scroll = rememberScrollState()

    Box(Modifier.fillMaxSize().screenBackground()) {
        Column(Modifier.fillMaxSize().statusBarsPadding().imePadding().verticalScroll(scroll)) {
            Spacer(Modifier.height(TopRowHeight))
            Column(Modifier.padding(start = 20.dp, end = 20.dp, top = 8.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Text(stringResource(if (signUp) R.string.account_sign_up_title else R.string.account_log_in_title), style = MetchuType.Title)
                Text(stringResource(R.string.account_lead), style = MetchuType.Lead)
                Field(username, { username = it }, R.string.account_username, "accountUsername", ImeAction.Next)
                Field(password, { password = it }, R.string.account_password, "accountPassword",
                      if (signUp) ImeAction.Next else ImeAction.Done, secret = true, onDone = submit)
                if (signUp) {
                    Field(confirmation, { confirmation = it }, R.string.account_password_again, "accountConfirm",
                          ImeAction.Done, secret = true, onDone = submit)
                    Text(stringResource(R.string.account_rules), style = MetchuType.Caption)
                }
                if (error != null) {
                    Text(stringResource(error), Modifier.testTag("accountError"), style = MetchuType.Label, color = MetchuColors.Primary)
                }
                LabelCapsule(
                    stringResource(if (signUp) R.string.account_sign_up else R.string.account_log_in), submit,
                    filled = true, enabled = !busy, modifier = Modifier.fillMaxWidth().testTag("accountSubmit")
                )
                Text(
                    stringResource(if (signUp) R.string.account_have_one else R.string.account_need_one),
                    Modifier
                        .align(Alignment.CenterHorizontally)
                        .clickable(role = Role.Button) { signUp = !signUp; onModeChange() }
                        .padding(8.dp)
                        .testTag("accountSwitch"),
                    style = MetchuType.Label, color = MetchuColors.Grey700
                )
                if (onGoogle != null) {
                    Text(stringResource(R.string.account_or), Modifier.align(Alignment.CenterHorizontally), style = MetchuType.Caption)
                    LabelCapsule(
                        stringResource(R.string.account_google), onGoogle, filled = false, enabled = !busy,
                        modifier = Modifier.fillMaxWidth().testTag("accountGoogle")
                    )
                }
                if (busy) Spinner(MetchuColors.Primary, 28.dp, Modifier.align(Alignment.CenterHorizontally))
            }
            Box(Modifier.navigationBarsPadding().height(120.dp))
        }
        PinnedTopRow(scroll) {
            CircleIconButton(Icons.Back, stringResource(R.string.back), onBack, Modifier.testTag("back"))
        }
        if (onSkip != null) {
            ActionCapsule(
                stringResource(R.string.account_skip), Icons.Forward, onSkip, filled = false,
                modifier = Modifier.align(Alignment.BottomEnd).navigationBarsPadding().padding(end = 20.dp, bottom = 16.dp).testTag("accountSkip")
            )
        }
    }
}

@Composable
private fun Field(
    value: String,
    onChange: (String) -> Unit,
    @StringRes label: Int,
    tag: String,
    action: ImeAction,
    secret: Boolean = false,
    onDone: () -> Unit = {}
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        modifier = Modifier.fillMaxWidth().testTag(tag),
        label = { Text(stringResource(label)) },
        singleLine = true,
        textStyle = MetchuType.Body.copy(color = MetchuColors.Grey900),
        visualTransformation = if (secret) PasswordVisualTransformation() else VisualTransformation.None,
        keyboardOptions = KeyboardOptions(
            keyboardType = if (secret) KeyboardType.Password else KeyboardType.Text,
            autoCorrectEnabled = false,
            imeAction = action
        ),
        keyboardActions = KeyboardActions(onDone = { onDone() }),
        shape = RoundedCornerShape(14.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = MetchuColors.Primary,
            focusedLabelColor = MetchuColors.Primary,
            cursorColor = MetchuColors.Primary,
            unfocusedBorderColor = MetchuColors.Grey300
        )
    )
}
