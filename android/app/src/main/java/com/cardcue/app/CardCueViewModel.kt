package com.cardcue.app

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.cardcue.app.data.Bill
import com.cardcue.app.data.BillRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch

data class CardCueState(val loading: Boolean = true, val bills: List<Bill> = emptyList(), val busy: Boolean = false, val error: String? = null)

class CardCueViewModel(private val repository: BillRepository) : ViewModel() {
    private val mutableState = MutableStateFlow(CardCueState())
    val state = mutableState.asStateFlow()
    private val eventChannel = Channel<String>(Channel.BUFFERED)
    val events = eventChannel.receiveAsFlow()

    init {
        viewModelScope.launch {
            try {
                repository.seedIfNeeded()
                repository.bills.collect { mutableState.value = mutableState.value.copy(loading = false, bills = it) }
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { mutableState.value = mutableState.value.copy(loading = false, error = "本地账单读取失败，请关闭后重试。") }
        }
    }

    fun recordPayment(id: String, amount: Long, note: String, onSuccess: () -> Unit) = mutate("已记录还款", onSuccess) {
        repository.recordPayment(id, amount, note)
    }
    fun voidPayment(id: String) = mutate("已撤销，待还金额已恢复") { repository.voidPayment(id) }

    private fun mutate(message: String, onSuccess: () -> Unit = {}, action: suspend () -> Unit) {
        if (mutableState.value.busy) return
        mutableState.value = mutableState.value.copy(busy = true)
        viewModelScope.launch {
            try { action(); onSuccess(); eventChannel.send(message) }
            catch (e: CancellationException) { throw e }
            catch (e: Exception) { eventChannel.send(if (e is IllegalArgumentException) e.message ?: "操作失败" else "保存失败，请重试") }
            finally { mutableState.value = mutableState.value.copy(busy = false) }
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
