package com.cardcue.app.common.ui

import androidx.compose.material3.lightColorScheme
import androidx.compose.ui.graphics.Color

val Ink = Color(0xFF17252C)
val Paper = Color(0xFFF7F5F0)
val Gold = Color(0xFFDDB56A)
val Muted = Color(0xFF707A7E)
val Green = Color(0xFF267566)
val Red = Color(0xFFB5413D)
val Line = Color(0xFFE7E5DF)

val Palette = lightColorScheme(
    primary = Ink, onPrimary = Color.White, secondary = Green,
    background = Paper, surface = Color.White, onSurface = Ink,
    onSurfaceVariant = Muted, outlineVariant = Line, error = Red,
)
