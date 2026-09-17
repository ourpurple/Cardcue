package com.cardcue.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.cardcue.app.CardCueViewModel
import com.cardcue.app.data.Bill
import com.cardcue.app.data.Payment
import com.cardcue.app.domain.BillingRules
import com.cardcue.app.domain.Money
import com.cardcue.app.domain.HomeRules
import kotlinx.coroutines.delay
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val Ink = Color(0xFF17252C)
private val Paper = Color(0xFFF7F5F0)
private val Gold = Color(0xFFDDB56A)
private val Muted = Color(0xFF707A7E)
private val Green = Color(0xFF267566)
private val Red = Color(0xFFB5413D)
private val Line = Color(0xFFE7E5DF)
private val Palette = lightColorScheme(
    primary = Ink, onPrimary = Color.White, secondary = Green,
    background = Paper, surface = Color.White, onSurface = Ink,
    onSurfaceVariant = Muted, outlineVariant = Line, error = Red,
)

@Composable
fun CardCueApp(model: CardCueViewModel) {
    val state by model.state.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var historyFilter by rememberSaveable { mutableIntStateOf(0) }
    var selectedId by rememberSaveable { mutableStateOf<String?>(null) }
    var paymentId by rememberSaveable { mutableStateOf<String?>(null) }
    var syncInfo by rememberSaveable { mutableStateOf(false) }
    var today by remember { mutableStateOf(LocalDate.now()) }
    val snackbar = remember { SnackbarHostState() }
    val selected = state.bills.find { it.statement.id == selectedId }
    LaunchedEffect(Unit) { while (true) { today = LocalDate.now(); delay(60_000) } }
    LaunchedEffect(model) { model.events.collect { snackbar.showSnackbar(it) } }
    BackHandler(enabled = selectedId != null) { selectedId = null }

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
                tab == 0 -> HomeScreen(state.bills, today, pageModifier, onOpen = { selectedId = it }, onPay = { paymentId = it }, onSync = { syncInfo = true })
                tab == 1 -> HistoryScreen(state.bills, historyFilter, pageModifier, onFilter = { historyFilter = it }, onOpen = { selectedId = it })
                else -> SettingsScreen(pageModifier)
            }
        }
        state.bills.find { it.statement.id == paymentId }?.let { bill ->
            PaymentDialog(bill, state.busy, onDismiss = { if (!state.busy) paymentId = null }) { amount, note ->
                model.recordPayment(bill.statement.id, amount, note) { paymentId = null }
            }
        }
        if (syncInfo) AlertDialog(
            onDismissRequest = { syncInfo = false },
            icon = { Icon(Icons.Outlined.MailOutline, null) },
            title = { Text("邮箱接入将在下一阶段开放") },
            text = { Text("当前为本地演示版本，尚未连接新浪邮箱或大模型。你可以先体验账单详情、记录还款和撤销。所有金额均为演示数据。") },
            confirmButton = { TextButton(onClick = { syncInfo = false }) { Text("知道了") } },
        )
    }
}

@Composable
private fun HomeScreen(bills: List<Bill>, today: LocalDate, modifier: Modifier, onOpen: (String) -> Unit, onPay: (String) -> Unit, onSync: () -> Unit) {
    val overview = remember(bills, today) { runCatching { HomeRules.summarize(bills, today) }.getOrNull() }
    if (overview == null) {
        Column(modifier.padding(20.dp)) {
            Text("账单汇总异常", fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Text("金额超出支持范围或账单存在冲突。请在历史中核对记录，当前不显示合计。", modifier = Modifier.padding(top = 12.dp))
        }
        return
    }
    val totals = overview.totals
    val soon = overview.dueSoonCount
    LazyColumn(modifier.testTag("home-list"), contentPadding = PaddingValues(bottom = 16.dp)) {
        item {
            Column(Modifier.testTag("home-header").fillMaxWidth().clip(RoundedCornerShape(bottomStart = 20.dp, bottomEnd = 20.dp)).background(Ink).padding(horizontal = 20.dp, vertical = 10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("CardCue", color = Color.White, fontSize = 22.sp, lineHeight = 28.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.5).sp, modifier = Modifier.weight(1f))
                    Surface(color = Gold.copy(alpha = 0.15f), shape = RoundedCornerShape(50)) {
                        Text("演示版", color = Gold, fontSize = 11.sp, lineHeight = 16.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp))
                    }
                    Spacer(Modifier.width(8.dp))
                    TextButton(onClick = onSync, colors = ButtonDefaults.textButtonColors(contentColor = Gold), contentPadding = PaddingValues(horizontal = 8.dp)) {
                        Icon(Icons.Outlined.Sync, null, Modifier.size(18.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("同步邮箱", fontSize = 12.sp)
                    }
                }
                Spacer(Modifier.height(4.dp))
                Text("待还合计 · 人民币", color = Color(0xFFB7C1C4), fontSize = 12.sp, lineHeight = 16.sp)
                Text(Money.display(totals["CNY"] ?: 0L, "CNY"), color = Color.White, fontSize = 30.sp, lineHeight = 38.sp, fontWeight = FontWeight.Medium, letterSpacing = (-0.5).sp, maxLines = 1, modifier = Modifier.fillMaxWidth().testTag("home-total-CNY"))
                totals.filterKeys { it != "CNY" }.forEach { (currency, amount) ->
                    Text("另有 ${Money.display(amount, currency)} · 单独统计", color = Gold, fontSize = 12.sp, lineHeight = 16.sp, modifier = Modifier.padding(top = 2.dp))
                }
                Text("$soon 笔近期到期 · 未来 7 天（含今天）", color = Color(0xFFB7C1C4), fontSize = 12.sp, lineHeight = 16.sp, modifier = Modifier.padding(top = 8.dp))
            }
        }
        item {
            Row(Modifier.padding(horizontal = 20.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("我的账单", fontSize = 17.sp, lineHeight = 22.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                Text("按还款日排序", fontSize = 11.sp, color = Muted)
            }
        }
        items(overview.bills, key = { it.statement.id }) { bill ->
            BillCard(bill, today, onOpen = { onOpen(bill.statement.id) }, onPay = { onPay(bill.statement.id) })
        }
        item {
            Row(Modifier.padding(horizontal = 26.dp, vertical = 14.dp), verticalAlignment = Alignment.Top) {
                Icon(Icons.Outlined.Info, null, Modifier.size(15.dp), tint = Muted)
                Spacer(Modifier.width(6.dp))
                Text("演示数据 · 尚未同步邮箱\n待还金额根据账单与手动还款记录计算，不是银行实时余额。", fontSize = 11.sp, color = Muted, lineHeight = 18.sp)
            }
        }
    }
}

@Composable
private fun BillCard(bill: Bill, today: LocalDate, onOpen: () -> Unit, onPay: () -> Unit) {
    val s = bill.statement
    val urgent = !bill.settled && BillingRules.daysUntil(LocalDate.parse(s.dueDate), today) <= 3
    Card(onClick = onOpen, modifier = Modifier.testTag("home-bill-${s.id}").fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp), shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(horizontal = 14.dp, vertical = 10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                BankBadge(s.bankMark, Color(s.color), compact = true)
                Column(Modifier.weight(1f).padding(start = 8.dp)) {
                    Text(s.bank, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, lineHeight = 20.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("尾号 ${s.cardTails} · ${s.cycle}", color = Muted, fontSize = 11.sp, lineHeight = 16.sp, maxLines = 1, modifier = Modifier.fillMaxWidth().testTag("home-cards-${s.id}"))
                }
                Icon(Icons.Outlined.ChevronRight, contentDescription = "查看账单", tint = Muted, modifier = Modifier.size(20.dp))
            }
            Spacer(Modifier.height(2.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(Money.display(bill.remaining, s.currency), fontSize = 23.sp, lineHeight = 30.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.5).sp, modifier = Modifier.weight(1f).testTag("home-remaining-${s.id}"))
                Spacer(Modifier.width(8.dp))
                if (!bill.settled) Button(onClick = onPay, modifier = Modifier.testTag("home-pay-${s.id}").defaultMinSize(minHeight = 48.dp), colors = ButtonDefaults.buttonColors(containerColor = Gold.copy(alpha = 0.28f), contentColor = Ink), contentPadding = PaddingValues(horizontal = 12.dp)) {
                    Text("记录还款", fontSize = 12.sp)
                } else Icon(Icons.Outlined.CheckCircle, contentDescription = "已记录还清", tint = Green)
            }
            Text("${BillingRules.dueLabel(LocalDate.parse(s.dueDate), today, bill.settled)} · 还款日 ${s.dueDate}", color = if (bill.settled) Green else if (urgent) Red else Muted, fontSize = 12.sp, lineHeight = 16.sp, maxLines = 1, modifier = Modifier.fillMaxWidth().testTag("home-due-${s.id}"))
            if (s.cardTails.contains("·")) Text("多卡共用账单 · 金额仅统计一次", color = Green, fontSize = 11.sp, lineHeight = 16.sp, modifier = Modifier.padding(top = 2.dp))
        }
    }
}

@Composable
private fun BankBadge(mark: String, color: Color, compact: Boolean = false) {
    Box(Modifier.size(if (compact) 30.dp else 38.dp).clip(CircleShape).background(color.copy(alpha = 0.1f)), contentAlignment = Alignment.Center) {
        Text(mark, color = color, fontWeight = FontWeight.Bold, fontSize = if (compact) 16.sp else 18.sp)
    }
}

@Composable
private fun PageHeader(title: String, subtitle: String, onBack: (() -> Unit)? = null) {
    Column(Modifier.fillMaxWidth().background(Ink).padding(horizontal = 20.dp, vertical = 20.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (onBack != null) IconButton(onClick = onBack, modifier = Modifier.padding(end = 6.dp)) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack, "返回", tint = Color.White)
            }
            Column {
                Text(title, color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Bold)
                Text(subtitle, color = Color(0xFFB7C1C4), fontSize = 12.sp, modifier = Modifier.padding(top = 5.dp))
            }
        }
    }
}

@Composable
private fun HistoryScreen(bills: List<Bill>, filter: Int, modifier: Modifier, onFilter: (Int) -> Unit, onOpen: (String) -> Unit) {
    val filtered = bills.filter { filter == 0 || (filter == 1 && !it.settled) || (filter == 2 && it.settled) }.sortedByDescending { it.statement.dueDate }
    Column(modifier) {
        PageHeader("账单历史", "每期账单，都有迹可循")
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("全部", "待还", "已记录还清").forEachIndexed { index, title -> FilterChip(modifier = Modifier.testTag("history-filter-$index"), selected = filter == index, onClick = { onFilter(index) }, label = { Text(title) }) }
        }
        LazyColumn(contentPadding = PaddingValues(horizontal = 18.dp, vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (filtered.isEmpty()) item { Text("暂时没有这类账单", color = Muted, modifier = Modifier.padding(24.dp)) }
            items(filtered, key = { it.statement.id }) { bill ->
                Card(onClick = { onOpen(bill.statement.id) }, modifier = Modifier.testTag("history-bill-${bill.statement.id}"), colors = CardDefaults.cardColors(containerColor = Color.White), shape = RoundedCornerShape(18.dp)) {
                    Row(Modifier.fillMaxWidth().padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                        BankBadge(bill.statement.bankMark, Color(bill.statement.color))
                        Column(Modifier.weight(1f).padding(horizontal = 10.dp)) {
                            Text(bill.statement.bank, fontSize = 15.sp, fontWeight = FontWeight.Medium)
                            Text("${bill.statement.cycle} · ${bill.statement.cardTails}", fontSize = 10.sp, color = Muted, modifier = Modifier.padding(top = 5.dp))
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text(Money.display(bill.statement.amountMinor, bill.statement.currency), fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                            Text(if (bill.settled) "已记录还清" else "待还", fontSize = 11.sp, color = if (bill.settled) Green else Red, modifier = Modifier.padding(top = 5.dp))
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DetailScreen(bill: Bill, today: LocalDate, busy: Boolean, modifier: Modifier, onBack: () -> Unit, onPay: () -> Unit, onVoid: (String) -> Unit) {
    val s = bill.statement
    var voidId by rememberSaveable { mutableStateOf<String?>(null) }
    Column(modifier.navigationBarsPadding()) {
        PageHeader("账单详情", "${s.bank} · ${s.cycle}", onBack)
        LazyColumn(modifier = Modifier.testTag("bill-detail-list"), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = Color.White), shape = RoundedCornerShape(22.dp)) {
                    Column(Modifier.fillMaxWidth().padding(22.dp)) {
                        Text("当前待还 · ${s.currency}", color = Muted, fontSize = 13.sp)
                        Text(Money.display(bill.remaining, s.currency), fontSize = 35.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.testTag("detail-remaining").padding(vertical = 8.dp))
                        Text(BillingRules.dueLabel(LocalDate.parse(s.dueDate), today, bill.settled), color = if (bill.settled) Green else Red, fontSize = 13.sp)
                        Spacer(Modifier.height(20.dp))
                        Button(onClick = onPay, enabled = !bill.settled && !busy, modifier = Modifier.testTag("detail-pay").fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Gold, contentColor = Ink)) {
                            Text(if (bill.settled) "已记录还清" else "记录还款", modifier = Modifier.padding(vertical = 5.dp))
                        }
                        Text("仅记录你已完成的还款，不执行银行转账。", color = Muted, fontSize = 11.sp, modifier = Modifier.padding(top = 10.dp))
                    }
                }
            }
            item {
                SectionCard("账单信息") {
                    InfoRow("关联卡片", s.cardTails)
                    InfoRow("本期应还", Money.display(s.amountMinor, s.currency))
                    InfoRow("最低还款额", Money.display(s.minimumMinor, s.currency))
                    InfoRow("已记录还款", Money.display(s.amountMinor - bill.remaining, s.currency))
                    InfoRow("账单日期", s.statementDate)
                    InfoRow("到期还款日", s.dueDate)
                    InfoRow("数据来源", s.source)
                    if (s.cardTails.contains("·")) Text("此账户的多张卡共用一份账单，应还金额只统计一次。", fontSize = 12.sp, color = Green, lineHeight = 19.sp, modifier = Modifier.padding(top = 10.dp))
                }
            }
            item { Text("还款记录", fontSize = 18.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 4.dp)) }
            if (bill.payments.isEmpty()) item {
                Text("还没有记录。完成银行还款后，可以在这里记一笔。", fontSize = 13.sp, color = Muted, lineHeight = 21.sp)
            }
            items(bill.payments, key = { it.id }) { payment -> PaymentRow(payment, s.currency, busy, onVoid = { voidId = payment.id }) }
            item { Text("当前账单为演示数据。手动记录不会获取银行实时还款状态。", fontSize = 11.sp, color = Muted, lineHeight = 18.sp) }
        }
    }
    if (voidId != null) AlertDialog(
        onDismissRequest = { voidId = null }, title = { Text("撤销这笔记录？") },
        text = { Text("撤销后将重新计算待还金额，原记录会保留并标注已撤销。这不会撤回任何银行交易。") },
        dismissButton = { TextButton(onClick = { voidId = null }) { Text("保留记录") } },
        confirmButton = { TextButton(onClick = { voidId?.let(onVoid); voidId = null }, enabled = !busy, modifier = Modifier.testTag("void-confirm")) { Text("撤销记录", color = Red) } },
    )
}

@Composable
private fun PaymentRow(payment: Payment, currency: String, busy: Boolean, onVoid: () -> Unit) {
    val date = Instant.ofEpochMilli(payment.recordedAt).atZone(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"))
    Surface(shape = RoundedCornerShape(16.dp), color = Color.White) {
        Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(Money.display(payment.amountMinor, currency), fontSize = 19.sp, fontWeight = FontWeight.SemiBold, color = if (payment.voidedAt != null) Muted else Ink)
                Text(date, fontSize = 11.sp, color = Muted, modifier = Modifier.padding(top = 5.dp))
                if (payment.note.isNotBlank()) Text(payment.note, fontSize = 12.sp, color = Muted, modifier = Modifier.padding(top = 5.dp))
            }
            if (payment.voidedAt != null) Text("已撤销", fontSize = 12.sp, color = Muted, modifier = Modifier.testTag("payment-voided-${payment.id}"))
            else TextButton(onClick = onVoid, enabled = !busy, modifier = Modifier.testTag("payment-void-${payment.id}")) { Text("撤销") }
        }
    }
}

@Composable
private fun PaymentDialog(bill: Bill, busy: Boolean, onDismiss: () -> Unit, onConfirm: (Long, String) -> Unit) {
    var amount by rememberSaveable(bill.statement.id) { mutableStateOf(Money.input(bill.remaining)) }
    var note by rememberSaveable(bill.statement.id) { mutableStateOf("") }
    val parsed = Money.parse(amount)
    val valid = parsed != null && parsed <= bill.remaining && note.length <= 120
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("记录还款") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text("${bill.statement.bank} · ${bill.statement.currency}\n待还 ${Money.display(bill.remaining, bill.statement.currency)}", color = Muted, lineHeight = 22.sp)
                Spacer(Modifier.height(16.dp))
                OutlinedTextField(value = amount, onValueChange = { amount = it }, label = { Text("已还金额") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), enabled = !busy,
                    isError = !valid && amount.isNotEmpty(), modifier = Modifier.testTag("payment-amount").fillMaxWidth(),
                    supportingText = { Text(if (parsed != null && parsed > bill.remaining) "不能超过当前待还金额" else "支持部分还款，最多两位小数") })
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = note, onValueChange = { if (it.length <= 120) note = it }, label = { Text("备注（选填）") }, enabled = !busy,
                    modifier = Modifier.testTag("payment-note").fillMaxWidth(), maxLines = 3)
                Text("确认前请核实银行实际还款情况。", fontSize = 11.sp, color = Muted, modifier = Modifier.padding(top = 14.dp))
            }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy, modifier = Modifier.testTag("payment-cancel")) { Text("取消") } },
        confirmButton = { Button(onClick = { parsed?.let { onConfirm(it, note) } }, enabled = valid && !busy, modifier = Modifier.testTag("payment-save")) { Text(if (busy) "保存中…" else "保存记录") } },
    )
}

@Composable
private fun SettingsScreen(modifier: Modifier) {
    LazyColumn(modifier, contentPadding = PaddingValues(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { PageHeader("我的 CardCue", "一个安静、清楚的私人账单本") }
        item {
            Column(Modifier.padding(horizontal = 20.dp)) {
                SectionCard("当前版本") {
                    SettingRow(Icons.Outlined.CheckCircle, "本地账单与还款记录", "已可用 · 自动保存在此设备", Green)
                    SettingRow(Icons.Outlined.MailOutline, "新浪邮箱 · IMAP", "下一阶段接入 · 当前未读取邮箱", Muted)
                    SettingRow(Icons.Outlined.AutoAwesome, "智能账单解析", "下一阶段接入 · 当前未调用模型", Muted)
                    SettingRow(Icons.Outlined.NotificationsNone, "到期通知", "尚未开放 · 当前不会发送提醒", Muted)
                    SettingRow(Icons.Outlined.Lock, "加密备份", "尚未开放 · 卸载或清除数据会丢失记录", Muted)
                }
            }
        }
        item {
            Column(Modifier.padding(horizontal = 20.dp)) {
                SectionCard("数据说明") {
                    Text("此版本内置演示账单，不代表你的真实欠款。还款记录只用于本地管理，不执行转账。", color = Muted, fontSize = 13.sp, lineHeight = 22.sp)
                    Spacer(Modifier.height(12.dp))
                    Text("当前版本不联网，不收集邮箱凭证，也不上传账单。", color = Muted, fontSize = 13.sp, lineHeight = 22.sp)
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

@Composable
private fun SectionCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Surface(shape = RoundedCornerShape(20.dp), color = Color.White) {
        Column(Modifier.fillMaxWidth().padding(20.dp)) {
            Text(title, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(12.dp))
            content()
        }
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 9.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(label, color = Muted, fontSize = 13.sp, modifier = Modifier.weight(0.42f))
        Text(value, color = Ink, fontSize = 13.sp, modifier = Modifier.weight(0.58f))
    }
}
