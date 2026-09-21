package com.cardcue.app.feature.settings

import android.os.Build
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.cardcue.app.common.ui.*
import com.cardcue.app.sync.SyncManager

@Composable
fun PairingDialog(
    currentServerUrl: String,
    busy: Boolean,
    onDismiss: () -> Unit,
    onConfirmPair: (serverUrl: String, pairingCode: String, deviceName: String, onError: (String) -> Unit) -> Unit,
) {
    var serverUrl by remember {
        mutableStateOf(currentServerUrl.ifBlank { SyncManager.DEFAULT_SERVER_URL })
    }
    var pairingCode by remember { mutableStateOf("") }
    val defaultDeviceName = remember { "CardCue Android ()" }
    var deviceName by remember { mutableStateOf(defaultDeviceName) }
    var localError by remember { mutableStateOf<String?>(null) }
    val clipboardManager = LocalClipboardManager.current

    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        shape = RoundedCornerShape(20.dp),
        icon = {
            Icon(
                Icons.Outlined.Key,
                contentDescription = null,
                tint = Gold,
                modifier = Modifier.size(28.dp)
            )
        },
        title = {
            Text(
                "连接云端服务",
                fontWeight = FontWeight.Bold,
                fontSize = 18.sp
            )
        },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(14.dp)
            ) {
                Surface(
                    color = Gold.copy(alpha = 0.1f),
                    shape = RoundedCornerShape(10.dp)
                ) {
                    Row(
                        modifier = Modifier.padding(10.dp),
                        verticalAlignment = Alignment.Top
                    ) {
                        Icon(
                            Icons.Outlined.Info,
                            contentDescription = null,
                            tint = Gold,
                            modifier = Modifier.size(16.dp).padding(top = 2.dp)
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            "提示：请在 Web 管理后台「移动设备管理」点击「生成 Android 设备配对码」（10 分钟内有效），复制后填入下方即可。",
                            color = Ink,
                            fontSize = 12.sp,
                            lineHeight = 17.sp
                        )
                    }
                }

                OutlinedTextField(
                    value = serverUrl,
                    onValueChange = {
                        serverUrl = it
                        localError = null
                    },
                    label = { Text("VPS 服务端地址") },
                    placeholder = { Text("http://ip:8000 或 https://domain") },
                    leadingIcon = {
                        Icon(
                            Icons.Outlined.Dns,
                            contentDescription = null,
                            tint = Muted,
                            modifier = Modifier.size(20.dp)
                        )
                    },
                    singleLine = true,
                    enabled = !busy,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("pair-server-url-input"),
                    shape = RoundedCornerShape(10.dp)
                )

                OutlinedTextField(
                    value = pairingCode,
                    onValueChange = {
                        pairingCode = it.trim()
                        localError = null
                    },
                    label = { Text("一次性配对码") },
                    placeholder = { Text("从 Web 后台复制后点击右侧粘贴") },
                    leadingIcon = {
                        Icon(
                            Icons.Outlined.Key,
                            contentDescription = null,
                            tint = Gold,
                            modifier = Modifier.size(20.dp)
                        )
                    },
                    trailingIcon = {
                        IconButton(
                            onClick = {
                                val clip = clipboardManager.getText()?.text
                                if (!clip.isNullOrBlank()) {
                                    pairingCode = clip.trim()
                                    localError = null
                                }
                            },
                            enabled = !busy
                        ) {
                            Icon(
                                Icons.Outlined.ContentPaste,
                                contentDescription = "粘贴剪贴板",
                                tint = if (busy) Muted else Gold,
                                modifier = Modifier.size(20.dp)
                            )
                        }
                    },
                    singleLine = true,
                    enabled = !busy,
                    textStyle = LocalTextStyle.current.copy(
                        fontFamily = FontFamily.Monospace,
                        letterSpacing = 1.sp
                    ),
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("pair-code-input"),
                    shape = RoundedCornerShape(10.dp)
                )

                OutlinedTextField(
                    value = deviceName,
                    onValueChange = {
                        deviceName = it
                    },
                    label = { Text("设备名称 (选填)") },
                    placeholder = { Text("例如：我的主力手机") },
                    leadingIcon = {
                        Icon(
                            Icons.Outlined.Smartphone,
                            contentDescription = null,
                            tint = Muted,
                            modifier = Modifier.size(20.dp)
                        )
                    },
                    singleLine = true,
                    enabled = !busy,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("pair-device-name-input"),
                    shape = RoundedCornerShape(10.dp)
                )

                if (localError != null) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            Icons.Outlined.ErrorOutline,
                            contentDescription = null,
                            tint = Red,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(Modifier.width(6.dp))
                        Text(
                            localError ?: "",
                            color = Red,
                            fontSize = 12.sp,
                            lineHeight = 16.sp
                        )
                    }
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val cleanUrl = serverUrl.trim().removeSuffix("/")
                    val cleanCode = pairingCode.trim()
                    if (cleanUrl.isBlank() || (!cleanUrl.startsWith("http://") && !cleanUrl.startsWith("https://"))) {
                        localError = "请输入正确的服务端地址 (需以 http:// 或 https:// 开头)"
                        return@Button
                    }
                    if (cleanCode.length < 20) {
                        localError = "配对码格式不正确 (至少 20 位字符)"
                        return@Button
                    }
                    localError = null
                    onConfirmPair(cleanUrl, cleanCode, deviceName.trim()) { err ->
                        localError = err
                    }
                },
                enabled = !busy && pairingCode.isNotBlank(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = Gold,
                    contentColor = Ink,
                    disabledContainerColor = Muted.copy(alpha = 0.2f),
                    disabledContentColor = Muted
                ),
                shape = RoundedCornerShape(10.dp),
                modifier = Modifier.testTag("pair-confirm-button")
            ) {
                if (busy) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        color = Ink,
                        strokeWidth = 2.dp
                    )
                    Spacer(Modifier.width(6.dp))
                    Text("配对中...", fontSize = 13.sp, fontWeight = FontWeight.Bold)
                } else {
                    Icon(Icons.Outlined.Link, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("立即配对", fontSize = 13.sp, fontWeight = FontWeight.Bold)
                }
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !busy
            ) {
                Text("取消", color = Muted)
            }
        }
    )
}