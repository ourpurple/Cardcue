package com.cardcue.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.cardcue.app.CardCueViewModel
import com.cardcue.app.common.ui.*
import com.cardcue.app.feature.billing.DetailScreen
import com.cardcue.app.feature.billing.PaymentDialog
import com.cardcue.app.feature.history.HistoryScreen
import com.cardcue.app.feature.home.DraftReviewDialog
import com.cardcue.app.feature.home.HomeScreen
import com.cardcue.app.feature.settings.PairingDialog
import com.cardcue.app.feature.settings.SettingsScreen
import kotlinx.coroutines.delay
import java.time.LocalDate

@Composable
fun CardCueApp(model: CardCueViewModel) {
    val state by model.state.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var historyFilter by rememberSaveable { mutableIntStateOf(0) }
    var selectedId by rememberSaveable { mutableStateOf<String?>(null) }
    var paymentId by rememberSaveable { mutableStateOf<String?>(null) }
    var reviewingDraftId by rememberSaveable { mutableStateOf<String?>(null) }
    var syncInfoDialog by rememberSaveable { mutableStateOf(false) }
    var showPairingDialog by rememberSaveable { mutableStateOf(false) }
    var today by remember { mutableStateOf(LocalDate.now()) }
    val snackbar = remember { SnackbarHostState() }
    val syncInfo by model.syncInfo.collectAsStateWithLifecycle()
    val pendingDrafts by model.pendingDrafts.collectAsStateWithLifecycle()
    val syncedAccounts by model.syncedAccounts.collectAsStateWithLifecycle()
    val syncedCards by model.syncedCards.collectAsStateWithLifecycle()

    val selected = state.bills.find { it.statement.id == selectedId }
    LaunchedEffect(Unit) { while (true) { today = LocalDate.now(); delay(60_000) } }
    LaunchedEffect(model) { model.events.collect { snackbar.showSnackbar(it) } }
    BackHandler(enabled = selectedId != null || reviewingDraftId != null) {
        if (reviewingDraftId != null) reviewingDraftId = null
        else selectedId = null
    }

    MaterialTheme(colorScheme = Palette) {
        Scaffold(
            modifier = Modifier.background(Ink).statusBarsPadding(),
            containerColor = Paper,
            contentWindowInsets = WindowInsets(0, 0, 0, 0),
            snackbarHost = { SnackbarHost(snackbar) },
            bottomBar = {
                if (selectedId == null) NavigationBar(containerColor = Paper, tonalElevation = 0.dp) {
                    listOf("账单" to Icons.Outlined.CreditCard, "历史" to Icons.Outlined.History, "设置" to Icons.Outlined.Tune)
                        .forEachIndexed { index, (label, icon) ->
                            NavigationBarItem(
                                modifier = Modifier.testTag("tab-$index"),
                                selected = tab == index, onClick = { tab = index },
                                icon = { Icon(icon, contentDescription = null) },
                                label = { Text(label) },
                                colors = NavigationBarItemDefaults.colors(indicatorColor = Gold.copy(alpha = 0.25f), selectedIconColor = Ink, selectedTextColor = Ink),
                            )
                        }
                }
            },
        ) { padding ->
            val pageModifier = Modifier.fillMaxSize().padding(padding)
            when {
                state.loading -> Column(pageModifier.background(Ink), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                    Text("CardCue", color = Gold, fontSize = 32.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(24.dp))
                    CircularProgressIndicator(color = Gold)
                }
                state.error != null -> Column(pageModifier.background(Ink).padding(24.dp)) {
                    Text("CardCue", color = Gold, fontSize = 28.sp)
                    Spacer(Modifier.height(24.dp))
                    Text(state.error ?: "", color = Color.White)
                }
                selected != null -> DetailScreen(selected, today, state.busy, pageModifier,
                    onBack = { selectedId = null }, onPay = { paymentId = selected.statement.id },
                    onVoid = model::voidPayment)
                tab == 0 -> HomeScreen(
                    bills = state.bills,
                    today = today,
                    syncInfo = syncInfo,
                    pendingDrafts = pendingDrafts,
                    modifier = pageModifier,
                    onOpen = { selectedId = it },
                    onPay = { paymentId = it },
                    onSync = { model.syncNow(); syncInfoDialog = true },
                    onReviewDraft = { reviewingDraftId = it.id }
                )
                tab == 1 -> HistoryScreen(state.bills, historyFilter, pageModifier, onFilter = { historyFilter = it }, onOpen = { selectedId = it })
                else -> SettingsScreen(
                    syncInfo = syncInfo,
                    busy = state.busy,
                    modifier = pageModifier,
                    onOpenPairDialog = { showPairingDialog = true },
                    onSyncNow = { model.syncNow() },
                    onUnpair = { model.unpairDevice() },
                    onResetAllData = { model.resetAllData() }
                )
            }
        }
        state.bills.find { it.statement.id == paymentId }?.let { bill ->
            PaymentDialog(bill, state.busy, onDismiss = { if (!state.busy) paymentId = null }) { amount, note ->
                model.recordPayment(bill.statement.id, amount, note) { paymentId = null }
            }
        }
        pendingDrafts.find { it.id == reviewingDraftId }?.let { draft ->
            DraftReviewDialog(
                draft = draft,
                accounts = syncedAccounts,
                cards = syncedCards,
                busy = state.busy,
                onDismiss = { reviewingDraftId = null },
                onConfirm = { req ->
                    model.confirmDraft(draft.id, req) {
                        reviewingDraftId = null
                    }
                },
                onReject = { reason ->
                    model.rejectDraft(draft.id, reason) {
                        reviewingDraftId = null
                    }
                }
            )
        }
        if (syncInfoDialog) AlertDialog(
            onDismissRequest = { syncInfoDialog = false },
            icon = { Icon(Icons.Outlined.Sync, null, tint = Gold) },
            title = { Text("数据同步与服务状态") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("服务地址: ${syncInfo.serverUrl}", fontSize = 13.sp, color = Ink)
                    Text(
                        "设备状态: ${if (syncInfo.isPaired) "已配对 (${syncInfo.deviceId?.take(8)}...)" else "未配对 (需要输入配对码)"}",
                        fontSize = 13.sp,
                        color = if (syncInfo.isPaired) Ink else Red
                    )
                    Text("同步状态: ${when (syncInfo.state) {
                        com.cardcue.app.sync.SyncState.SYNCING -> "正在同步数据..."
                        com.cardcue.app.sync.SyncState.SUCCESS -> "数据已是最新"
                        com.cardcue.app.sync.SyncState.OFFLINE -> "离线只读 (服务器未连接)"
                        com.cardcue.app.sync.SyncState.ERROR -> "同步异常: ${syncInfo.message ?: "未知错误"}"
                        com.cardcue.app.sync.SyncState.IDLE -> "就绪"
                    }}", fontSize = 13.sp, color = if (syncInfo.state == com.cardcue.app.sync.SyncState.OFFLINE) Red else Ink)
                    Text("上次同步: ${syncInfo.lastSyncTime ?: "尚未同步"}", fontSize = 12.sp, color = Muted)
                    Spacer(Modifier.height(4.dp))
                    Text("CardCue 权威数据存储在后台服务器，本地为离线只读缓存。后台支持定时收取邮件、大模型解析并生成草稿，手机核对原文依据后入账。", fontSize = 11.sp, color = Muted, lineHeight = 16.sp)
                }
            },
            dismissButton = {
                Row {
                    TextButton(onClick = { syncInfoDialog = false }) { Text("关闭") }
                    if (syncInfo.isPaired) {
                        Spacer(Modifier.width(4.dp))
                        TextButton(
                            onClick = { model.parsePendingEmails() },
                            enabled = syncInfo.state != com.cardcue.app.sync.SyncState.SYNCING
                        ) { Text("解析邮件") }
                    }
                }
            },
            confirmButton = {
                Row {
                    if (!syncInfo.isPaired) {
                        Button(
                            onClick = {
                                syncInfoDialog = false
                                showPairingDialog = true
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = Gold, contentColor = Ink),
                            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
                        ) {
                            Icon(Icons.Outlined.Key, null, Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("输入配对码", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                        }
                    } else {
                        TextButton(
                            onClick = { model.checkNewEmails() },
                            enabled = syncInfo.state != com.cardcue.app.sync.SyncState.SYNCING
                        ) { Text("收取邮件") }
                        Spacer(Modifier.width(4.dp))
                        TextButton(
                            onClick = { model.syncNow() },
                            enabled = syncInfo.state != com.cardcue.app.sync.SyncState.SYNCING
                        ) { Text("立即同步") }
                    }
                }
            },
        )
        if (showPairingDialog) {
            PairingDialog(
                currentServerUrl = syncInfo.serverUrl,
                busy = state.busy,
                onDismiss = { showPairingDialog = false },
                onConfirmPair = { serverUrl, pairingCode, deviceName, onError ->
                    model.pairDevice(
                        serverUrl = serverUrl,
                        pairingCode = pairingCode,
                        deviceName = deviceName.ifBlank { null },
                        onSuccess = { showPairingDialog = false },
                        onError = { err -> onError(err) }
                    )
                }
            )
        }
    }
}