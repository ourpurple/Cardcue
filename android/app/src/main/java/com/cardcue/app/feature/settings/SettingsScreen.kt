package com.cardcue.app.feature.settings

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.cardcue.app.common.ui.*

@Composable
fun SettingsScreen(modifier: Modifier) {
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
                SectionCard("数据说明") {
                    Text("此版本内置演示账单与后台同步，不代表你的真实欠款。还款记录只用于个人管理，不执行真实转账。", color = Muted, fontSize = 13.sp, lineHeight = 22.sp)
                    Spacer(Modifier.height(12.dp))
                    Text("邮件账单由自建后台抓取并提取草稿，在手机核对原文依据后方可入账。", color = Muted, fontSize = 13.sp, lineHeight = 22.sp)
                }
            }
        }
        item { Text("CardCue  0.1.0\nEvery bill. On time.", color = Muted, fontSize = 12.sp, lineHeight = 22.sp, modifier = Modifier.padding(horizontal = 26.dp, vertical = 8.dp)) }
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
