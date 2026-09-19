package com.cardcue.app.sync

import java.util.UUID

data class AccountDto(
    val id: String,
    val bank: String,
    val alias: String?,
    val reference: String?,
    val status: String,
    val createdAt: String,
    val updatedAt: String,
)

data class CardDto(
    val id: String,
    val accountId: String,
    val displayName: String?,
    val tail: String,
    val status: String,
    val createdAt: String,
)

data class StatementVersionDto(
    val id: String,
    val statementId: String,
    val versionNumber: Int,
    val amountMinor: Long,
    val minimumMinor: Long?,
    val source: String,
    val reason: String?,
    val confirmedAt: String?,
    val confirmedBy: String?,
    val createdAt: String,
)

data class StatementDetailDto(
    val id: String,
    val accountId: String,
    val currency: String,
    val statementDate: String,
    val dueDate: String,
    val currentVersionId: String?,
    val createdAt: String,
    val updatedAt: String,
    val currentVersion: StatementVersionDto?,
    val totalPaidMinor: Long,
    val remainingMinor: Long,
)

data class PaymentDto(
    val id: String,
    val statementId: String,
    val amountMinor: Long,
    val currency: String,
    val note: String?,
    val recordedAt: String,
    val revokedAt: String?,
    val revokeReason: String?,
)

data class SyncBootstrapResponse(
    val cursor: Long,
    val serverTime: String,
    val accounts: List<AccountDto>,
    val cards: List<CardDto>,
    val statements: List<StatementDetailDto>,
    val payments: List<PaymentDto>,
)

data class SyncChangeItemDto(
    val seq: Long,
    val entityType: String,
    val entityId: String,
    val action: String,
    val snapshot: Map<String, Any?>?,
    val createdAt: String,
)

data class SyncChangesResponse(
    val cursor: Long,
    val hasMore: Boolean,
    val changes: List<SyncChangeItemDto>,
    val serverTime: String,
)

data class PaymentCreateRequest(
    val statementId: String,
    val amountMinor: Long,
    val currency: String,
    val note: String? = null,
    val requestId: String = UUID.randomUUID().toString(),
)

data class SyncPaymentResponse(
    val payment: PaymentDto,
    val created: Boolean,
    val statementDetail: StatementDetailDto,
)

data class PairResponse(
    val deviceId: String,
    val name: String,
    val token: String,
)

data class MailSyncTriggerResult(
    val jobIds: List<String>,
    val message: String,
)

data class MailJobDto(
    val id: String,
    val mailboxId: String,
    val triggerType: String,
    val status: String,
    val startedAt: String?,
    val finishedAt: String?,
    val errorMessage: String?,
    val emailsChecked: Int,
    val emailsFetched: Int,
    val statementCandidates: Int,
    val createdAt: String,
)


data class EvidenceSnippetDto(
    val field: String,
    val snippet: String,
    val sourceType: String,
    val confidence: Double = 1.0,
)

data class StatementDraftDto(
    val id: String,
    val emailSourceId: String?,
    val mailboxId: String?,
    val status: String,
    val bank: String?,
    val currency: String?,
    val amountMinor: Long?,
    val minimumMinor: Long?,
    val statementDate: String?,
    val dueDate: String?,
    val accountReference: String?,
    val cardTails: List<String> = emptyList(),
    val evidence: List<EvidenceSnippetDto> = emptyList(),
    val reviewReasons: List<String> = emptyList(),
    val matchedAccountId: String?,
    val matchedCardId: String?,
    val confirmedVersionId: String?,
    val rejectionReason: String?,
    val extractorName: String,
    val createdAt: String,
    val updatedAt: String,
)

data class StatementDraftConfirmRequestDto(
    val accountId: String,
    val cardId: String? = null,
    val currency: String? = null,
    val amountMinor: Long? = null,
    val minimumMinor: Long? = null,
    val statementDate: String? = null,
    val dueDate: String? = null,
)

data class StatementDraftConfirmResponseDto(
    val draftId: String,
    val statement: StatementDetailDto,
    val version: StatementVersionDto,
)
