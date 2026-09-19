package com.cardcue.app.sync

import android.os.Build
import androidx.room.withTransaction
import com.cardcue.app.data.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.UUID

enum class SyncState {
    IDLE,
    SYNCING,
    SUCCESS,
    OFFLINE,
    ERROR,
}

data class SyncInfo(
    val state: SyncState = SyncState.IDLE,
    val lastSyncTime: String? = null,
    val message: String? = null,
    val serverUrl: String = SyncManager.DEFAULT_SERVER_URL,
    val isPaired: Boolean = false,
    val deviceId: String? = null,
    val isOffline: Boolean = false,
)

class SyncManager(
    private val db: CardCueDatabase,
    private val apiClient: SyncApiClient = SyncApiClient(),
    val serverUrl: String = DEFAULT_SERVER_URL,
) {
    companion object {
        const val DEFAULT_SERVER_URL = "http://152.70.238.24:8000"
        private const val META_SERVER_URL = "sync_server_url"
        private const val META_DEVICE_TOKEN = "sync_device_token"
        private const val META_DEVICE_ID = "sync_device_id"
        private const val META_CURSOR = "sync_cursor"
        private const val META_LAST_SYNC_TIME = "sync_last_time"
    }

    private val dao = db.dao()
    private val mutex = Mutex()
    private val _syncInfo = MutableStateFlow(SyncInfo(serverUrl = serverUrl))
    val syncInfo = _syncInfo.asStateFlow()

    suspend fun init() = withContext(Dispatchers.IO) {
        val token = dao.syncMeta(META_DEVICE_TOKEN)
        val deviceId = dao.syncMeta(META_DEVICE_ID)
        val lastTime = dao.syncMeta(META_LAST_SYNC_TIME)
        val isPaired = !token.isNullOrBlank() && !deviceId.isNullOrBlank()
        _syncInfo.value = _syncInfo.value.copy(
            isPaired = isPaired,
            deviceId = deviceId,
            lastSyncTime = lastTime,
            state = if (isPaired) SyncState.IDLE else SyncState.IDLE
        )
    }

    suspend fun syncNow(forceBootstrap: Boolean = false): Boolean = mutex.withLock {
        withContext(Dispatchers.IO) {
            _syncInfo.value = _syncInfo.value.copy(state = SyncState.SYNCING, message = "正在检查服务器连接...")

            // 1. Health check
            val healthy = apiClient.checkHealth(serverUrl)
            if (!healthy) {
                _syncInfo.value = _syncInfo.value.copy(
                    state = SyncState.OFFLINE,
                    isOffline = true,
                    message = "无法连接服务器，展示离线缓存"
                )
                return@withContext false
            }

            // 2. Ensure paired
            var token = dao.syncMeta(META_DEVICE_TOKEN)
            var deviceId = dao.syncMeta(META_DEVICE_ID)
            if (token.isNullOrBlank() || deviceId.isNullOrBlank()) {
                try {
                    _syncInfo.value = _syncInfo.value.copy(message = "正在配对设备...")
                    val modelName = Build.MODEL ?: "Device"
                    val deviceName = "CardCue Android (${modelName})"
                    val pairRes = apiClient.pairDevice(serverUrl, deviceName)
                    token = pairRes.token
                    deviceId = pairRes.deviceId
                    db.withTransaction {
                        dao.setSyncMeta(SyncMeta(META_DEVICE_TOKEN, token))
                        dao.setSyncMeta(SyncMeta(META_DEVICE_ID, deviceId))
                    }
                    _syncInfo.value = _syncInfo.value.copy(isPaired = true, deviceId = deviceId)
                } catch (e: Exception) {
                    _syncInfo.value = _syncInfo.value.copy(
                        state = SyncState.ERROR,
                        message = "设备配对失败: ${e.message}"
                    )
                    return@withContext false
                }
            }

            // 3. Sync data
            val activeToken = requireNotNull(token)
            val currentCursorStr = dao.syncMeta(META_CURSOR)
            val currentCursor = currentCursorStr?.toLongOrNull() ?: 0L

            try {
                if (forceBootstrap || currentCursor == 0L) {
                    performBootstrap(activeToken)
                } else {
                    try {
                        performIncrementalSync(activeToken, currentCursor)
                    } catch (e: CursorOutOfRangeException) {
                        // Cursor invalid / server restore -> fallback to bootstrap
                        performBootstrap(activeToken)
                    }
                }

                val now = formatNow()
                db.withTransaction {
                    dao.setSyncMeta(SyncMeta(META_LAST_SYNC_TIME, now))
                }
                _syncInfo.value = _syncInfo.value.copy(
                    state = SyncState.SUCCESS,
                    isOffline = false,
                    lastSyncTime = now,
                    message = "同步成功"
                )
                return@withContext true
            } catch (e: SyncAuthException) {
                // Token revoked on server
                db.withTransaction {
                    dao.setSyncMeta(SyncMeta(META_DEVICE_TOKEN, ""))
                    dao.setSyncMeta(SyncMeta(META_DEVICE_ID, ""))
                }
                _syncInfo.value = _syncInfo.value.copy(
                    state = SyncState.ERROR,
                    isPaired = false,
                    message = "设备凭证已失效，请重新连接"
                )
                return@withContext false
            } catch (e: Exception) {
                _syncInfo.value = _syncInfo.value.copy(
                    state = SyncState.ERROR,
                    message = "同步失败: ${e.message}"
                )
                return@withContext false
            }
        }
    }

    private suspend fun performBootstrap(token: String) {
        _syncInfo.value = _syncInfo.value.copy(message = "正在拉取完整快照...")
        val bootstrap = apiClient.getBootstrap(serverUrl, token)

        val accounts = bootstrap.accounts.map {
            SyncedAccount(
                id = it.id,
                bank = it.bank,
                alias = it.alias,
                reference = it.reference,
                status = it.status,
                updatedAt = it.updatedAt
            )
        }
        val cards = bootstrap.cards.map {
            SyncedCard(
                id = it.id,
                accountId = it.accountId,
                displayName = it.displayName,
                tail = it.tail,
                status = it.status
            )
        }
        val statements = bootstrap.statements.map {
            SyncedStatement(
                id = it.id,
                accountId = it.accountId,
                currency = it.currency,
                statementDate = it.statementDate,
                dueDate = it.dueDate,
                currentVersionId = it.currentVersionId,
                totalPaidMinor = it.totalPaidMinor,
                remainingMinor = it.remainingMinor,
                updatedAt = it.updatedAt
            )
        }
        val versions = bootstrap.statements.mapNotNull { it.currentVersion }.map {
            SyncedStatementVersion(
                id = it.id,
                statementId = it.statementId,
                versionNumber = it.versionNumber,
                amountMinor = it.amountMinor,
                minimumMinor = it.minimumMinor,
                source = it.source,
                reason = it.reason,
                confirmedAt = it.confirmedAt,
                confirmedBy = it.confirmedBy
            )
        }
        val payments = bootstrap.payments.map {
            SyncedPayment(
                id = it.id,
                statementId = it.statementId,
                amountMinor = it.amountMinor,
                currency = it.currency,
                note = it.note,
                recordedAt = it.recordedAt,
                revokedAt = it.revokedAt,
                revokeReason = it.revokeReason
            )
        }

        db.withTransaction {
            dao.clearAllSyncedData()
            dao.upsertSyncedAccounts(accounts)
            dao.upsertSyncedCards(cards)
            dao.upsertSyncedStatements(statements)
            dao.upsertSyncedStatementVersions(versions)
            dao.upsertSyncedPayments(payments)
            dao.setSyncMeta(SyncMeta(META_CURSOR, bootstrap.cursor.toString()))
        }
    }

    private suspend fun performIncrementalSync(token: String, startCursor: Long) {
        _syncInfo.value = _syncInfo.value.copy(message = "正在拉取增量变更...")
        var cursor = startCursor
        var hasMore = true
        while (hasMore) {
            val res = apiClient.getChanges(serverUrl, token, cursor, limit = 100)
            if (res.changes.isNotEmpty()) {
                db.withTransaction {
                    for (ch in res.changes) {
                        applyChange(ch)
                    }
                    dao.setSyncMeta(SyncMeta(META_CURSOR, res.cursor.toString()))
                }
            }
            cursor = res.cursor
            hasMore = res.hasMore
        }
    }

    private suspend fun applyChange(change: SyncChangeItemDto) {
        val snapshot = change.snapshot
        when (change.entityType) {
            "account" -> {
                if (change.action == "delete") {
                    dao.deleteSyncedAccount(change.entityId)
                } else if (snapshot != null) {
                    dao.upsertSyncedAccounts(listOf(
                        SyncedAccount(
                            id = change.entityId,
                            bank = snapshot["bank"]?.toString() ?: "",
                            alias = snapshot["alias"]?.toString(),
                            reference = snapshot["reference"]?.toString(),
                            status = snapshot["status"]?.toString() ?: "active",
                            updatedAt = snapshot["updated_at"]?.toString() ?: ""
                        )
                    ))
                }
            }
            "card" -> {
                if (change.action == "delete") {
                    dao.deleteSyncedCard(change.entityId)
                } else if (snapshot != null) {
                    dao.upsertSyncedCards(listOf(
                        SyncedCard(
                            id = change.entityId,
                            accountId = snapshot["account_id"]?.toString() ?: "",
                            displayName = snapshot["display_name"]?.toString(),
                            tail = snapshot["tail"]?.toString() ?: "",
                            status = snapshot["status"]?.toString() ?: "active"
                        )
                    ))
                }
            }
            "statement" -> {
                if (change.action == "delete") {
                    dao.deleteSyncedStatement(change.entityId)
                } else if (snapshot != null) {
                    dao.upsertSyncedStatements(listOf(
                        SyncedStatement(
                            id = change.entityId,
                            accountId = snapshot["account_id"]?.toString() ?: "",
                            currency = snapshot["currency"]?.toString() ?: "CNY",
                            statementDate = snapshot["statement_date"]?.toString() ?: "",
                            dueDate = snapshot["due_date"]?.toString() ?: "",
                            currentVersionId = snapshot["current_version_id"]?.toString(),
                            totalPaidMinor = (snapshot["total_paid_minor"] as? Number)?.toLong() ?: 0L,
                            remainingMinor = (snapshot["remaining_minor"] as? Number)?.toLong() ?: 0L,
                            updatedAt = snapshot["updated_at"]?.toString() ?: ""
                        )
                    ))
                }
            }
            "statement_version" -> {
                if (change.action == "delete") {
                    dao.deleteSyncedStatementVersion(change.entityId)
                } else if (snapshot != null) {
                    dao.upsertSyncedStatementVersions(listOf(
                        SyncedStatementVersion(
                            id = change.entityId,
                            statementId = snapshot["statement_id"]?.toString() ?: "",
                            versionNumber = (snapshot["version_number"] as? Number)?.toInt() ?: 1,
                            amountMinor = (snapshot["amount_minor"] as? Number)?.toLong() ?: 0L,
                            minimumMinor = (snapshot["minimum_minor"] as? Number)?.toLong(),
                            source = snapshot["source"]?.toString() ?: "manual",
                            reason = snapshot["reason"]?.toString(),
                            confirmedAt = snapshot["confirmed_at"]?.toString(),
                            confirmedBy = snapshot["confirmed_by"]?.toString()
                        )
                    ))
                }
            }
            "payment" -> {
                if (change.action == "delete") {
                    dao.deleteSyncedPayment(change.entityId)
                } else if (snapshot != null) {
                    dao.upsertSyncedPayments(listOf(
                        SyncedPayment(
                            id = change.entityId,
                            statementId = snapshot["statement_id"]?.toString() ?: "",
                            amountMinor = (snapshot["amount_minor"] as? Number)?.toLong() ?: 0L,
                            currency = snapshot["currency"]?.toString() ?: "CNY",
                            note = snapshot["note"]?.toString(),
                            recordedAt = snapshot["recorded_at"]?.toString() ?: "",
                            revokedAt = snapshot["revoked_at"]?.toString(),
                            revokeReason = snapshot["revoke_reason"]?.toString()
                        )
                    ))
                }
            }
        }
    }

    suspend fun recordPaymentOnline(
        statementId: String,
        amountMinor: Long,
        currency: String,
        note: String,
        requestId: String = UUID.randomUUID().toString(),
    ): SyncPaymentResponse = withContext(Dispatchers.IO) {
        val token = dao.syncMeta(META_DEVICE_TOKEN)
        if (token.isNullOrBlank()) {
            throw IllegalStateException("设备未连接服务器，离线只读")
        }
        val healthy = apiClient.checkHealth(serverUrl)
        if (!healthy) {
            _syncInfo.value = _syncInfo.value.copy(state = SyncState.OFFLINE, isOffline = true)
            throw IllegalStateException("离线只读，请连接网络后还款")
        }

        val req = PaymentCreateRequest(
            statementId = statementId,
            amountMinor = amountMinor,
            currency = currency,
            note = note.ifBlank { null },
            requestId = requestId
        )
        val res = apiClient.recordPayment(serverUrl, token, req)

        // Atomically update local cache with the returned payment & updated statement
        db.withTransaction {
            dao.upsertSyncedPayments(listOf(
                SyncedPayment(
                    id = res.payment.id,
                    statementId = res.payment.statementId,
                    amountMinor = res.payment.amountMinor,
                    currency = res.payment.currency,
                    note = res.payment.note,
                    recordedAt = res.payment.recordedAt,
                    revokedAt = res.payment.revokedAt,
                    revokeReason = res.payment.revokeReason
                )
            ))
            dao.upsertSyncedStatements(listOf(
                SyncedStatement(
                    id = res.statementDetail.id,
                    accountId = res.statementDetail.accountId,
                    currency = res.statementDetail.currency,
                    statementDate = res.statementDetail.statementDate,
                    dueDate = res.statementDetail.dueDate,
                    currentVersionId = res.statementDetail.currentVersionId,
                    totalPaidMinor = res.statementDetail.totalPaidMinor,
                    remainingMinor = res.statementDetail.remainingMinor,
                    updatedAt = res.statementDetail.updatedAt
                )
            ))
        }
        res
    }

    suspend fun revokePaymentOnline(
        paymentId: String,
        reason: String
    ): SyncPaymentResponse = withContext(Dispatchers.IO) {
        val token = dao.syncMeta(META_DEVICE_TOKEN)
        if (token.isNullOrBlank()) {
            throw IllegalStateException("设备未连接服务器，离线只读")
        }
        val healthy = apiClient.checkHealth(serverUrl)
        if (!healthy) {
            _syncInfo.value = _syncInfo.value.copy(state = SyncState.OFFLINE, isOffline = true)
            throw IllegalStateException("离线只读，请连接网络后撤销还款")
        }

        val res = apiClient.revokePayment(serverUrl, token, paymentId, reason)
        db.withTransaction {
            dao.upsertSyncedPayments(listOf(
                SyncedPayment(
                    id = res.payment.id,
                    statementId = res.payment.statementId,
                    amountMinor = res.payment.amountMinor,
                    currency = res.payment.currency,
                    note = res.payment.note,
                    recordedAt = res.payment.recordedAt,
                    revokedAt = res.payment.revokedAt,
                    revokeReason = res.payment.revokeReason
                )
            ))
            dao.upsertSyncedStatements(listOf(
                SyncedStatement(
                    id = res.statementDetail.id,
                    accountId = res.statementDetail.accountId,
                    currency = res.statementDetail.currency,
                    statementDate = res.statementDetail.statementDate,
                    dueDate = res.statementDetail.dueDate,
                    currentVersionId = res.statementDetail.currentVersionId,
                    totalPaidMinor = res.statementDetail.totalPaidMinor,
                    remainingMinor = res.statementDetail.remainingMinor,
                    updatedAt = res.statementDetail.updatedAt
                )
            ))
        }
        res
    }

    suspend fun triggerMailSync(): MailSyncTriggerResult = withContext(Dispatchers.IO) {
        val token = dao.syncMeta(META_DEVICE_TOKEN)
        if (token.isNullOrBlank()) {
            throw IllegalStateException("设备未连接服务器，离线只读")
        }
        val healthy = apiClient.checkHealth(serverUrl)
        if (!healthy) {
            _syncInfo.value = _syncInfo.value.copy(state = SyncState.OFFLINE, isOffline = true)
            throw IllegalStateException("离线只读，请连接网络后检查邮件")
        }
        apiClient.triggerMailSync(serverUrl, token)
    }

    suspend fun fetchMailJobs(): List<MailJobDto> = withContext(Dispatchers.IO) {
        val token = dao.syncMeta(META_DEVICE_TOKEN)
        if (token.isNullOrBlank()) {
            return@withContext emptyList()
        }
        try {
            apiClient.getMailJobs(serverUrl, token)
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun fetchPendingDrafts(): List<StatementDraftDto> = withContext(Dispatchers.IO) {
        val token = dao.syncMeta(META_DEVICE_TOKEN) ?: return@withContext emptyList()
        try {
            apiClient.getDrafts(serverUrl, token, status = "pending_review")
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun confirmDraftOnline(
        draftId: String,
        req: StatementDraftConfirmRequestDto
    ): StatementDraftConfirmResponseDto = withContext(Dispatchers.IO) {
        val token = dao.syncMeta(META_DEVICE_TOKEN)
            ?: throw IllegalStateException("设备未连接服务器，离线只读")
        val healthy = apiClient.checkHealth(serverUrl)
        if (!healthy) {
            _syncInfo.value = _syncInfo.value.copy(state = SyncState.OFFLINE, isOffline = true)
            throw IllegalStateException("离线只读，请连接网络后确认草稿")
        }

        val res = apiClient.confirmDraft(serverUrl, token, draftId, req)
        val stmt = res.statement
        val ver = res.version
        db.withTransaction {
            dao.upsertSyncedStatements(listOf(
                SyncedStatement(
                    id = stmt.id,
                    accountId = stmt.accountId,
                    currency = stmt.currency,
                    statementDate = stmt.statementDate,
                    dueDate = stmt.dueDate,
                    currentVersionId = stmt.currentVersionId ?: ver.id,
                    totalPaidMinor = stmt.totalPaidMinor,
                    remainingMinor = stmt.remainingMinor,
                    updatedAt = stmt.updatedAt
                )
            ))
            dao.upsertSyncedStatementVersions(listOf(
                SyncedStatementVersion(
                    id = ver.id,
                    statementId = ver.statementId,
                    versionNumber = ver.versionNumber,
                    amountMinor = ver.amountMinor,
                    minimumMinor = ver.minimumMinor,
                    source = ver.source,
                    reason = ver.reason,
                    confirmedAt = ver.confirmedAt,
                    confirmedBy = ver.confirmedBy
                )
            ))
        }
        res
    }

    suspend fun rejectDraftOnline(
        draftId: String,
        reason: String
    ): StatementDraftDto = withContext(Dispatchers.IO) {
        val token = dao.syncMeta(META_DEVICE_TOKEN)
            ?: throw IllegalStateException("设备未连接服务器，离线只读")
        val healthy = apiClient.checkHealth(serverUrl)
        if (!healthy) {
            _syncInfo.value = _syncInfo.value.copy(state = SyncState.OFFLINE, isOffline = true)
            throw IllegalStateException("离线只读，请连接网络后处理草稿")
        }
        apiClient.rejectDraft(serverUrl, token, draftId, reason)
    }

    suspend fun parseAllPendingDrafts(): List<StatementDraftDto> = withContext(Dispatchers.IO) {
        val token = dao.syncMeta(META_DEVICE_TOKEN)
            ?: throw IllegalStateException("设备未连接服务器，离线只读")
        val healthy = apiClient.checkHealth(serverUrl)
        if (!healthy) {
            _syncInfo.value = _syncInfo.value.copy(state = SyncState.OFFLINE, isOffline = true)
            throw IllegalStateException("离线只读，请连接网络后解析邮件")
        }
        apiClient.parseAllPending(serverUrl, token)
    }

    private fun formatNow(): String {
        return DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")
            .withZone(ZoneId.systemDefault())
            .format(Instant.now())
    }
}
