package com.cardcue.app.sync

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

class CursorOutOfRangeException(message: String) : Exception(message)
class SyncAuthException(message: String) : Exception(message)
class SyncApiException(val statusCode: Int, message: String) : Exception(message)

class SyncApiClient(private val timeoutMs: Int = 15_000) {

    fun checkHealth(baseUrl: String): Boolean {
        return try {
            val url = URL("$baseUrl/health")
            val conn = (url.openConnection() as HttpURLConnection).apply {
                connectTimeout = 5_000
                readTimeout = 5_000
                requestMethod = "GET"
            }
            conn.responseCode == 200
        } catch (_: Exception) {
            false
        }
    }

    fun pairDevice(baseUrl: String, deviceName: String, pairingCode: String): PairResponse {
        val payload = JSONObject().apply {
            put("name", deviceName)
            put("pairing_code", pairingCode)
        }
        val (code, body) = executeRequest(
            urlStr = "$baseUrl/v1/devices/pair",
            method = "POST",
            jsonBody = payload.toString()
        )
        if (code != 200 && code != 201) {
            val errorDetail = try {
                val json = JSONObject(body)
                val detailObj = json.opt("detail")
                when (detailObj) {
                    is String -> detailObj
                    is JSONArray -> {
                        val messages = mutableListOf<String>()
                        for (i in 0 until detailObj.length()) {
                            val item = detailObj.optJSONObject(i)
                            if (item != null) {
                                val field = item.optJSONArray("loc")?.let { loc ->
                                    (0 until loc.length()).map { loc.getString(it) }.filter { it != "body" }.joinToString(".")
                                } ?: ""
                                val msg = item.optString("msg", "")
                                if (field.isNotBlank()) messages.add("$field: $msg") else messages.add(msg)
                            } else {
                                messages.add(detailObj.getString(i))
                            }
                        }
                        messages.joinToString("; ")
                    }
                    else -> body
                }
            } catch (_: Exception) {
                body
            }
            throw SyncApiException(code, if (errorDetail.isNotBlank()) errorDetail else "设备配对失败 ($code)")
        }
        val json = JSONObject(body)
        return PairResponse(
            deviceId = json.getString("device_id"),
            name = json.getString("name"),
            token = json.getString("token"),
        )
    }

    fun getBootstrap(baseUrl: String, token: String): SyncBootstrapResponse {
        val (code, body) = executeRequest(
            urlStr = "$baseUrl/v1/sync/bootstrap",
            method = "GET",
            token = token
        )
        if (code == 401) throw SyncAuthException("Unauthorized device token")
        if (code != 200) throw SyncApiException(code, "Bootstrap failed ($code): $body")

        val json = JSONObject(body)
        return parseBootstrapResponse(json)
    }

    fun getChanges(baseUrl: String, token: String, cursor: Long, limit: Int = 100): SyncChangesResponse {
        val (code, body) = executeRequest(
            urlStr = "$baseUrl/v1/sync/changes?cursor=$cursor&limit=$limit",
            method = "GET",
            token = token
        )
        if (code == 401) throw SyncAuthException("Unauthorized device token")
        if (code == 409 && body.contains("CURSOR_OUT_OF_RANGE")) {
            throw CursorOutOfRangeException("Cursor $cursor out of range")
        }
        if (code != 200) throw SyncApiException(code, "Fetch changes failed ($code): $body")

        val json = JSONObject(body)
        return parseChangesResponse(json)
    }

    fun recordPayment(baseUrl: String, token: String, req: PaymentCreateRequest): SyncPaymentResponse {
        val payload = JSONObject().apply {
            put("statement_id", req.statementId)
            put("amount_minor", req.amountMinor)
            put("currency", req.currency)
            if (!req.note.isNullOrBlank()) {
                put("note", req.note)
            }
            put("request_id", req.requestId)
        }
        val (code, body) = executeRequest(
            urlStr = "$baseUrl/v1/sync/payments",
            method = "POST",
            jsonBody = payload.toString(),
            token = token
        )
        if (code == 401) throw SyncAuthException("Unauthorized device token")
        if (code != 200 && code != 201) {
            throw SyncApiException(code, "Record payment failed ($code): $body")
        }
        val json = JSONObject(body)
        return SyncPaymentResponse(
            payment = parsePaymentDto(json.getJSONObject("payment")),
            created = json.optBoolean("created", true),
            statementDetail = parseStatementDetailDto(json.getJSONObject("statement_detail"))
        )
    }

    fun revokePayment(baseUrl: String, token: String, paymentId: String, reason: String): SyncPaymentResponse {
        val payload = JSONObject().apply {
            put("reason", reason)
        }
        val (code, body) = executeRequest(
            urlStr = "$baseUrl/v1/sync/payments/$paymentId/revoke",
            method = "POST",
            jsonBody = payload.toString(),
            token = token
        )
        if (code == 401) throw SyncAuthException("Unauthorized device token")
        if (code != 200) throw SyncApiException(code, "Revoke payment failed ($code): $body")

        val json = JSONObject(body)
        return SyncPaymentResponse(
            payment = parsePaymentDto(json.getJSONObject("payment")),
            created = false,
            statementDetail = parseStatementDetailDto(json.getJSONObject("statement_detail"))
        )
    }

    fun triggerMailSync(baseUrl: String, token: String, mailboxId: String? = null): MailSyncTriggerResult {
        val payload = JSONObject().apply {
            if (mailboxId != null) {
                put("mailbox_id", mailboxId)
            }
        }
        val (code, body) = executeRequest(
            urlStr = "$baseUrl/v1/mail/sync-now",
            method = "POST",
            jsonBody = payload.toString(),
            token = token
        )
        if (code == 401) throw SyncAuthException("Unauthorized device token")
        if (code != 200 && code != 201) {
            throw SyncApiException(code, "Trigger mail sync failed ($code): $body")
        }
        val json = JSONObject(body)
        val arr = json.optJSONArray("job_ids") ?: JSONArray()
        val list = mutableListOf<String>()
        for (i in 0 until arr.length()) {
            list.add(arr.getString(i))
        }
        return MailSyncTriggerResult(
            jobIds = list,
            message = json.optString("message", "")
        )
    }

    fun getMailJobs(baseUrl: String, token: String, mailboxId: String? = null, limit: Int = 10): List<MailJobDto> {
        val query = buildString {
            append("?limit=").append(limit)
            if (mailboxId != null) {
                append("&mailbox_id=").append(mailboxId)
            }
        }
        val (code, body) = executeRequest(
            urlStr = "$baseUrl/v1/mail/jobs$query",
            method = "GET",
            token = token
        )
        if (code == 401) throw SyncAuthException("Unauthorized device token")
        if (code != 200) {
            throw SyncApiException(code, "Fetch mail jobs failed ($code): $body")
        }
        val arr = JSONArray(body)
        val list = mutableListOf<MailJobDto>()
        for (i in 0 until arr.length()) {
            val j = arr.getJSONObject(i)
            list.add(
                MailJobDto(
                    id = j.getString("id"),
                    mailboxId = j.getString("mailbox_id"),
                    triggerType = j.getString("trigger_type"),
                    status = j.getString("status"),
                    startedAt = if (j.isNull("started_at")) null else j.getString("started_at"),
                    finishedAt = if (j.isNull("finished_at")) null else j.getString("finished_at"),
                    errorMessage = if (j.isNull("error_message")) null else j.getString("error_message"),
                    emailsChecked = j.optInt("emails_checked", 0),
                    emailsFetched = j.optInt("emails_fetched", 0),
                    statementCandidates = j.optInt("statement_candidates", 0),
                    createdAt = j.optString("created_at", "")
                )
            )
        }
        return list
    }

    fun getDrafts(baseUrl: String, token: String, status: String = "pending_review"): List<StatementDraftDto> {
        val (code, body) = executeRequest(
            urlStr = "$baseUrl/v1/drafts?status=$status",
            method = "GET",
            token = token
        )
        if (code == 401) throw SyncAuthException("Unauthorized device token")
        if (code != 200) throw SyncApiException(code, "Fetch drafts failed ($code): $body")
        val arr = JSONArray(body)
        val list = mutableListOf<StatementDraftDto>()
        for (i in 0 until arr.length()) {
            list.add(parseDraftDto(arr.getJSONObject(i)))
        }
        return list
    }

    fun getDraftDetail(baseUrl: String, token: String, draftId: String): StatementDraftDto {
        val (code, body) = executeRequest(
            urlStr = "$baseUrl/v1/drafts/$draftId",
            method = "GET",
            token = token
        )
        if (code == 401) throw SyncAuthException("Unauthorized device token")
        if (code != 200) throw SyncApiException(code, "Get draft detail failed ($code): $body")
        return parseDraftDto(JSONObject(body))
    }

    fun confirmDraft(
        baseUrl: String,
        token: String,
        draftId: String,
        req: StatementDraftConfirmRequestDto
    ): StatementDraftConfirmResponseDto {
        val payload = JSONObject().apply {
            put("account_id", req.accountId)
            if (req.cardId != null) put("card_id", req.cardId)
            if (req.currency != null) put("currency", req.currency)
            if (req.amountMinor != null) put("amount_minor", req.amountMinor)
            if (req.minimumMinor != null) put("minimum_minor", req.minimumMinor)
            if (req.statementDate != null) put("statement_date", req.statementDate)
            if (req.dueDate != null) put("due_date", req.dueDate)
        }
        val (code, body) = executeRequest(
            urlStr = "$baseUrl/v1/drafts/$draftId/confirm",
            method = "POST",
            jsonBody = payload.toString(),
            token = token
        )
        if (code == 401) throw SyncAuthException("Unauthorized device token")
        if (code != 200) throw SyncApiException(code, "Confirm draft failed ($code): $body")

        val json = JSONObject(body)
        return StatementDraftConfirmResponseDto(
            draftId = json.getString("draft_id"),
            statement = parseStatementDetailDto(json.getJSONObject("statement")),
            version = parseStatementVersionDto(json.getJSONObject("version"))
        )
    }

    fun rejectDraft(baseUrl: String, token: String, draftId: String, reason: String): StatementDraftDto {
        val payload = JSONObject().apply {
            put("reason", reason)
        }
        val (code, body) = executeRequest(
            urlStr = "$baseUrl/v1/drafts/$draftId/reject",
            method = "POST",
            jsonBody = payload.toString(),
            token = token
        )
        if (code == 401) throw SyncAuthException("Unauthorized device token")
        if (code != 200) throw SyncApiException(code, "Reject draft failed ($code): $body")
        return parseDraftDto(JSONObject(body))
    }

    fun parseAllPending(baseUrl: String, token: String): List<StatementDraftDto> {
        val (code, body) = executeRequest(
            urlStr = "$baseUrl/v1/drafts/parse-all-pending",
            method = "POST",
            token = token
        )
        if (code == 401) throw SyncAuthException("Unauthorized device token")
        if (code != 200) throw SyncApiException(code, "Parse all pending drafts failed ($code): $body")
        val arr = JSONArray(body)
        val list = mutableListOf<StatementDraftDto>()
        for (i in 0 until arr.length()) {
            list.add(parseDraftDto(arr.getJSONObject(i)))
        }
        return list
    }

    private fun executeRequest(
        urlStr: String,
        method: String,
        jsonBody: String? = null,
        token: String? = null
    ): Pair<Int, String> {
        val url = URL(urlStr)
        val conn = (url.openConnection() as HttpURLConnection).apply {
            connectTimeout = timeoutMs
            readTimeout = timeoutMs
            requestMethod = method
            setRequestProperty("Accept", "application/json")
            if (token != null) {
                setRequestProperty("Authorization", "Bearer $token")
            }
            if (jsonBody != null) {
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
                doOutput = true
            }
        }

        if (jsonBody != null) {
            OutputStreamWriter(conn.outputStream, "UTF-8").use { it.write(jsonBody) }
        }

        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val responseBody = stream?.let {
            BufferedReader(InputStreamReader(it, "UTF-8")).use { reader -> reader.readText() }
        } ?: ""

        return Pair(code, responseBody)
    }

    private fun parseBootstrapResponse(json: JSONObject): SyncBootstrapResponse {
        val accounts = mutableListOf<AccountDto>()
        val acctArr = json.optJSONArray("accounts") ?: JSONArray()
        for (i in 0 until acctArr.length()) {
            val a = acctArr.getJSONObject(i)
            accounts.add(
                AccountDto(
                    id = a.getString("id"),
                    bank = a.getString("bank"),
                    alias = if (a.isNull("alias")) null else a.getString("alias"),
                    reference = if (a.isNull("reference")) null else a.getString("reference"),
                    status = a.optString("status", "active"),
                    createdAt = a.optString("created_at", ""),
                    updatedAt = a.optString("updated_at", "")
                )
            )
        }

        val cards = mutableListOf<CardDto>()
        val cardArr = json.optJSONArray("cards") ?: JSONArray()
        for (i in 0 until cardArr.length()) {
            val c = cardArr.getJSONObject(i)
            cards.add(
                CardDto(
                    id = c.getString("id"),
                    accountId = c.getString("account_id"),
                    displayName = if (c.isNull("display_name")) null else c.getString("display_name"),
                    tail = c.getString("tail"),
                    status = c.optString("status", "active"),
                    createdAt = c.optString("created_at", "")
                )
            )
        }

        val statements = mutableListOf<StatementDetailDto>()
        val stArr = json.optJSONArray("statements") ?: JSONArray()
        for (i in 0 until stArr.length()) {
            statements.add(parseStatementDetailDto(stArr.getJSONObject(i)))
        }

        val payments = mutableListOf<PaymentDto>()
        val payArr = json.optJSONArray("payments") ?: JSONArray()
        for (i in 0 until payArr.length()) {
            payments.add(parsePaymentDto(payArr.getJSONObject(i)))
        }

        return SyncBootstrapResponse(
            cursor = json.getLong("cursor"),
            serverTime = json.getString("server_time"),
            accounts = accounts,
            cards = cards,
            statements = statements,
            payments = payments
        )
    }

    private fun parseChangesResponse(json: JSONObject): SyncChangesResponse {
        val changes = mutableListOf<SyncChangeItemDto>()
        val chArr = json.optJSONArray("changes") ?: JSONArray()
        for (i in 0 until chArr.length()) {
            val item = chArr.getJSONObject(i)
            val snapshotMap = if (item.isNull("snapshot")) null else {
                val s = item.getJSONObject("snapshot")
                val map = mutableMapOf<String, Any?>()
                for (key in s.keys()) {
                    map[key] = if (s.isNull(key)) null else s.get(key)
                }
                map
            }
            changes.add(
                SyncChangeItemDto(
                    seq = item.getLong("seq"),
                    entityType = item.getString("entity_type"),
                    entityId = item.getString("entity_id"),
                    action = item.getString("action"),
                    snapshot = snapshotMap,
                    createdAt = item.getString("created_at")
                )
            )
        }
        return SyncChangesResponse(
            cursor = json.getLong("cursor"),
            hasMore = json.optBoolean("has_more", false),
            changes = changes,
            serverTime = json.getString("server_time")
        )
    }

    private fun parseStatementVersionDto(v: JSONObject): StatementVersionDto {
        return StatementVersionDto(
            id = v.getString("id"),
            statementId = v.getString("statement_id"),
            versionNumber = v.getInt("version_number"),
            amountMinor = v.getLong("amount_minor"),
            minimumMinor = if (v.isNull("minimum_minor")) null else v.getLong("minimum_minor"),
            source = v.optString("source", "manual"),
            reason = if (v.isNull("reason")) null else v.getString("reason"),
            confirmedAt = if (v.isNull("confirmed_at")) null else v.getString("confirmed_at"),
            confirmedBy = if (v.isNull("confirmed_by")) null else v.getString("confirmed_by"),
            createdAt = v.optString("created_at", "")
        )
    }

    private fun parseStatementDetailDto(s: JSONObject): StatementDetailDto {
        val versionDto = if (s.isNull("current_version")) null else {
            parseStatementVersionDto(s.getJSONObject("current_version"))
        }

        return StatementDetailDto(
            id = s.getString("id"),
            accountId = s.getString("account_id"),
            currency = s.getString("currency"),
            statementDate = s.getString("statement_date"),
            dueDate = s.getString("due_date"),
            currentVersionId = if (s.isNull("current_version_id")) null else s.getString("current_version_id"),
            createdAt = s.optString("created_at", ""),
            updatedAt = s.optString("updated_at", ""),
            currentVersion = versionDto,
            totalPaidMinor = s.optLong("total_paid_minor", 0L),
            remainingMinor = s.optLong("remaining_minor", 0L)
        )
    }

    private fun parsePaymentDto(p: JSONObject): PaymentDto {
        val revokedAt = if (p.isNull("revoked_at")) null else p.getString("revoked_at")
        return PaymentDto(
            id = p.getString("id"),
            statementId = p.getString("statement_id"),
            amountMinor = p.getLong("amount_minor"),
            currency = p.getString("currency"),
            note = if (p.isNull("note")) null else p.getString("note"),
            recordedAt = p.getString("recorded_at"),
            revokedAt = revokedAt,
            revokeReason = if (p.isNull("revoke_reason")) null else p.getString("revoke_reason")
        )
    }

    private fun parseDraftDto(d: JSONObject): StatementDraftDto {
        val tails = mutableListOf<String>()
        val tailArr = d.optJSONArray("card_tails")
        if (tailArr != null) {
            for (i in 0 until tailArr.length()) {
                tails.add(tailArr.getString(i))
            }
        }

        val evidences = mutableListOf<EvidenceSnippetDto>()
        val evArr = d.optJSONArray("evidence")
        if (evArr != null) {
            for (i in 0 until evArr.length()) {
                val ev = evArr.getJSONObject(i)
                evidences.add(
                    EvidenceSnippetDto(
                        field = ev.optString("field", ""),
                        snippet = ev.optString("snippet", ""),
                        sourceType = ev.optString("source_type", "html"),
                        confidence = ev.optDouble("confidence", 1.0)
                    )
                )
            }
        }

        val reasons = mutableListOf<String>()
        val rrArr = d.optJSONArray("review_reasons")
        if (rrArr != null) {
            for (i in 0 until rrArr.length()) {
                reasons.add(rrArr.getString(i))
            }
        }

        return StatementDraftDto(
            id = d.getString("id"),
            emailSourceId = if (d.isNull("email_source_id")) null else d.getString("email_source_id"),
            mailboxId = if (d.isNull("mailbox_id")) null else d.getString("mailbox_id"),
            status = d.getString("status"),
            bank = if (d.isNull("bank")) null else d.getString("bank"),
            currency = if (d.isNull("currency")) null else d.getString("currency"),
            amountMinor = if (d.isNull("amount_minor")) null else d.getLong("amount_minor"),
            minimumMinor = if (d.isNull("minimum_minor")) null else d.getLong("minimum_minor"),
            statementDate = if (d.isNull("statement_date")) null else d.getString("statement_date"),
            dueDate = if (d.isNull("due_date")) null else d.getString("due_date"),
            accountReference = if (d.isNull("account_reference")) null else d.getString("account_reference"),
            cardTails = tails,
            evidence = evidences,
            reviewReasons = reasons,
            matchedAccountId = if (d.isNull("matched_account_id")) null else d.getString("matched_account_id"),
            matchedCardId = if (d.isNull("matched_card_id")) null else d.getString("matched_card_id"),
            confirmedVersionId = if (d.isNull("confirmed_version_id")) null else d.getString("confirmed_version_id"),
            rejectionReason = if (d.isNull("rejection_reason")) null else d.getString("rejection_reason"),
            extractorName = d.optString("extractor_name", ""),
            createdAt = d.optString("created_at", ""),
            updatedAt = d.optString("updated_at", "")
        )
    }
}
