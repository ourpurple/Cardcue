"""Read-only IMAP client with strict read-only guarantees (no mark-as-read, no delete, no flags mutation)."""

import imaplib
import re
import ssl
import socket
from cardcue_api.admin.outbound import resolve_public
from cardcue_api.config import settings
from typing import Any


class ImapClientError(Exception):
    """Base exception for IMAP client errors."""
    pass


class ImapAuthenticationError(ImapClientError):
    """Authentication failed."""
    pass


class ImapConnectionError(ImapClientError):
    """Connection or socket error."""
    pass


class ReadOnlyImapClient:
    r"""Strictly read-only IMAP client.

    Guarantees:
    1. Folders are always selected with readonly=True.
    2. Message payloads are fetched strictly with BODY.PEEK[], preventing the server from marking messages as \Seen.
    3. No deletion, flag alteration, or expunge methods are exposed or executed.
    """

    def __init__(
        self,
        host: str,
        port: int = 993,
        username: str = "",
        password: str = "",
        use_ssl: bool = True,
        timeout: float = 30.0,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.timeout = timeout
        self._client: imaplib.IMAP4 | None = None
        self._connected = False

    def connect(self) -> None:
        """Establish connection and authenticate."""
        try:
            ip = resolve_public(self.host, self.port)
            address = (ip, self.port)
            context = ssl.create_default_context()
            class PinnedPlain(imaplib.IMAP4):
                def _create_socket(inner, timeout):
                    return socket.create_connection(address, timeout)
            class PinnedTLS(imaplib.IMAP4_SSL):
                def _create_socket(inner, timeout):
                    raw = socket.create_connection(address, timeout)
                    return context.wrap_socket(raw, server_hostname=inner.host)
            if self.use_ssl:
                self._client = PinnedTLS(self.host, self.port, ssl_context=context, timeout=self.timeout)
            else:
                self._client = PinnedPlain(self.host, self.port, timeout=self.timeout)
                self._client.starttls(ssl_context=context)

            status, data = self._client.login(self.username, self.password)
            if status != "OK":
                raise ImapAuthenticationError("IMAP login failed")
            self._connected = True
        except imaplib.IMAP4.error as e:
            raise ImapAuthenticationError("IMAP authentication failed") from None
        except Exception as e:
            raise ImapConnectionError("IMAP connection or TLS failed") from None

    def disconnect(self) -> None:
        """Close connection gracefully."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            try:
                self._client.logout()
            except Exception:
                pass
            self._client = None
            self._connected = False

    def __enter__(self) -> "ReadOnlyImapClient":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.disconnect()

    def get_folder_status(self, folder: str = "INBOX") -> tuple[int, int, int]:
        """Fetch folder status: (uidvalidity, uidnext, total_messages)."""
        if not self._client:
            raise ImapConnectionError("Not connected to IMAP server")

        status, data = self._client.status(f'"{folder}"', "(UIDVALIDITY UIDNEXT MESSAGES)")
        if status != "OK" or not data:
            raise ImapClientError(f"Failed to get folder status for {folder}: {data}")

        status_str = data[0].decode("utf-8", errors="replace")
        uidvalidity = 0
        uidnext = 0
        messages = 0

        val_match = re.search(r"UIDVALIDITY\s+(\d+)", status_str, re.IGNORECASE)
        if val_match:
            uidvalidity = int(val_match.group(1))

        next_match = re.search(r"UIDNEXT\s+(\d+)", status_str, re.IGNORECASE)
        if next_match:
            uidnext = int(next_match.group(1))

        msg_match = re.search(r"MESSAGES\s+(\d+)", status_str, re.IGNORECASE)
        if msg_match:
            messages = int(msg_match.group(1))

        return uidvalidity, uidnext, messages

    def select_folder(self, folder: str = "INBOX") -> int:
        """Select a mailbox folder strictly in READ-ONLY mode.

        Returns total message count.
        """
        if not self._client:
            raise ImapConnectionError("Not connected to IMAP server")

        status, count_data = self._client.select(f'"{folder}"', readonly=True)
        if status != "OK":
            raise ImapClientError(f"Failed to select folder {folder} in read-only mode: {count_data}")

        try:
            return int(count_data[0])
        except (ValueError, TypeError, IndexError):
            return 0

    def search_uids_since(
        self,
        last_uid: int = 0,
        folder: str = "INBOX",
        since_date: Any = None,
    ) -> list[int]:
        """Search for message UIDs strictly greater than last_uid, optionally after since_date."""
        self.select_folder(folder)
        query_parts = []
        if last_uid > 0:
            query_parts.append(f"UID {last_uid + 1}:*")
        if since_date is not None:
            # IMAP date format: 01-Jan-2026
            query_parts.append(f'SINCE {since_date.strftime("%d-%b-%Y")}')

        query = " ".join(query_parts) if query_parts else "ALL"
        status, data = self._client.uid("SEARCH", None, query)

        if status != "OK" or not data:
            return []

        uids_str = data[0].decode("ascii", errors="ignore").split()
        uids = []
        for u in uids_str:
            try:
                uid_int = int(u)
                if uid_int > last_uid:
                    uids.append(uid_int)
            except ValueError:
                continue
        return sorted(list(set(uids)))

    def fetch_email_bytes(self, uid: int, folder: str = "INBOX") -> bytes:
        """Fetch RFC822 raw message bytes using BODY.PEEK[] to guarantee read-only behavior."""
        self.select_folder(folder)
        size_status, size_data = self._client.uid("FETCH", str(uid), "(RFC822.SIZE)")
        sizes = [int(n) for item in (size_data or []) if isinstance(item, bytes) for n in re.findall(rb"RFC822.SIZE (\d+)", item)]
        if size_status != "OK" or not sizes or max(sizes) > settings.mail_max_bytes:
            raise ImapClientError("Message size unavailable or exceeds limit")
        status, data = self._client.uid("FETCH", str(uid), f"(BODY.PEEK[]<0.{settings.mail_max_bytes + 1}>)")
        if status != "OK" or not data:
            raise ImapClientError(f"Failed to fetch UID {uid}: status={status}")

        for part in data:
            if isinstance(part, tuple) and len(part) >= 2:
                if len(part[1]) > settings.mail_max_bytes:
                    raise ImapClientError("Message exceeds size limit")
                return part[1]
        raise ImapClientError(f"Incomplete or empty fetch response for UID {uid}")
