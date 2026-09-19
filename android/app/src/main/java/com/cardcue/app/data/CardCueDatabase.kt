package com.cardcue.app.data

import androidx.room.*
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
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

@Entity(tableName = "synced_accounts")
data class SyncedAccount(
    @PrimaryKey val id: String,
    val bank: String,
    val alias: String?,
    val reference: String?,
    val status: String,
    val updatedAt: String,
)

@Entity(
    tableName = "synced_cards",
    indices = [Index("accountId")]
)
data class SyncedCard(
    @PrimaryKey val id: String,
    val accountId: String,
    val displayName: String?,
    val tail: String,
    val status: String,
)

@Entity(
    tableName = "synced_statements",
    indices = [Index("accountId")]
)
data class SyncedStatement(
    @PrimaryKey val id: String,
    val accountId: String,
    val currency: String,
    val statementDate: String,
    val dueDate: String,
    val currentVersionId: String?,
    val totalPaidMinor: Long,
    val remainingMinor: Long,
    val updatedAt: String,
)

@Entity(
    tableName = "synced_statement_versions",
    indices = [Index("statementId")]
)
data class SyncedStatementVersion(
    @PrimaryKey val id: String,
    val statementId: String,
    val versionNumber: Int,
    val amountMinor: Long,
    val minimumMinor: Long?,
    val source: String,
    val reason: String?,
    val confirmedAt: String?,
    val confirmedBy: String?,
)

@Entity(
    tableName = "synced_payments",
    indices = [Index("statementId")]
)
data class SyncedPayment(
    @PrimaryKey val id: String,
    val statementId: String,
    val amountMinor: Long,
    val currency: String,
    val note: String?,
    val recordedAt: String,
    val revokedAt: String?,
    val revokeReason: String?,
)

@Entity(tableName = "sync_meta")
data class SyncMeta(@PrimaryKey val key: String, val value: String)

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

    @Query("SELECT * FROM synced_accounts") fun observeSyncedAccounts(): Flow<List<SyncedAccount>>
    @Query("SELECT * FROM synced_cards") fun observeSyncedCards(): Flow<List<SyncedCard>>
    @Query("SELECT * FROM synced_statements ORDER BY dueDate ASC") fun observeSyncedStatements(): Flow<List<SyncedStatement>>
    @Query("SELECT * FROM synced_statement_versions") fun observeSyncedStatementVersions(): Flow<List<SyncedStatementVersion>>
    @Query("SELECT * FROM synced_payments ORDER BY recordedAt DESC") fun observeSyncedPayments(): Flow<List<SyncedPayment>>

    @Query("SELECT * FROM synced_accounts") suspend fun getSyncedAccounts(): List<SyncedAccount>
    @Query("SELECT * FROM synced_cards") suspend fun getSyncedCards(): List<SyncedCard>
    @Query("SELECT * FROM synced_statements") suspend fun getSyncedStatements(): List<SyncedStatement>
    @Query("SELECT * FROM synced_statement_versions") suspend fun getSyncedStatementVersions(): List<SyncedStatementVersion>
    @Query("SELECT * FROM synced_payments") suspend fun getSyncedPayments(): List<SyncedPayment>
    @Query("SELECT * FROM synced_statements WHERE id = :id") suspend fun getSyncedStatement(id: String): SyncedStatement?
    @Query("SELECT * FROM synced_payments WHERE id = :id") suspend fun getSyncedPayment(id: String): SyncedPayment?
    @Query("SELECT * FROM sync_meta") fun observeSyncMeta(): Flow<List<SyncMeta>>

    @Query("SELECT value FROM sync_meta WHERE `key` = :key") suspend fun syncMeta(key: String): String?
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun setSyncMeta(item: SyncMeta)

    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertSyncedAccounts(items: List<SyncedAccount>)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertSyncedCards(items: List<SyncedCard>)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertSyncedStatements(items: List<SyncedStatement>)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertSyncedStatementVersions(items: List<SyncedStatementVersion>)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertSyncedPayments(items: List<SyncedPayment>)

    @Query("DELETE FROM synced_accounts WHERE id = :id") suspend fun deleteSyncedAccount(id: String)
    @Query("DELETE FROM synced_cards WHERE id = :id") suspend fun deleteSyncedCard(id: String)
    @Query("DELETE FROM synced_statements WHERE id = :id") suspend fun deleteSyncedStatement(id: String)
    @Query("DELETE FROM synced_statement_versions WHERE id = :id") suspend fun deleteSyncedStatementVersion(id: String)
    @Query("DELETE FROM synced_payments WHERE id = :id") suspend fun deleteSyncedPayment(id: String)

    @Query("DELETE FROM synced_statement_versions") suspend fun clearSyncedVersions()
    @Query("DELETE FROM synced_payments") suspend fun clearSyncedPayments()
    @Query("DELETE FROM synced_statements") suspend fun clearSyncedStatements()
    @Query("DELETE FROM synced_cards") suspend fun clearSyncedCards()
    @Query("DELETE FROM synced_accounts") suspend fun clearSyncedAccounts()

    @Transaction
    suspend fun clearAllSyncedData() {
        clearSyncedVersions()
        clearSyncedPayments()
        clearSyncedStatements()
        clearSyncedCards()
        clearSyncedAccounts()
    }
}

@Database(
    entities = [
        Statement::class,
        Payment::class,
        AppMeta::class,
        SyncedAccount::class,
        SyncedCard::class,
        SyncedStatement::class,
        SyncedStatementVersion::class,
        SyncedPayment::class,
        SyncMeta::class,
    ],
    version = 2,
    exportSchema = true,
)
abstract class CardCueDatabase : RoomDatabase() {
    abstract fun dao(): CardCueDao

    companion object {
        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """CREATE TABLE IF NOT EXISTS `synced_accounts` (
                        `id` TEXT NOT NULL,
                        `bank` TEXT NOT NULL,
                        `alias` TEXT,
                        `reference` TEXT,
                        `status` TEXT NOT NULL,
                        `updatedAt` TEXT NOT NULL,
                        PRIMARY KEY(`id`)
                    )"""
                )
                db.execSQL(
                    """CREATE TABLE IF NOT EXISTS `synced_cards` (
                        `id` TEXT NOT NULL,
                        `accountId` TEXT NOT NULL,
                        `displayName` TEXT,
                        `tail` TEXT NOT NULL,
                        `status` TEXT NOT NULL,
                        PRIMARY KEY(`id`)
                    )"""
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_synced_cards_accountId` ON `synced_cards` (`accountId`)")
                db.execSQL(
                    """CREATE TABLE IF NOT EXISTS `synced_statements` (
                        `id` TEXT NOT NULL,
                        `accountId` TEXT NOT NULL,
                        `currency` TEXT NOT NULL,
                        `statementDate` TEXT NOT NULL,
                        `dueDate` TEXT NOT NULL,
                        `currentVersionId` TEXT,
                        `totalPaidMinor` INTEGER NOT NULL,
                        `remainingMinor` INTEGER NOT NULL,
                        `updatedAt` TEXT NOT NULL,
                        PRIMARY KEY(`id`)
                    )"""
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_synced_statements_accountId` ON `synced_statements` (`accountId`)")
                db.execSQL(
                    """CREATE TABLE IF NOT EXISTS `synced_statement_versions` (
                        `id` TEXT NOT NULL,
                        `statementId` TEXT NOT NULL,
                        `versionNumber` INTEGER NOT NULL,
                        `amountMinor` INTEGER NOT NULL,
                        `minimumMinor` INTEGER,
                        `source` TEXT NOT NULL,
                        `reason` TEXT,
                        `confirmedAt` TEXT,
                        `confirmedBy` TEXT,
                        PRIMARY KEY(`id`)
                    )"""
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_synced_statement_versions_statementId` ON `synced_statement_versions` (`statementId`)")
                db.execSQL(
                    """CREATE TABLE IF NOT EXISTS `synced_payments` (
                        `id` TEXT NOT NULL,
                        `statementId` TEXT NOT NULL,
                        `amountMinor` INTEGER NOT NULL,
                        `currency` TEXT NOT NULL,
                        `note` TEXT,
                        `recordedAt` TEXT NOT NULL,
                        `revokedAt` TEXT,
                        `revokeReason` TEXT,
                        PRIMARY KEY(`id`)
                    )"""
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_synced_payments_statementId` ON `synced_payments` (`statementId`)")
                db.execSQL(
                    """CREATE TABLE IF NOT EXISTS `sync_meta` (
                        `key` TEXT NOT NULL,
                        `value` TEXT NOT NULL,
                        PRIMARY KEY(`key`)
                    )"""
                )
            }
        }
    }
}
