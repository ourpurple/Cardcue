package com.cardcue.app.feature.billing

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.cardcue.app.common.ui.Muted
import com.cardcue.app.data.Bill
import com.cardcue.app.domain.Money

@Composable
fun PaymentDialog(bill: Bill, busy: Boolean, onDismiss: () -> Unit, onConfirm: (Long, String) -> Unit) {
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
