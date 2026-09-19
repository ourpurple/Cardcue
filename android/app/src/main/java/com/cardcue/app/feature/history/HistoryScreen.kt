package com.cardcue.app.feature.history

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.cardcue.app.common.ui.*
import com.cardcue.app.data.Bill
import com.cardcue.app.domain.Money

@Composable
fun HistoryScreen(bills: List<Bill>, filter: Int, modifier: Modifier, onFilter: (Int) -> Unit, onOpen: (String) -> Unit) {
    val filtered = when (filter) {
        1 -> bills.filterNot { it.settled }
        2 -> bills.filter { it.settled }
        else -> bills
    }.sortedByDescending { it.statement.dueDate }
    Column(modifier) {
        PageHeader("账单历史", "每期账单，都有迹可循")
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("全部", "待还", "已还清").forEachIndexed { index, label ->
                FilterChip(
                    modifier = Modifier.testTag("history-filter-$index"),
                    selected = filter == index, onClick = { onFilter(index) },
                    label = { Text(label) },
                    colors = FilterChipDefaults.filterChipColors(selectedContainerColor = Gold.copy(alpha = 0.35f)),
                )
            }
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
