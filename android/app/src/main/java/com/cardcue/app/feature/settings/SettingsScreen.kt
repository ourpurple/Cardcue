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
import com.cardcue.app.sync.SyncInfo
import com.cardcue.app.sync.SyncState

@Composable
fun SettingsScreen(
    syncInfo: SyncInfo = SyncInfo(),
    busy: Boolean = false,
    modifier: Modifier = Modifier,
    onOpenPairDialog: () -> Unit = {},
    onSyncNow: () -> Unit = {},
    onUnpair: () -> Unit = {},
    onResetAllData: () -> Unit = {}
) {
    var showResetDialog by remember { mutableStateOf(false) }
    var showUnpairDialog by remember { mutableStateOf(false) }

    LazyColumn(
        modifier = modifier,
        contentPadding = PaddingValues(bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        item {
            PageHeader("我的 CardCue", "一个安静、清楚的私人账单本")
        }

        // 1. 云端服务与设备配对
        item {
            Column(Modifier.padding(horizontal = 20.dp)) {
                SectionCard("云端服务与设备配对") {
                    if (syncInfo.isPaired) {
                        // 已配对状态
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                Icons.Outlined.CloudDone,
                                contentDescription = null,
                                tint = Green,
                                modifier = Modifier.size(26.dp)
                            )
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) {
                                Text(
                                    "已连接到云端服务",
                                    fontSize = 15.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = Ink
                                )
                                Text(
                                    syncInfo.deviceName ?: "CardCue 移动设备",
                                    fontSize = 12.sp,
                                    color = Muted,
                                    modifier = Modifier.padding(top = 2.dp)
                                )
                            }
                            Surface(
                                color = Green.copy(alpha = 0.12f),
                                shape = RoundedCornerShape(50)
                            ) {
                                Text(
                                    "已配对",
                                    color = Green,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                                )
                            }
                        }

                        HorizontalDivider(color = Line, thickness = 0.5.dp)
                        Spacer(Modifier.height(10.dp))

                        InfoRow("服务器地址", syncInfo.serverUrl)
                        InfoRow("设备标识", syncInfo.deviceId?.take(16)?.let { "$it..." } ?: "-")
                        InfoRow(
                            "同步状态",
                            when (syncInfo.state) {
                                SyncState.SYNCING -> "正在同步数据..."
                                SyncState.SUCCESS -> "数据已是最新"
                                SyncState.OFFLINE -> "离线只读 (服务器未连接)"
                                SyncState.ERROR -> "同步异常: ${syncInfo.message ?: "未知错误"}"
                                SyncState.IDLE -> "就绪"
                            },
                            valueColor = if (syncInfo.state == SyncState.OFFLINE) Red else Ink
                        )
                        InfoRow("上次同步", syncInfo.lastSyncTime ?: "尚未同步")

                        Spacer(Modifier.height(14.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            Button(
                                onClick = onSyncNow,
                                enabled = !busy && syncInfo.state != SyncState.SYNCING,
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = Gold,
                                    contentColor = Ink,
                                    disabledContainerColor = Muted.copy(alpha = 0.2f),
                                    disabledContentColor = Muted
                                ),
                                shape = RoundedCornerShape(10.dp),
                                modifier = Modifier.weight(1f).testTag("settings-sync-now-button")
                            ) {
                                if (syncInfo.state == SyncState.SYNCING) {
                                    CircularProgressIndicator(
                                        color = Ink,
                                        strokeWidth = 2.dp,
                                        modifier = Modifier.size(16.dp)
                                    )
                                    Spacer(Modifier.width(6.dp))
                                    Text("同步中...", fontSize = 13.sp, fontWeight = FontWeight.Bold)
                                } else {
                                    Icon(Icons.Outlined.Sync, contentDescription = null, modifier = Modifier.size(16.dp))
                                    Spacer(Modifier.width(6.dp))
                                    Text("立即同步", fontSize = 13.sp, fontWeight = FontWeight.Bold)
                                }
                            }

                            OutlinedButton(
                                onClick = onOpenPairDialog,
                                enabled = !busy,
                                shape = RoundedCornerShape(10.dp),
                                modifier = Modifier.testTag("settings-repair-button")
                            ) {
                                Icon(Icons.Outlined.Key, contentDescription = null, modifier = Modifier.size(16.dp))
                                Spacer(Modifier.width(4.dp))
                                Text("重新配对", fontSize = 13.sp)
                            }
                        }

                        Spacer(Modifier.height(6.dp))

                        TextButton(
                            onClick = { showUnpairDialog = true },
                            enabled = !busy,
                            modifier = Modifier.align(Alignment.CenterHorizontally).testTag("settings-unpair-button")
                        ) {
                            Icon(
                                Icons.Outlined.LinkOff,
                                contentDescription = null,
                                tint = Red.copy(alpha = 0.8f),
                                modifier = Modifier.size(16.dp)
                            )
                            Spacer(Modifier.width(6.dp))
                            Text(
                                "解除与此服务器的绑定",
                                color = Red.copy(alpha = 0.8f),
                                fontSize = 12.sp
                            )
                        }
                    } else {
                        // 未配对状态
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(bottom = 10.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                Icons.Outlined.CloudOff,
                                contentDescription = null,
                                tint = Gold,
                                modifier = Modifier.size(26.dp)
                            )
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) {
                                Text(
                                    "未连接云端服务",
                                    fontSize = 15.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = Ink
                                )
                                Text(
                                    "当前为本地独立模式",
                                    fontSize = 12.sp,
                                    color = Muted,
                                    modifier = Modifier.padding(top = 2.dp)
                                )
                            }
                            Surface(
                                color = Gold.copy(alpha = 0.15f),
                                shape = RoundedCornerShape(50)
                            ) {
                                Text(
                                    "演示版",
                                    color = Gold,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                                )
                            }
                        }

                        Text(
                            "配对后可自动同步 Web 管理端配置的邮箱抓取账单与大模型解析结果，并实现多端权威账单协同。",
                            color = Muted,
                            fontSize = 13.sp,
                            lineHeight = 20.sp,
                            modifier = Modifier.padding(bottom = 12.dp)
                        )

                        InfoRow("默认服务地址", syncInfo.serverUrl)

                        Spacer(Modifier.height(14.dp))

                        Button(
                            onClick = onOpenPairDialog,
                            enabled = !busy,
                            colors = ButtonDefaults.buttonColors(
                                containerColor = Gold,
                                contentColor = Ink
                            ),
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(46.dp)
                                .testTag("settings-pair-device-button")
                        ) {
                            Icon(Icons.Outlined.Key, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(8.dp))
                            Text("输入配对码 · 连接云端", fontSize = 14.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }

        // 2. 当前版本
        item {
            Column(Modifier.padding(horizontal = 20.dp)) {
                SectionCard("当前版本功能") {
                    SettingRow(Icons.Outlined.CheckCircle, "本地账单与还款记录", "已可用 · 自动保存在此设备", Green)
                    SettingRow(Icons.Outlined.MailOutline, "邮箱账单 · IMAP", "已接入后台定时收发 · 支持按需检查", Green)
                    SettingRow(Icons.Outlined.AutoAwesome, "智能账单解析与草稿核对", "已接入 · 规则解析与结构化草稿核实", Green)
                    SettingRow(Icons.Outlined.NotificationsNone, "到期通知", "尚未开放 · 当前不会发送提醒", Muted)
                    SettingRow(Icons.Outlined.Lock, "加密备份", "尚未开放 · 卸载或清除数据会丢失记录", Muted)
                }
            }
        }

        // 3. 数据管理
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

        // 4. 数据说明
        item {
            Column(Modifier.padding(horizontal = 20.dp)) {
                SectionCard("数据说明") {
                    Text(
                        "此版本内置演示账单与后台同步，不代表你的真实欠款。还款记录只用于个人管理，不执行真实转账。",
                        color = Muted,
                        fontSize = 13.sp,
                        lineHeight = 22.sp
                    )
                    Spacer(Modifier.height(12.dp))
                    Text(
                        "邮件账单由自建后台抓取并提取草稿，在手机核对原文依据后方可入账。",
                        color = Muted,
                        fontSize = 13.sp,
                        lineHeight = 22.sp
                    )
                }
            }
        }

        item {
            Text(
                "CardCue v0.1.0\nEvery bill. On time.",
                color = Muted,
                fontSize = 12.sp,
                lineHeight = 22.sp,
                modifier = Modifier.padding(horizontal = 26.dp, vertical = 8.dp)
            )
        }
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

    if (showUnpairDialog) {
        AlertDialog(
            onDismissRequest = { showUnpairDialog = false },
            icon = { Icon(Icons.Outlined.LinkOff, contentDescription = null, tint = Red) },
            title = { Text("确认解除设备配对？") },
            text = { Text("解除配对后，本设备将清除与服务器连接的凭据，并恢复为本地演示模式。") },
            confirmButton = {
                TextButton(
                    onClick = {
                        showUnpairDialog = false
                        onUnpair()
                    },
                    modifier = Modifier.testTag("settings-confirm-unpair-button")
                ) {
                    Text("确认解除", color = Red, fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                TextButton(onClick = { showUnpairDialog = false }) {
                    Text("取消")
                }
            }
        )
    }
}

@Composable
private fun InfoRow(
    label: String,
    value: String,
    valueColor: Color = Ink
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            label,
            fontSize = 12.sp,
            color = Muted
        )
        Text(
            value,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium,
            color = valueColor
        )
    }
}

@Composable
private fun SettingRow(icon: ImageVector, title: String, subtitle: String, color: Color) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(icon, null, tint = color, modifier = Modifier.size(22.dp))
        Column(
            Modifier
                .padding(start = 13.dp)
                .weight(1f)
        ) {
            Text(title, fontSize = 14.sp, fontWeight = FontWeight.Medium)
            Text(
                subtitle,
                color = Muted,
                fontSize = 11.sp,
                lineHeight = 18.sp,
                modifier = Modifier.padding(top = 4.dp)
            )
        }
    }
}
