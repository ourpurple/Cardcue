"""Read-only IMAP client with strict read-only guarantees (no mark-as-read, no delete, no flags mutation)."""

import imaplib
import re
import ssl
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
            if self.use_ssl:
                ssl_context = ssl.create_default_context()
                self._client = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=ssl_context)
            else:
                self._client = imaplib.IMAP4(self.host, self.port)
                try:
                    self._client.starttls()
                except Exception:
                    pass

            status, data = self._client.login(self.username, self.password)
            if status != "OK":
                raise ImapAuthenticationError(f"IMAP login failed: {data}")
            self._connected = True
        except imaplib.IMAP4.error as e:
            raise ImapAuthenticationError(f"IMAP authentication failed: {e}") from e
        except Exception as e:
            raise ImapConnectionError(f"Failed to connect to IMAP server {self.host}:{self.port}: {e}") from e

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

    def search_uids_since(self, last_uid: int = 0, folder: str = "INBOX") -> list[int]:
        """Search for message UIDs strictly greater than last_uid."""
        self.select_folder(folder)
        if last_uid <= 0:
            status, data = self._client.uid("SEARCH", None, "ALL")
        else:
            status, data = self._client.uid("SEARCH", None, f"UID {last_uid + 1}:*")

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
        status, data = self._client.uid("FETCH", str(uid), "(BODY.PEEK[])")
        if status != "OK" or not data:
            raise ImapClientError(f"Failed to fetch UID {uid}: status={status}")

        for part in data:
            if isinstance(part, tuple) and len(part) >= 2:
                return part[1]
        raise ImapClientError(f"Incomplete or empty fetch response for UID {uid}")
