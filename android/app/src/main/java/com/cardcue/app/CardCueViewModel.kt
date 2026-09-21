package com.cardcue.app

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.cardcue.app.data.Bill
import com.cardcue.app.data.BillRepository
import com.cardcue.app.data.SyncedAccount
import com.cardcue.app.data.SyncedCard
import com.cardcue.app.sync.StatementDraftConfirmRequestDto
import com.cardcue.app.sync.StatementDraftDto
import com.cardcue.app.sync.SyncApiException
import com.cardcue.app.sync.SyncInfo
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class CardCueState(
    val loading: Boolean = true,
    val bills: List<Bill> = emptyList(),
    val busy: Boolean = false,
    val error: String? = null
)

class CardCueViewModel(private val repository: BillRepository) : ViewModel() {
    private val mutableState = MutableStateFlow(CardCueState())
    val state = mutableState.asStateFlow()
    private val eventChannel = Channel<String>(Channel.BUFFERED)
    val events = eventChannel.receiveAsFlow()

    val syncInfo: StateFlow<SyncInfo> = repository.syncManager?.syncInfo
        ?: MutableStateFlow(SyncInfo()).asStateFlow()

    private val _pendingDrafts = MutableStateFlow<List<StatementDraftDto>>(emptyList())
    val pendingDrafts: StateFlow<List<StatementDraftDto>> = _pendingDrafts.asStateFlow()

    val syncedAccounts: StateFlow<List<SyncedAccount>> = repository.syncedAccounts
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val syncedCards: StateFlow<List<SyncedCard>> = repository.syncedCards
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    init {
        viewModelScope.launch {
            try {
                repository.seedIfNeeded()
                repository.syncManager?.init()
                launch {
                    val ok = repository.syncManager?.syncNow() ?: false
                    if (ok) {
                        loadPendingDrafts()
                    }
                }
                repository.bills.collect { mutableState.value = mutableState.value.copy(loading = false, bills = it) }
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { mutableState.value = mutableState.value.copy(loading = false, error = "本地账单读取失败，请关闭后重试。") }
        }
    }

    fun pairDevice(
        serverUrl: String,
        pairingCode: String,
        deviceName: String? = null,
        onSuccess: () -> Unit = {},
        onError: (String) -> Unit = {}
    ) {
        viewModelScope.launch {
            val sync = repository.syncManager
            if (sync == null) {
                onError("同步管理器未初始化")
                return@launch
            }
            try {
                mutableState.value = mutableState.value.copy(busy = true)
                sync.pairWithCode(serverUrl, pairingCode, deviceName)
                loadPendingDrafts()
                eventChannel.send("设备配对成功！账单已同步")
                onSuccess()
            } catch (e: Exception) {
                val msg = when (e) {
                    is SyncApiException -> e.message ?: "配对请求失败 (${e.statusCode})"
                    else -> e.message ?: "配对失败"
                }
                onError(msg)
                eventChannel.send("配对失败: $msg")
            } finally {
                mutableState.value = mutableState.value.copy(busy = false)
            }
        }
    }

    fun unpairDevice(onComplete: () -> Unit = {}) {
        viewModelScope.launch {
            val sync = repository.syncManager
            if (sync == null) {
                onComplete()
                return@launch
            }
            try {
                mutableState.value = mutableState.value.copy(busy = true)
                sync.unpairDevice()
                _pendingDrafts.value = emptyList()
                eventChannel.send("已解除配对，恢复本地演示模式")
                onComplete()
            } catch (e: Exception) {
                eventChannel.send("解除配对失败: ${e.message ?: "未知错误"}")
            } finally {
                mutableState.value = mutableState.value.copy(busy = false)
            }
        }
    }

    fun syncNow() {
        viewModelScope.launch {
            val sync = repository.syncManager
            if (sync != null) {
                val ok = sync.syncNow()
                if (!ok) {
                    val msg = sync.syncInfo.value.message ?: "同步未完成"
                    eventChannel.send(msg)
                } else {
                    eventChannel.send("账单同步成功")
                    loadPendingDrafts()
                }
            } else {
                eventChannel.send("本地演示模式，未配置同步服务器")
            }
        }
    }

    fun checkNewEmails() {
        viewModelScope.launch {
            val sync = repository.syncManager
            if (sync != null) {
                try {
                    val res = sync.triggerMailSync()
                    val count = res.jobIds.size
                    val msg = if (count > 0) "已触发后台检查邮件 (共 ${count} 个任务)" else res.message.ifBlank { "已检查邮件" }
                    eventChannel.send(msg)
                    delay(1500)
                    parsePendingEmails()
                } catch (e: Exception) {
                    val errMsg = e.message ?: "网络异常"
                    eventChannel.send("检查邮件失败: $errMsg")
                }
            } else {
                eventChannel.send("本地演示模式，未配置同步服务器")
            }
        }
    }

    fun loadPendingDrafts() {
        viewModelScope.launch {
            val sync = repository.syncManager ?: return@launch
            try {
                _pendingDrafts.value = sync.fetchPendingDrafts()
            } catch (e: Exception) {
                // Keep existing drafts on error
            }
        }
    }

    fun confirmDraft(
        draftId: String,
        req: StatementDraftConfirmRequestDto,
        onSuccess: () -> Unit = {}
    ) = mutate("草稿已确认入账", onSuccess) {
        val sync = repository.syncManager ?: throw IllegalStateException("离线模式，无法确认草稿")
        sync.confirmDraftOnline(draftId, req)
        loadPendingDrafts()
    }

    fun rejectDraft(
        draftId: String,
        reason: String,
        onSuccess: () -> Unit = {}
    ) = mutate("已忽略草稿", onSuccess) {
        val sync = repository.syncManager ?: throw IllegalStateException("离线模式，无法操作草稿")
        sync.rejectDraftOnline(draftId, reason)
        loadPendingDrafts()
    }

    fun parsePendingEmails() {
        viewModelScope.launch {
            val sync = repository.syncManager
            if (sync != null) {
                try {
                    val drafts = sync.parseAllPendingDrafts()
                    _pendingDrafts.value = sync.fetchPendingDrafts()
                    val count = drafts.size
                    val msg = if (count > 0) "已解析 ${count} 封账单邮件" else "暂无新的待解析邮件"
                    eventChannel.send(msg)
                } catch (e: Exception) {
                    val errMsg = e.message ?: "网络异常"
                    eventChannel.send("解析失败: $errMsg")
                }
            } else {
                eventChannel.send("本地演示模式，未配置同步服务器")
            }
        }
    }

    fun resetAllData(onComplete: () -> Unit = {}) {
        viewModelScope.launch {
            try {
                mutableState.value = mutableState.value.copy(busy = true)
                repository.resetAllLocalData()
                _pendingDrafts.value = emptyList()
                val sync = repository.syncManager
                if (sync != null) {
                    sync.syncNow()
                    loadPendingDrafts()
                }
                eventChannel.send("已重置本地数据并重新拉取")
                onComplete()
            } catch (e: Exception) {
                eventChannel.send("重置数据失败: ${e.message ?: "未知错误"}")
            } finally {
                mutableState.value = mutableState.value.copy(busy = false)
            }
        }
    }

    fun recordPayment(id: String, amount: Long, note: String, onSuccess: () -> Unit) = mutate("已记录还款", onSuccess) {
        repository.recordPayment(id, amount, note)
    }

    fun voidPayment(id: String) = mutate("已撤销，待还金额已恢复") {
        repository.voidPayment(id)
    }

    private fun mutate(message: String, onSuccess: () -> Unit = {}, action: suspend () -> Unit) {
        if (mutableState.value.busy) return
        mutableState.value = mutableState.value.copy(busy = true)
        viewModelScope.launch {
            try {
                action()
                onSuccess()
                eventChannel.send(message)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                val errorMsg = when (e) {
                    is IllegalArgumentException -> e.message ?: "操作失败"
                    is IllegalStateException -> e.message ?: "操作受限"
                    is SyncApiException -> e.message ?: "网络请求失败"
                    else -> e.message ?: "保存失败，请重试"
                }
                eventChannel.send(errorMsg)
            } finally {
                mutableState.value = mutableState.value.copy(busy = false)
            }
        }
    }

    class Factory(private val repository: BillRepository) : ViewModelProvider.Factory {
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(CardCueViewModel::class.java))
            @Suppress("UNCHECKED_CAST")
            return CardCueViewModel(repository) as T
        }
    }
}
