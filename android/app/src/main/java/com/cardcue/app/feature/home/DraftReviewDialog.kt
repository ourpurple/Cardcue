package com.cardcue.app.feature.home

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.cardcue.app.common.ui.*
import com.cardcue.app.data.SyncedAccount
import com.cardcue.app.data.SyncedCard
import com.cardcue.app.domain.Money
import com.cardcue.app.sync.EvidenceSnippetDto
import com.cardcue.app.sync.StatementDraftConfirmRequestDto
import com.cardcue.app.sync.StatementDraftDto
import java.math.BigDecimal
import java.time.LocalDate

@Composable
fun DraftReviewDialog(
    draft: StatementDraftDto,
    accounts: List<SyncedAccount>,
    cards: List<SyncedCard>,
    busy: Boolean,
    onDismiss: () -> Unit,
    onConfirm: (StatementDraftConfirmRequestDto) -> Unit,
    onReject: (String) -> Unit,
) {
    // 1. Account matching
    val initialAccountId = remember(draft, accounts) {
        draft.matchedAccountId?.takeIf { id -> accounts.any { it.id == id } }
            ?: accounts.find { it.bank == draft.bank }?.id
            ?: accounts.firstOrNull()?.id
    }
    var selectedAccountId by rememberSaveable(draft.id) { mutableStateOf(initialAccountId) }
    var accountMenuExpanded by remember { mutableStateOf(false) }

    // 2. Editable fields
    var amountText by rememberSaveable(draft.id) {
        mutableStateOf(draft.amountMinor?.let { Money.input(it) } ?: "")
    }
    var minimumText by rememberSaveable(draft.id) {
        mutableStateOf(draft.minimumMinor?.let { Money.input(it) } ?: "")
    }
    var statementDateText by rememberSaveable(draft.id) {
        mutableStateOf(draft.statementDate ?: "")
    }
    var dueDateText by rememberSaveable(draft.id) {
        mutableStateOf(draft.dueDate ?: "")
    }
    var currencyText by rememberSaveable(draft.id) {
        mutableStateOf(draft.currency ?: "CNY")
    }

    // Validation
    val parsedAmount = Money.parse(amountText)
    val parsedMinimum = if (minimumText.isBlank()) null else runCatching {
        if (Regex("^[0-9]{1,10}(\\.[0-9]{1,2})?$").matches(minimumText.trim())) {
            BigDecimal(minimumText.trim()).movePointRight(2).longValueExact()
        } else null
    }.getOrNull()

    val parsedStmtDate = runCatching { LocalDate.parse(statementDateText.trim()) }.getOrNull()
    val parsedDueDate = runCatching { LocalDate.parse(dueDateText.trim()) }.getOrNull()

    val dateValid = parsedStmtDate != null && parsedDueDate != null && !parsedDueDate.isBefore(parsedStmtDate)
    val minimumValid = parsedMinimum == null || (parsedAmount != null && parsedMinimum in 0L..parsedAmount)
    val formValid = selectedAccountId != null && parsedAmount != null && dateValid && minimumValid

    val selectedAccount = accounts.find { it.id == selectedAccountId }

    Dialog(
        onDismissRequest = { if (!busy) onDismiss() },
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            modifier = Modifier
                .testTag("draft-dialog")
                .fillMaxWidth(0.94f)
                .fillMaxHeight(0.88f)
                .clip(RoundedCornerShape(20.dp)),
            color = Color.White,
            tonalElevation = 6.dp
        ) {
            Column(Modifier.fillMaxSize()) {
                // Header
                Column(
                    Modifier
                        .fillMaxWidth()
                        .background(Ink)
                        .padding(horizontal = 20.dp, vertical = 16.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "${draft.bank} 账单草稿",
                            color = Color.White,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.weight(1f)
                        )
                        Surface(
                            shape = RoundedCornerShape(50),
                            color = Gold.copy(alpha = 0.2f)
                        ) {
                            Text(
                                text = when (draft.extractorName) {
                                    "model_extractor" -> "智能大模型提取"
                                    "pdf_rule" -> "PDF 规则解析"
                                    "html_rule" -> "HTML 规则解析"
                                    else -> "后台解析"
                                },
                                color = Gold,
                                fontSize = 11.sp,
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                            )
                        }
                    }
                    Text(
                        text = "不可信数据核验 · 缺失字段不补零 · 确认后入账",
                        color = Color(0xFFB7C1C4),
                        fontSize = 11.sp,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                }

                // Scrollable Content
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .verticalScroll(rememberScrollState())
                        .padding(horizontal = 20.dp, vertical = 14.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp)
                ) {
                    // Review Reasons Banner
                    if (draft.reviewReasons.isNotEmpty()) {
                        Card(
                            colors = CardDefaults.cardColors(containerColor = Red.copy(alpha = 0.08f)),
                            shape = RoundedCornerShape(10.dp)
                        ) {
                            Row(
                                modifier = Modifier.padding(12.dp),
                                verticalAlignment = Alignment.Top
                            ) {
                                Icon(Icons.Outlined.WarningAmber, null, tint = Red, modifier = Modifier.size(18.dp))
                                Spacer(Modifier.width(8.dp))
                                Column {
                                    Text("核对提醒", fontWeight = FontWeight.Bold, fontSize = 12.sp, color = Red)
                                    draft.reviewReasons.forEach { reason ->
                                        Text(
                                            "• ${formatReviewReason(reason)}",
                                            fontSize = 11.sp,
                                            color = Ink,
                                            lineHeight = 16.sp,
                                            modifier = Modifier.padding(top = 2.dp)
                                        )
                                    }
                                }
                            }
                        }
                    }

                    // Account Selection
                    Column {
                        Text("归属信用卡账户", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Ink)
                        Spacer(Modifier.height(4.dp))
                        Box {
                            OutlinedCard(
                                onClick = { if (accounts.isNotEmpty()) accountMenuExpanded = true },
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .testTag("draft-account-select"),
                                shape = RoundedCornerShape(8.dp)
                            ) {
                                Row(
                                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column(Modifier.weight(1f)) {
                                        if (selectedAccount != null) {
                                            Text(
                                                "${selectedAccount.bank} (${selectedAccount.alias})",
                                                fontSize = 14.sp,
                                                fontWeight = FontWeight.Medium
                                            )
                                        } else {
                                            Text(
                                                if (accounts.isEmpty()) "暂无已同步账户 (请先在后台录入)" else "请选择对应信用卡账户",
                                                fontSize = 13.sp,
                                                color = Red
                                            )
                                        }
                                    }
                                    if (accounts.size > 1) {
                                        Icon(Icons.Outlined.ArrowDropDown, null, tint = Muted)
                                    }
                                }
                            }
                            DropdownMenu(
                                expanded = accountMenuExpanded,
                                onDismissRequest = { accountMenuExpanded = false }
                            ) {
                                accounts.forEach { acct ->
                                    DropdownMenuItem(
                                        text = {
                                            Text("${acct.bank} (${acct.alias})")
                                        },
                                        onClick = {
                                            selectedAccountId = acct.id
                                            accountMenuExpanded = false
                                        }
                                    )
                                }
                            }
                        }
                    }

                    // Card tail display if available
                    if (draft.cardTails.isNotEmpty()) {
                        Text(
                            "识别到卡号尾号: ${draft.cardTails.joinToString(" · ")}",
                            fontSize = 12.sp,
                            color = Green,
                            fontWeight = FontWeight.Medium
                        )
                    }

                    // Amounts
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        OutlinedTextField(
                            value = amountText,
                            onValueChange = { amountText = it },
                            label = { Text("应还总额") },
                            modifier = Modifier
                                .weight(1f)
                                .testTag("draft-amount-input"),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                            singleLine = true,
                            isError = parsedAmount == null && amountText.isNotEmpty(),
                            supportingText = { Text("元，必填") }
                        )
                        OutlinedTextField(
                            value = minimumText,
                            onValueChange = { minimumText = it },
                            label = { Text("最低还款额") },
                            modifier = Modifier.weight(1f),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                            singleLine = true,
                            isError = parsedMinimum != null && parsedAmount != null && parsedMinimum > parsedAmount,
                            supportingText = { Text("选填，无则留空") }
                        )
                    }

                    // Dates
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        OutlinedTextField(
                            value = statementDateText,
                            onValueChange = { statementDateText = it },
                            label = { Text("账单日") },
                            placeholder = { Text("YYYY-MM-DD") },
                            modifier = Modifier.weight(1f),
                            singleLine = true,
                            isError = parsedStmtDate == null && statementDateText.isNotEmpty(),
                            supportingText = { Text(if (parsedStmtDate == null) "年-月-日" else "") }
                        )
                        OutlinedTextField(
                            value = dueDateText,
                            onValueChange = { dueDateText = it },
                            label = { Text("到期还款日") },
                            placeholder = { Text("YYYY-MM-DD") },
                            modifier = Modifier
                                .weight(1f)
                                .testTag("draft-due-input"),
                            singleLine = true,
                            isError = (parsedDueDate == null || (parsedStmtDate != null && parsedDueDate.isBefore(parsedStmtDate))) && dueDateText.isNotEmpty(),
                            supportingText = { Text(if (!dateValid && dueDateText.isNotEmpty()) "不得早于账单日" else "") }
                        )
                    }

                    // Verbatim Evidence Section
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(12.dp))
                            .background(Paper)
                            .padding(14.dp)
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Outlined.Description, null, tint = Green, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(6.dp))
                            Text(
                                "原文依据与溯源",
                                fontWeight = FontWeight.Bold,
                                fontSize = 13.sp,
                                color = Ink
                            )
                        }
                        Text(
                            "来自原始邮件正文或附件的原文片段，不依赖模型臆测",
                            fontSize = 11.sp,
                            color = Muted,
                            modifier = Modifier.padding(top = 2.dp, bottom = 8.dp)
                        )

                        if (draft.evidence.isEmpty()) {
                            Text("未关联到具体文字摘录", fontSize = 11.sp, color = Muted)
                        } else {
                            draft.evidence.forEach { snippet ->
                                EvidenceCard(snippet)
                                Spacer(Modifier.height(6.dp))
                            }
                        }
                    }
                }

                // Action Buttons Bottom Bar
                Surface(
                    color = Paper,
                    tonalElevation = 2.dp,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        TextButton(
                            onClick = { onReject("用户核对后忽略") },
                            enabled = !busy,
                            colors = ButtonDefaults.textButtonColors(contentColor = Red),
                            modifier = Modifier.testTag("draft-reject-button")
                        ) {
                            Text("忽略草稿", fontSize = 13.sp)
                        }

                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            TextButton(
                                onClick = onDismiss,
                                enabled = !busy,
                                modifier = Modifier.testTag("draft-cancel-button")
                            ) {
                                Text("取消", fontSize = 13.sp)
                            }
                            Button(
                                onClick = {
                                    val aid = selectedAccountId ?: return@Button
                                    val amt = parsedAmount ?: return@Button
                                    val sDate = statementDateText.trim()
                                    val dDate = dueDateText.trim()
                                    val card = cards.find { it.accountId == aid && draft.cardTails.contains(it.tail) }
                                    onConfirm(
                                        StatementDraftConfirmRequestDto(
                                            accountId = aid,
                                            cardId = card?.id,
                                            currency = currencyText.trim().ifBlank { "CNY" },
                                            amountMinor = amt,
                                            minimumMinor = parsedMinimum,
                                            statementDate = sDate,
                                            dueDate = dDate
                                        )
                                    )
                                },
                                enabled = formValid && !busy,
                                colors = ButtonDefaults.buttonColors(containerColor = Gold, contentColor = Ink),
                                modifier = Modifier.testTag("draft-confirm-button")
                            ) {
                                Text(if (busy) "处理中…" else "确认入账", fontWeight = FontWeight.Bold, fontSize = 13.sp)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun EvidenceCard(snippet: EvidenceSnippetDto) {
    Surface(
        color = Color.White,
        shape = RoundedCornerShape(8.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, Line),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(Modifier.padding(8.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    formatEvidenceField(snippet.field),
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 11.sp,
                    color = Ink
                )
                Text(
                    "${snippet.sourceType} · 置信度 ${(snippet.confidence * 100).toInt()}%",
                    fontSize = 10.sp,
                    color = Muted
                )
            }
            Spacer(Modifier.height(4.dp))
            Surface(
                color = Paper,
                shape = RoundedCornerShape(4.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    snippet.snippet,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 11.sp,
                    color = Ink,
                    lineHeight = 15.sp,
                    modifier = Modifier.padding(6.dp)
                )
            }
        }
    }
}

private fun formatEvidenceField(field: String): String = when (field) {
    "amount_minor", "amount" -> "应还总额依据"
    "minimum_minor", "minimum" -> "最低还款额依据"
    "due_date" -> "到期还款日依据"
    "statement_date" -> "账单日依据"
    "bank" -> "银行名称依据"
    "currency" -> "币种依据"
    "card_tails" -> "卡片尾号依据"
    "account_reference" -> "账户编号依据"
    else -> "字段依据 ($field)"
}

private fun formatReviewReason(reason: String): String = when {
    reason == "unresolved:account" -> "未匹配到唯一的信用卡账户，请手动核对并选择归属账户"
    reason == "unverified:minimum_minor" -> "最低还款额有提取值，但缺少明确原文依据，请核实"
    reason == "mismatch:due_before_statement" -> "到期还款日早于账单日，请核对日期"
    reason.startsWith("unresolved:") -> "未明确关联: ${reason.removePrefix("unresolved:")}"
    else -> reason
}
