package com.cardcue.app.feature.billing

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
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
import com.cardcue.app.common.ui.*
import com.cardcue.app.data.Bill
import com.cardcue.app.data.Payment
import com.cardcue.app.domain.BillingRules
import com.cardcue.app.domain.Money
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@Composable
fun DetailScreen(bill: Bill, today: LocalDate, busy: Boolean, modifier: Modifier, onBack: () -> Unit, onPay: () -> Unit, onVoid: (String) -> Unit) {
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
