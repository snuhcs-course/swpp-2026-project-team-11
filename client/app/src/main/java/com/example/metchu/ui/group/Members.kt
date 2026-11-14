package com.example.metchu.ui.group

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.metchu.R
import com.example.metchu.data.model.Allergen
import com.example.metchu.data.model.RoomMember
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType

/** A pale fill and a dark ink of the same hue per member, in joining order. */
private val Tints = listOf(
    Color(0xFFFBE3D9) to Color(0xFFB23A0A),
    Color(0xFFDCE9FB) to Color(0xFF1F5FB8),
    Color(0xFFDDEFE3) to Color(0xFF2B7148),
    Color(0xFFECE3F8) to Color(0xFF6A3FA8),
    Color(0xFFF8EBCF) to Color(0xFF8A5A00),
    Color(0xFFFADDE6) to Color(0xFFA3264E),
    Color(0xFFD7F0F0) to Color(0xFF1F6B6B),
    Color(0xFFE4E7EB) to MetchuColors.Grey700
)

/** A member's circle with the first letter of their name; [ring] marks this phone's member or an answer. */
@Composable
fun Avatar(member: RoomMember, size: Dp, modifier: Modifier = Modifier, ring: Color? = null) {
    val (fill, ink) = Tints[member.id % Tints.size]
    Box(
        modifier
            .size(size)
            .then(if (ring != null) Modifier.border(2.dp, ring, CircleShape).padding(4.dp) else Modifier)
            .clip(CircleShape)
            .background(fill),
        contentAlignment = Alignment.Center
    ) {
        Text(
            member.name.take(1).uppercase(),
            style = MetchuType.Label.copy(fontSize = (size.value * 0.4f).sp, lineHeight = (size.value * 0.5f).sp, fontWeight = FontWeight.Bold),
            color = ink
        )
    }
}

/** "No eggs, peanuts" or "No allergies", for the member list. */
@Composable
fun allergyText(member: RoomMember): String {
    val names = member.allergies.mapNotNull { id -> Allergen.entries.firstOrNull { it.id == id } }.map { stringResource(it.label) }
    return if (names.isEmpty()) stringResource(R.string.group_no_allergies)
    else stringResource(R.string.group_without, names.joinToString(", "))
}
