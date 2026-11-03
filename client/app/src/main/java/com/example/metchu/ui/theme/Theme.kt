package com.example.metchu.ui.theme

import androidx.compose.foundation.LocalIndication
import androidx.compose.foundation.background
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.PlatformTextStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.example.metchu.R
import com.example.metchu.ui.common.NoIndication

/** The color tokens of the design foundation board (1st UI/UX, 11/02). */
object MetchuColors {
    /** Start button and whatever the user has picked. */
    val Primary = Color(0xFFD2440C)
    val Grey900 = Color(0xFF1A1F26)
    val Grey700 = Color(0xFF4E5762)
    /** The lightest grey for text: 4.7:1 on white. Grey400 and lighter are for lines and fills. */
    val Grey600 = Color(0xFF6B7480)
    val Grey400 = Color(0xFFA8B0B9)
    val Grey300 = Color(0xFFCED3D9)
    val Grey200 = Color(0xFFE4E7EB)
    val Grey100 = Color(0xFFF2F4F6)
    val MapBlank = Color(0xFFECEEF1)
    val Shadow = Color(0xFF1A1F26)
}

/** Pretendard, subset to KS X 1001 Hangul and Latin and renamed as the OFL requires. */
val MetchuSans = FontFamily(
    Font(R.font.metchu_sans_regular, FontWeight.Normal),
    Font(R.font.metchu_sans_medium, FontWeight.Medium),
    Font(R.font.metchu_sans_semibold, FontWeight.SemiBold),
    Font(R.font.metchu_sans_bold, FontWeight.Bold)
)

/** The six text sizes of the design foundation board. */
object MetchuType {
    // CSS puts half the extra line height above each line and half below, and does not trim it.
    private val base = TextStyle(
        fontFamily = MetchuSans,
        letterSpacing = (-0.01).em,
        color = MetchuColors.Grey900,
        platformStyle = PlatformTextStyle(includeFontPadding = false),
        lineHeightStyle = LineHeightStyle(LineHeightStyle.Alignment.Center, LineHeightStyle.Trim.None)
    )
    val Title = base.copy(fontSize = 28.sp, lineHeight = 39.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.02).em)
    val Item = base.copy(fontSize = 20.sp, lineHeight = 28.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.02).em)
    val Button = base.copy(fontSize = 17.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold)
    val Label = base.copy(fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold)
    val Body = base.copy(fontSize = 15.sp, lineHeight = 22.sp, color = MetchuColors.Grey700)
    val Lead = base.copy(fontSize = 17.sp, lineHeight = 26.sp, color = MetchuColors.Grey700)
    val Caption = base.copy(fontSize = 12.sp, lineHeight = 16.sp, fontWeight = FontWeight.Medium, color = MetchuColors.Grey600)
}

/** Every screen and sheet is plain white. */
fun Modifier.screenBackground(): Modifier = background(Color.White)

@Composable
fun MetchuTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = MetchuColors.Primary,
            onPrimary = Color.White,
            background = Color.White,
            onBackground = MetchuColors.Grey900,
            surface = Color.White,
            onSurface = MetchuColors.Grey900
        )
    ) {
        CompositionLocalProvider(
            LocalTextStyle provides MetchuType.Body,
            LocalIndication provides NoIndication,
            content = content
        )
    }
}
