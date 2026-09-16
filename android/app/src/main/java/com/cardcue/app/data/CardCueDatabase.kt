package com.cardcue.app.data

import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "statements", indices = [Index(value = ["accountKey", "cycle", "currency"], unique = true)])
data class Statement(
    @PrimaryKey val id: String,
    val accountKey: String,
    val bank: String,
    val bankMark: String,
    val color: Long,
    val cardTails: String,
    val cycle: String,
    val currency: String,
    val amountMinor: Long,
    val minimumMinor: Long,
    val statementDate: String,
    val dueDate: String,
    val source: String = "内置演示账单",
    val isDemo: Boolean = true,
)

@Entity(
    tableName = "payments",
    foreignKeys = [ForeignKey(entity = Statement::class, parentColumns = ["id"], childColumns = ["statementId"], onDelete = ForeignKey.RESTRICT)],
    indices = [Index("statementId")],
)
data class Payment(
    @PrimaryKey val id: String,
    val statementId: String,
    val amountMinor: Long,
    val recordedAt: Long,
    val note: String,
    val voidedAt: Long? = null,
)

@Entity(tableName = "app_meta")
data class AppMeta(@PrimaryKey val key: String, val value: String)

@Dao
interface CardCueDao {
    @Query("SELECT * FROM statements ORDER BY dueDate ASC") fun observeStatements(): Flow<List<Statement>>
    @Query("SELECT * FROM payments ORDER BY recordedAt DESC") fun observePayments(): Flow<List<Payment>>
    @Query("SELECT * FROM statements WHERE id = :id") suspend fun statement(id: String): Statement?
    @Query("SELECT * FROM payments WHERE statementId = :id AND voidedAt IS NULL") suspend fun activePayments(id: String): List<Payment>
    @Query("SELECT * FROM payments WHERE id = :id") suspend fun payment(id: String): Payment?
    @Query("SELECT value FROM app_meta WHERE `key` = :key") suspend fun meta(key: String): String?
    @Insert suspend fun insertStatements(items: List<Statement>)
    @Insert suspend fun insertPayment(item: Payment)
    @Insert suspend fun insertMeta(item: AppMeta)
    @Query("UPDATE payments SET voidedAt = :time WHERE id = :id AND voidedAt IS NULL") suspend fun voidPayment(id: String, time: Long): Int
}

@Database(entities = [Statement::class, Payment::class, AppMeta::class], version = 1, exportSchema = true)
abstract class CardCueDatabase : RoomDatabase() {
    abstract fun dao(): CardCueDao
}
