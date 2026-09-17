package com.cardcue.app.domain

import com.cardcue.app.data.Bill
import java.time.LocalDate

data class HomeOverview(
    val bills: List<Bill>,
    val totals: Map<String, Long>,
    val dueSoonCount: Int,
)

object HomeRules {
    fun summarize(bills: List<Bill>, today: LocalDate): HomeOverview {
        // Conflicting rows must not silently become a second debt or be dropped.
        require(bills.map { it.statement.id }.distinct().size == bills.size)
        require(bills.map { Triple(it.statement.accountKey, it.statement.cycle, it.statement.currency) }
            .distinct().size == bills.size)
        val latestIds = bills.groupBy { it.statement.accountKey to it.statement.currency }
            .values.mapNotNull { group -> group.maxByOrNull { it.statement.dueDate }?.statement?.id }.toSet()
        val shown = bills.filter { !it.settled || it.statement.id in latestIds }
            .sortedWith(compareBy<Bill> { it.settled }.thenBy { it.statement.dueDate }.thenBy { it.statement.id })
        val pending = bills.filterNot { it.settled }
        val totals = pending.groupBy { it.statement.currency }.mapValues { (_, rows) ->
            rows.fold(0L) { sum, bill -> Math.addExact(sum, bill.remaining) }
        }
        return HomeOverview(shown, totals,
            pending.count { BillingRules.daysUntil(LocalDate.parse(it.statement.dueDate), today) in 0..6 })
    }
}
