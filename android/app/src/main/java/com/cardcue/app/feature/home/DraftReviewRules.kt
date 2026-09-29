package com.cardcue.app.feature.home

import com.cardcue.app.data.SyncedAccount
import com.cardcue.app.data.SyncedCard

/** A draft's bank and tails are evidence, never an account identifier. */
internal fun canConfirmDraftAccount(
    account: SyncedAccount?,
    accountCards: List<SyncedCard>,
    draftCardTails: List<String>,
): Boolean {
    if (account?.status != "active") return false
    return when (account.billingMode) {
        "consolidated" -> true
        "per_card" -> {
            val activeCards = accountCards.filter { it.accountId == account.id && it.status == "active" }
            activeCards.size == 1 && draftCardTails.distinct().size <= 1 &&
                (draftCardTails.isEmpty() || activeCards.single().tail in draftCardTails)
        }
        else -> false
    }
}

/** Money.parse currently uses two decimal places and only supports these currencies. */
internal fun supportedDraftCurrency(input: String): String? =
    input.trim().uppercase().takeIf { it == "CNY" || it == "USD" }
