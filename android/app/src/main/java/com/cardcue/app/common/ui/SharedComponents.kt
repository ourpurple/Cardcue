package com.cardcue.app.common.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun BankBadge(mark: String, color: Color, compact: Boolean = false) {
    Box(
        Modifier
            .size(if (compact) 30.dp else 38.dp)
            .clip(CircleShape)
            .background(color.copy(alpha = 0.1f)),
        contentAlignment = Alignment.Center
    ) {
        Text(mark, color = color, fontWeight = FontWeight.Bold, fontSize = if (compact) 16.sp else 18.sp)
    }
}

@Composable
fun PageHeader(title: String, subtitle: String, onBack: (() -> Unit)? = null) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(Ink)
            .padding(horizontal = 20.dp, vertical = 20.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (onBack != null) IconButton(onClick = onBack, modifier = Modifier.padding(end = 6.dp)) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack, "返回", tint = Color.White)
            }
            Column {
                Text(title, color = Color.White, fontSize = 24.sp, fontWeight = FontWeight.Bold)
                Text(subtitle, color = Gold, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp))
            }
        }
    }
}

@Composable
fun SectionCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Surface(shape = RoundedCornerShape(20.dp), color = Color.White) {
        Column(Modifier.fillMaxWidth().padding(20.dp)) {
            Text(title, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(12.dp))
            content()
        }
    }
}

@Composable
fun InfoRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 9.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(label, color = Muted, fontSize = 13.sp, modifier = Modifier.weight(0.42f))
        Text(value, color = Ink, fontSize = 13.sp, modifier = Modifier.weight(0.58f))
    }
}
