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
    val deviceName: String? = null,
    val isOffline: Boolean = false,
)

class SyncManager(
    private val db: CardCueDatabase,
    private val apiClient: SyncApiClient = SyncApiClient(),
    val serverUrl: String = DEFAULT_SERVER_URL,
) {
    companion object {
        const val DEFAULT_SERVER_URL = "http://152.70.238.24:8000"
        const val META_SERVER_URL = "sync_server_url"
        const val META_DEVICE_TOKEN = "sync_device_token"
        const val META_DEVICE_ID = "sync_device_id"
        const val META_DEVICE_NAME = "sync_device_name"
        const val META_CURSOR = "sync_cursor"
        // A server cursor does not describe cached row shape. Bump after schema changes.
        const val META_CACHE_PROTOCOL = "sync_cache_protocol"
        const val CACHE_PROTOCOL = "2"
        const val META_LAST_SYNC_TIME = "sync_last_time"
    }

    private val dao = db.dao()
    private val mutex = Mutex()
    private val _syncInfo = MutableStateFlow(SyncInfo(serverUrl = serverUrl))
    val syncInfo = _syncInfo.asStateFlow()

    suspend fun getActiveServerUrl(): String {
        val saved = dao.syncMeta(META_SERVER_URL)
        return if (!saved.isNullOrBlank()) saved else _syncInfo.value.serverUrl.ifBlank { serverUrl }
    }

    suspend fun init() = withContext(Dispatchers.IO) {
        val savedUrl = dao.syncMeta(META_SERVER_URL)
        val activeUrl = if (!savedUrl.isNullOrBlank()) savedUrl else serverUrl
        val token = dao.syncMeta(META_DEVICE_TOKEN)
        val deviceId = dao.syncMeta(META_DEVICE_ID)
        val deviceName = dao.syncMeta(META_DEVICE_NAME)
        val lastTime = dao.syncMeta(META_LAST_SYNC_TIME)
        val isPaired = !token.isNullOrBlank() && !deviceId.isNullOrBlank()
        _syncInfo.value = _syncInfo.value.copy(
            serverUrl = activeUrl,
            isPaired = isPaired,
            deviceId = deviceId,
            deviceName = deviceName,
            lastSyncTime = lastTime,
            state = SyncState.IDLE
        )
    }

    suspend fun pairWithCode(
        targetServerUrl: String,
        pairingCode: String,
        customDeviceName: String? = null
    ): PairResponse = mutex.withLock {
        withContext(Dispatchers.IO) {
            val normalizedUrl = targetServerUrl.trim().removeSuffix("/")
            val cleanCode = pairingCode.trim()
            require(normalizedUrl.isNotBlank()) { "服务器地址不能为空" }
            require(normalizedUrl.startsWith("http://") || normalizedUrl.startsWith("https://")) {
                "服务器地址需以 http:// 或 https:// 开头"
            }
            require(cleanCode.length >= 20) { "配对码格式不正确 (至少 20 位)" }

            val modelName = Build.MODEL ?: "Device"
            val devName = customDeviceName?.trim()?.takeIf { it.isNotBlank() } ?: "CardCue Android ($modelName)"

            _syncInfo.value = _syncInfo.value.copy(
                state = SyncState.SYNCING,
                serverUrl = normalizedUrl,
                message = "正在连接并配对设备..."
            )

            // 1. Call pairDevice
            val pairRes = apiClient.pairDevice(normalizedUrl, devName, cleanCode)

            // 2. Persist to DB
            db.withTransaction {
                dao.setSyncMeta(SyncMeta(META_SERVER_URL, normalizedUrl))
                dao.setSyncMeta(SyncMeta(META_DEVICE_TOKEN, pairRes.token))
                dao.setSyncMeta(SyncMeta(META_DEVICE_ID, pairRes.deviceId))
                dao.setSyncMeta(SyncMeta(META_DEVICE_NAME, devName))
                dao.deleteSyncMeta(META_CURSOR)
                dao.deleteSyncMeta(META_CACHE_PROTOCOL)
            }

            _syncInfo.value = _syncInfo.value.copy(
                isPaired = true,
                deviceId = pairRes.deviceId,
                deviceName = devName,
                serverUrl = normalizedUrl,
                isOffline = false,
                message = "配对成功，正在拉取最新账单..."
            )

            // 3. Perform initial bootstrap
            try {
                performBootstrap(normalizedUrl, pairRes.token)
                val now = formatNow()
                db.withTransaction {
                    dao.setSyncMeta(SyncMeta(META_LAST_SYNC_TIME, now))
                }
                _syncInfo.value = _syncInfo.value.copy(
                    state = SyncState.SUCCESS,
                    lastSyncTime = now,
                    message = "配对并同步成功"
                )
            } catch (e: Exception) {
                _syncInfo.value = _syncInfo.value.copy(
                    state = SyncState.SUCCESS,
                    message = "配对成功，但初始拉取稍后重试: ${e.message}"
                )
            }

            pairRes
        }
    }

    suspend fun unpairDevice(): Boolean = mutex.withLock {
        withContext(Dispatchers.IO) {
            db.withTransaction {
                dao.deleteSyncMeta(META_DEVICE_TOKEN)
                dao.deleteSyncMeta(META_DEVICE_ID)
                dao.deleteSyncMeta(META_DEVICE_NAME)
                dao.deleteSyncMeta(META_CURSOR)
                dao.deleteSyncMeta(META_CACHE_PROTOCOL)
                dao.deleteSyncMeta(META_LAST_SYNC_TIME)
                dao.clearAllSyncedData()
            }
            val activeUrl = dao.syncMeta(META_SERVER_URL) ?: serverUrl
            _syncInfo.value = _syncInfo.value.copy(
                isPaired = false,
                deviceId = null,
                deviceName = null,
                serverUrl = activeUrl,
                lastSyncTime = null,
                state = SyncState.IDLE,
                message = "已解除配对，恢复演示模式"
            )
            true
        }
    }

    suspend fun syncNow(forceBootstrap: Boolean = false): Boolean = mutex.withLock {
        withContext(Dispatchers.IO) {
            val currentServerUrl = getActiveServerUrl()
            _syncInfo.value = _syncInfo.value.copy(
                state = SyncState.SYNCING,
                serverUrl = currentServerUrl,
                message = "正在检查服务器连接..."
            )

            // 1. Health check
            val healthy = apiClient.checkHealth(currentServerUrl)
            if (!healthy) {
                _syncInfo.value = _syncInfo.value.copy(
                    state = SyncState.OFFLINE,
                    isOffline = true,
                    message = "无法连接服务器，展示离线缓存"
                )
                return@withContext false
            }

            // 2. Ensure paired
            val token = dao.syncMeta(META_DEVICE_TOKEN)
            val deviceId = dao.syncMeta(META_DEVICE_ID)
            if (token.isNullOrBlank() || deviceId.isNullOrBlank()) {
                _syncInfo.value = _syncInfo.value.copy(
                    state = SyncState.IDLE,
                    isPaired = false,
                    message = "设备未配对，请在设置中输入配对码"
                )
                return@withContext false
            }

            // 3. Sync data
            val activeToken = requireNotNull(token)
            val currentCursorStr = dao.syncMeta(META_CURSOR)
            val currentCursor = currentCursorStr?.toLongOrNull() ?: 0L
            val cacheProtocol = dao.syncMeta(META_CACHE_PROTOCOL)

            try {
                if (forceBootstrap || currentCursor == 0L || cacheProtocol != CACHE_PROTOCOL) {
                    performBootstrap(currentServerUrl, activeToken)
                } else {
                    try {
                        performIncrementalSync(currentServerUrl, activeToken, currentCursor)
                    } catch (e: CursorOutOfRangeException) {
                        // Cursor invalid / server restore -> fallback to bootstrap
                        performBootstrap(currentServerUrl, activeToken)
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
                    dao.deleteSyncMeta(META_DEVICE_TOKEN)
                    dao.deleteSyncMeta(META_DEVICE_ID)
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

    private suspend fun performBootstrap(url: String, token: String) {
        _syncInfo.value = _syncInfo.value.copy(message = "正在拉取完整快照...")
        val bootstrap = apiClient.getBootstrap(url, token)

        val accounts = bootstrap.accounts.map {
            SyncedAccount(
                id = it.id,
                bank = it.bank,
                alias = it.alias,
                reference = it.reference,
                status = it.status,
                updatedAt = it.updatedAt,
                holder = it.holder,
                billingMode = it.billingMode,
                billingModeSource = it.billingModeSource,
                revision = it.revision
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
            // Marker and authoritative rows activate atomically; failure preserves retry.
            dao.setSyncMeta(SyncMeta(META_CACHE_PROTOCOL, CACHE_PROTOCOL))
        }
    }

    private suspend fun performIncrementalSync(url: String, token: String, startCursor: Long) {
        _syncInfo.value = _syncInfo.value.copy(message = "正在检查服务端变更...")
        val changes = apiClient.getChanges(url, token, startCursor, limit = 100)
        if (changes.changes.isNotEmpty()) {
            // The backend change log records partial event snapshots, not a complete
            // representation of statement balances, versions or account/card identity.
            // Refresh all synced entities together instead of applying a partial event
            // or advancing the cursor past data that was not fully loaded.
            performBootstrap(url, token)
        }
    }

    suspend fun recordPaymentOnline(
        statementId: String,
        amountMinor: Long,
        currency: String,
        note: String,
        requestId: String = UUID.randomUUID().toString(),
    ): SyncPaymentResponse = withContext(Dispatchers.IO) {
        val currentUrl = getActiveServerUrl()
        val token = dao.syncMeta(META_DEVICE_TOKEN)
        if (token.isNullOrBlank()) {
            throw IllegalStateException("设备未连接服务器，离线只读")
        }
        val healthy = apiClient.checkHealth(currentUrl)
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
        val res = apiClient.recordPayment(currentUrl, token, req)

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
        val currentUrl = getActiveServerUrl()
        val token = dao.syncMeta(META_DEVICE_TOKEN)
        if (token.isNullOrBlank()) {
            throw IllegalStateException("设备未连接服务器，离线只读")
        }
        val healthy = apiClient.checkHealth(currentUrl)
        if (!healthy) {
            _syncInfo.value = _syncInfo.value.copy(state = SyncState.OFFLINE, isOffline = true)
            throw IllegalStateException("离线只读，请连接网络后撤销还款")
        }

        val res = apiClient.revokePayment(currentUrl, token, paymentId, reason)
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
        val currentUrl = getActiveServerUrl()
        val token = dao.syncMeta(META_DEVICE_TOKEN)
        if (token.isNullOrBlank()) {
            throw IllegalStateException("设备未连接服务器，离线只读")
        }
        val healthy = apiClient.checkHealth(currentUrl)
        if (!healthy) {
            _syncInfo.value = _syncInfo.value.copy(state = SyncState.OFFLINE, isOffline = true)
            throw IllegalStateException("离线只读，请连接网络后检查邮件")
        }
        apiClient.triggerMailSync(currentUrl, token)
    }

    suspend fun fetchMailJobs(): List<MailJobDto> = withContext(Dispatchers.IO) {
        val currentUrl = getActiveServerUrl()
        val token = dao.syncMeta(META_DEVICE_TOKEN)
        if (token.isNullOrBlank()) {
            return@withContext emptyList()
        }
        try {
            apiClient.getMailJobs(currentUrl, token)
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun fetchPendingDrafts(): List<StatementDraftDto> = withContext(Dispatchers.IO) {
        val currentUrl = getActiveServerUrl()
        val token = dao.syncMeta(META_DEVICE_TOKEN) ?: return@withContext emptyList()
        try {
            apiClient.getDrafts(currentUrl, token, status = "pending_review")
        } catch (e: Exception) {
            emptyList()
        }
    }

    suspend fun confirmDraftOnline(
        draftId: String,
        req: StatementDraftConfirmRequestDto
    ): StatementDraftConfirmResponseDto = withContext(Dispatchers.IO) {
        val currentUrl = getActiveServerUrl()
        val token = dao.syncMeta(META_DEVICE_TOKEN)
            ?: throw IllegalStateException("设备未连接服务器，离线只读")
        val healthy = apiClient.checkHealth(currentUrl)
        if (!healthy) {
            _syncInfo.value = _syncInfo.value.copy(state = SyncState.OFFLINE, isOffline = true)
            throw IllegalStateException("离线只读，请连接网络后确认草稿")
        }

        val res = apiClient.confirmDraft(currentUrl, token, draftId, req)
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
        val currentUrl = getActiveServerUrl()
        val token = dao.syncMeta(META_DEVICE_TOKEN)
            ?: throw IllegalStateException("设备未连接服务器，离线只读")
        val healthy = apiClient.checkHealth(currentUrl)
        if (!healthy) {
            _syncInfo.value = _syncInfo.value.copy(state = SyncState.OFFLINE, isOffline = true)
            throw IllegalStateException("离线只读，请连接网络后处理草稿")
        }
        apiClient.rejectDraft(currentUrl, token, draftId, reason)
    }

    suspend fun parseAllPendingDrafts(): List<StatementDraftDto> = withContext(Dispatchers.IO) {
        val currentUrl = getActiveServerUrl()
        val token = dao.syncMeta(META_DEVICE_TOKEN)
            ?: throw IllegalStateException("设备未连接服务器，离线只读")
        val healthy = apiClient.checkHealth(currentUrl)
        if (!healthy) {
            _syncInfo.value = _syncInfo.value.copy(state = SyncState.OFFLINE, isOffline = true)
            throw IllegalStateException("离线只读，请连接网络后解析邮件")
        }
        apiClient.parseAllPending(currentUrl, token)
    }

    private fun formatNow(): String {
        return DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")
            .withZone(ZoneId.systemDefault())
            .format(Instant.now())
    }
}