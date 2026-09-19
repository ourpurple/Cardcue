package com.cardcue.app.feature.home

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.MoreHoriz
import androidx.compose.material.icons.outlined.Sync
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.cardcue.app.common.ui.*
import com.cardcue.app.data.Bill
import com.cardcue.app.domain.BillingRules
import com.cardcue.app.domain.HomeRules
import com.cardcue.app.domain.Money
import com.cardcue.app.sync.StatementDraftDto
import com.cardcue.app.sync.SyncInfo
import com.cardcue.app.sync.SyncState
import java.time.LocalDate

@Composable
fun HomeScreen(
    bills: List<Bill>,
    today: LocalDate,
    syncInfo: SyncInfo = SyncInfo(),
    pendingDrafts: List<StatementDraftDto> = emptyList(),
    modifier: Modifier = Modifier,
    onOpen: (String) -> Unit,
    onPay: (String) -> Unit,
    onSync: () -> Unit,
    onReviewDraft: (StatementDraftDto) -> Unit = {}
) {
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
                    val badgeLabel = when {
                        syncInfo.state == SyncState.SYNCING -> "同步中"
                        syncInfo.state == SyncState.OFFLINE -> "离线缓存"
                        syncInfo.isPaired -> "已连接"
                        else -> "演示版"
                    }
                    val badgeColor = if (syncInfo.state == SyncState.OFFLINE) Red else Gold
                    Surface(color = badgeColor.copy(alpha = 0.15f), shape = RoundedCornerShape(50)) {
                        Text(badgeLabel, color = badgeColor, fontSize = 11.sp, lineHeight = 16.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp))
                    }
                    Spacer(Modifier.width(8.dp))
                    TextButton(onClick = onSync, colors = ButtonDefaults.textButtonColors(contentColor = Gold), contentPadding = PaddingValues(horizontal = 8.dp), modifier = Modifier.testTag("home-sync-button")) {
                        if (syncInfo.state == SyncState.SYNCING) {
                            CircularProgressIndicator(color = Gold, strokeWidth = 2.dp, modifier = Modifier.size(14.dp))
                            Spacer(Modifier.width(4.dp))
                        } else {
                            Icon(Icons.Outlined.Sync, null, Modifier.size(18.dp))
                            Spacer(Modifier.width(4.dp))
                        }
                        Text(if (syncInfo.state == SyncState.SYNCING) "同步中" else "同步账单", fontSize = 12.sp)
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
        if (pendingDrafts.isNotEmpty()) {
            item {
                Card(
                    onClick = { onReviewDraft(pendingDrafts.first()) },
                    modifier = Modifier
                        .testTag("home-draft-banner")
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 6.dp),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = Gold.copy(alpha = 0.18f))
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Outlined.AutoAwesome, contentDescription = null, tint = Ink, modifier = Modifier.size(20.dp))
                        Spacer(Modifier.width(10.dp))
                        Column(Modifier.weight(1f)) {
                            Text("待核对账单草稿 (${pendingDrafts.size})", fontWeight = FontWeight.Bold, fontSize = 13.sp, color = Ink)
                            Text(
                                "${pendingDrafts.first().bank} · 点击查看原文依据并入账",
                                fontSize = 11.sp,
                                color = Muted,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                        TextButton(
                            onClick = { onReviewDraft(pendingDrafts.first()) },
                            contentPadding = PaddingValues(horizontal = 6.dp),
                            modifier = Modifier.testTag("home-review-draft-button")
                        ) {
                            Text("立即核对", fontSize = 12.sp, color = Ink, fontWeight = FontWeight.Bold)
                        }
                    }
                }
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
                Icon(Icons.Outlined.CheckCircle, null, tint = Green, modifier = Modifier.size(16.dp))
                Text("所有金额以整数最小单位存储。还款记录仅保存在本地设备，撤销后恢复待还余额。", color = Muted, fontSize = 11.sp, lineHeight = 17.sp, modifier = Modifier.padding(start = 8.dp))
            }
        }
    }
}

fun shortBankName(bank: String): String = when {
    bank.contains("农业") || bank.contains("农行") -> "农行"
    bank.contains("中国银行") || bank.contains("中行") -> "中行"
    bank.contains("中信") -> "中信"
    bank.contains("工商") || bank.contains("工行") -> "工行"
    bank.contains("建设") || bank.contains("建行") -> "建行"
    bank.contains("交通") || bank.contains("交行") -> "交行"
    bank.contains("招商") || bank.contains("招行") -> "招行"
    bank.contains("广发") -> "广发"
    bank.contains("浦发") || bank.contains("浦东发展") -> "浦发"
    bank.contains("民生") -> "民生"
    bank.contains("光大") -> "光大"
    bank.contains("平安") -> "平安"
    bank.contains("兴业") -> "兴业"
    bank.contains("华夏") -> "华夏"
    bank.contains("邮政") || bank.contains("邮储") -> "邮储"
    bank.contains("北京") -> "北京"
    bank.contains("上海") -> "上海"
    bank.contains("江苏") -> "江苏"
    bank.contains("浙商") -> "浙商"
    bank.contains("宁波") -> "宁波"
    bank.endsWith("银行") -> bank.removeSuffix("银行")
    else -> bank
}

@Composable
private fun BillCard(bill: Bill, today: LocalDate, onOpen: () -> Unit, onPay: () -> Unit) {
    val s = bill.statement
    val isNew = !s.isDemo && runCatching {
        val stDate = LocalDate.parse(s.statementDate)
        val diff = java.time.temporal.ChronoUnit.DAYS.between(stDate, today)
        diff in 0..20
    }.getOrDefault(false)

    val dueDate = runCatching { LocalDate.parse(s.dueDate) }.getOrNull()
    val daysUntil = if (dueDate != null) BillingRules.daysUntil(dueDate, today) else 999L
    val isCoral = daysUntil in -999L..2L

    Card(
        onClick = onOpen,
        modifier = Modifier
            .testTag("home-bill-${s.id}")
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 6.dp),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White)
    ) {
        Box(Modifier.fillMaxWidth()) {
            if (isNew) {
                Box(
                    modifier = Modifier
                        .size(46.dp)
                        .align(Alignment.TopStart)
                        .clip(RoundedCornerShape(topStart = 16.dp))
                ) {
                    Canvas(modifier = Modifier.fillMaxSize()) {
                        val path = Path().apply {
                            moveTo(0f, size.height * 0.72f)
                            lineTo(size.width * 0.72f, 0f)
                            lineTo(size.width, 0f)
                            lineTo(0f, size.height)
                            close()
                        }
                        drawPath(path, Color(0xFF00C800))
                    }
                    Text(
                        text = "new",
                        color = Color.White,
                        fontSize = 9.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier
                            .align(Alignment.Center)
                            .offset(x = (-6).dp, y = (-6).dp)
                            .rotate(-45f)
                    )
                }
            }

            Column(Modifier.padding(horizontal = 16.dp, vertical = 14.dp)) {
                // Top row: BankBadge + Bank Name + Cardholder + Tails + MoreHoriz icon
                Row(verticalAlignment = Alignment.CenterVertically) {
                    BankBadge(s.bankMark, Color(s.color), compact = true)
                    Spacer(Modifier.width(8.dp))
                    val titleText = buildString {
                        append(shortBankName(s.bank))
                        if (!bill.cardHolder.isNullOrBlank()) {
                            append(" ").append(bill.cardHolder)
                        }
                        if (s.cardTails.isNotBlank()) {
                            append(" ").append(s.cardTails)
                        }
                    }
                    Text(
                        text = titleText,
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 15.sp,
                        lineHeight = 20.sp,
                        color = Ink,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier
                            .weight(1f)
                            .testTag("home-cards-${s.id}")
                    )
                    IconButton(
                        onClick = onOpen,
                        modifier = Modifier.size(24.dp)
                    ) {
                        Icon(
                            Icons.Outlined.MoreHoriz,
                            contentDescription = "更多",
                            tint = Color(0xFFC7C7CC),
                            modifier = Modifier.size(20.dp)
                        )
                    }
                }

                Spacer(Modifier.height(12.dp))

                // Middle row: 3 columns
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Col 1: Amount & "本期账单"
                    Column(modifier = Modifier.weight(1.1f)) {
                        val amountText = when {
                            bill.remaining > 0L -> {
                                if (s.currency == "CNY") {
                                    String.format(java.util.Locale.US, "%.2f", bill.remaining / 100.0)
                                } else {
                                    Money.display(bill.remaining, s.currency)
                                }
                            }
                            s.amountMinor == 0L -> "待更新"
                            bill.settled -> "0.00"
                            else -> "待更新"
                        }
                        Text(
                            text = amountText,
                            fontSize = 22.sp,
                            lineHeight = 26.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = (-0.5).sp,
                            color = if (amountText == "待更新") Color(0xFF8C8C8C) else Ink,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.testTag("home-remaining-${s.id}")
                        )
                        Spacer(Modifier.height(2.dp))
                        Text(
                            text = "本期账单",
                            fontSize = 11.sp,
                            lineHeight = 14.sp,
                            color = Color(0xFF8C8C8C)
                        )
                    }

                    // Col 2: Countdown & Due Date
                    val countdownChar = when {
                        daysUntil < 0L -> "${-daysUntil}"
                        daysUntil == 0L -> "今"
                        daysUntil == 1L -> "明"
                        daysUntil == 2L -> "后"
                        else -> "$daysUntil"
                    }
                    val countdownUnit = when {
                        daysUntil < 0L -> "天逾期"
                        daysUntil in 0L..2L -> "天到期"
                        else -> "天后到期"
                    }
                    val dateText = if (dueDate != null) {
                        String.format(java.util.Locale.US, "%02d-%02d", dueDate.monthValue, dueDate.dayOfMonth)
                    } else {
                        s.dueDate
                    }

                    Row(
                        modifier = Modifier.weight(1f),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = countdownChar,
                            fontSize = 28.sp,
                            lineHeight = 32.sp,
                            fontWeight = FontWeight.Normal,
                            color = if (isCoral) Color(0xFFE85D4E) else Color(0xFF262626)
                        )
                        Spacer(Modifier.width(4.dp))
                        Column {
                            Text(
                                text = countdownUnit,
                                fontSize = 11.sp,
                                lineHeight = 14.sp,
                                color = if (isCoral) Color(0xFFE85D4E) else Color(0xFF595959)
                            )
                            Text(
                                text = dateText,
                                fontSize = 11.sp,
                                lineHeight = 14.sp,
                                color = Color(0xFF8C8C8C),
                                maxLines = 1,
                                modifier = Modifier.testTag("home-due-${s.id}")
                            )
                        }
                    }

                    // Col 3: Action Button (Pill)
                    val pillBg: Color
                    val pillText: String
                    val pillTextColor: Color
                    when {
                        bill.remaining > 0L -> {
                            pillBg = Color(0xFFEAA655)
                            pillText = "还款"
                            pillTextColor = Color.White
                        }
                        bill.settled -> {
                            pillBg = Color(0xFFE8F5E9)
                            pillText = "已还清"
                            pillTextColor = Color(0xFF2E7D32)
                        }
                        else -> {
                            pillBg = Color(0xFFEDF3FC)
                            pillText = "更新账单"
                            pillTextColor = Color(0xFF2E82E5)
                        }
                    }

                    Button(
                        onClick = { if (bill.remaining > 0L) onPay() else onOpen() },
                        shape = RoundedCornerShape(50),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = pillBg,
                            contentColor = pillTextColor
                        ),
                        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 0.dp),
                        modifier = Modifier
                            .testTag("home-pay-${s.id}")
                            .defaultMinSize(minHeight = 48.dp, minWidth = 76.dp)
                    ) {
                        Text(
                            text = pillText,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Medium
                        )
                    }
                }

                if (s.cardTails.contains("·")) {
                    Text(
                        text = "多卡共用账单 · 金额仅统计一次",
                        color = Green,
                        fontSize = 11.sp,
                        lineHeight = 16.sp,
                        modifier = Modifier.padding(top = 8.dp)
                    )
                }
            }
        }
    }
}
