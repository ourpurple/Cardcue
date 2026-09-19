package com.cardcue.app.feature.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material.icons.outlined.Sync
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
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
                    Text("另有  · 单独统计", color = Gold, fontSize = 12.sp, lineHeight = 16.sp, modifier = Modifier.padding(top = 2.dp))
                }
                Text(" 笔近期到期 · 未来 7 天（含今天）", color = Color(0xFFB7C1C4), fontSize = 12.sp, lineHeight = 16.sp, modifier = Modifier.padding(top = 8.dp))
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
                            Text("待核对账单草稿 ()", fontWeight = FontWeight.Bold, fontSize = 13.sp, color = Ink)
                            Text(
                                " · 点击查看原文依据并入账",
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
                    Text("尾号  · ", color = Muted, fontSize = 11.sp, lineHeight = 16.sp, maxLines = 1, modifier = Modifier.fillMaxWidth().testTag("home-cards-${s.id}"))
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
            Text(" · 还款日 ", color = if (bill.settled) Green else if (urgent) Red else Muted, fontSize = 12.sp, lineHeight = 16.sp, maxLines = 1, modifier = Modifier.fillMaxWidth().testTag("home-due-${s.id}"))
            if (s.cardTails.contains("·")) Text("多卡共用账单 · 金额仅统计一次", color = Green, fontSize = 11.sp, lineHeight = 16.sp, modifier = Modifier.padding(top = 2.dp))
        }
    }
}
