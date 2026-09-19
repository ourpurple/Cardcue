package com.cardcue.app.feature.settings

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.cardcue.app.common.ui.*

@Composable
fun SettingsScreen(
    modifier: Modifier = Modifier,
    onResetAllData: () -> Unit = {}
) {
    var showResetDialog by remember { mutableStateOf(false) }

    LazyColumn(modifier, contentPadding = PaddingValues(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { PageHeader("我的 CardCue", "一个安静、清楚的私人账单本") }
        item {
            Column(Modifier.padding(horizontal = 20.dp)) {
                SectionCard("当前版本") {
                    SettingRow(Icons.Outlined.CheckCircle, "本地账单与还款记录", "已可用 · 自动保存在此设备", Green)
                    SettingRow(Icons.Outlined.MailOutline, "邮箱账单 · IMAP", "已接入后台定时收取 · 支持按需检查", Green)
                    SettingRow(Icons.Outlined.AutoAwesome, "智能账单解析与草稿核对", "已接入 · 规则解析与结构化草稿核对", Green)
                    SettingRow(Icons.Outlined.NotificationsNone, "到期通知", "尚未开放 · 当前不会发送提醒", Muted)
                    SettingRow(Icons.Outlined.Lock, "加密备份", "尚未开放 · 卸载或清除数据会丢失记录", Muted)
                }
            }
        }
        item {
            Column(Modifier.padding(horizontal = 20.dp)) {
                SectionCard("数据管理") {
                    Text(
                        "清空本地数据将清除本设备上的所有演示账单、缓存数据及还款记录，使 App 回到初始状态并重新从后台同步最新权威账单。",
                        color = Muted,
                        fontSize = 13.sp,
                        lineHeight = 22.sp
                    )
                    Spacer(Modifier.height(14.dp))
                    Button(
                        onClick = { showResetDialog = true },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Red.copy(alpha = 0.12f),
                            contentColor = Red
                        ),
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .testTag("settings-reset-button")
                    ) {
                        Icon(Icons.Outlined.DeleteSweep, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(8.dp))
                        Text("清空本地数据（回到初始状态）", fontSize = 13.sp, fontWeight = FontWeight.Medium)
                    }
                }
            }
        }
        item {
            Column(Modifier.padding(horizontal = 20.dp)) {
                SectionCard("数据说明") {
                    Text("此版本内置演示账单与后台同步，不代表你的真实欠款。还款记录只用于个人管理，不执行真实转账。", color = Muted, fontSize = 13.sp, lineHeight = 22.sp)
                    Spacer(Modifier.height(12.dp))
                    Text("邮件账单由自建后台抓取并提取草稿，在手机核对原文依据后方可入账。", color = Muted, fontSize = 13.sp, lineHeight = 22.sp)
                }
            }
        }
        item { Text("CardCue v0.1.0\nEvery bill. On time.", color = Muted, fontSize = 12.sp, lineHeight = 22.sp, modifier = Modifier.padding(horizontal = 26.dp, vertical = 8.dp)) }
    }

    if (showResetDialog) {
        AlertDialog(
            onDismissRequest = { showResetDialog = false },
            icon = { Icon(Icons.Outlined.WarningAmber, contentDescription = null, tint = Red) },
            title = { Text("确认清空并回到初始状态？") },
            text = { Text("此操作将清除本地的所有演示账单、还款记录与本地缓存，并重新从后台获取最新账单数据。") },
            confirmButton = {
                TextButton(
                    onClick = {
                        showResetDialog = false
                        onResetAllData()
                    },
                    modifier = Modifier.testTag("settings-confirm-reset-button")
                ) {
                    Text("确认清空", color = Red, fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                TextButton(onClick = { showResetDialog = false }) {
                    Text("取消")
                }
            }
        )
    }
}

@Composable
private fun SettingRow(icon: ImageVector, title: String, subtitle: String, color: Color) {
    Row(Modifier.fillMaxWidth().padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, null, tint = color, modifier = Modifier.size(22.dp))
        Column(Modifier.padding(start = 13.dp).weight(1f)) {
            Text(title, fontSize = 14.sp, fontWeight = FontWeight.Medium)
            Text(subtitle, color = Muted, fontSize = 11.sp, lineHeight = 18.sp, modifier = Modifier.padding(top = 4.dp))
        }
    }
}
