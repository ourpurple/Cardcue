"""File storage manager for raw email payloads and attachments with strict path safety."""

import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cardcue_api.config import settings


class MailStorageError(Exception):
    pass


class MailStorageManager:
    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir or settings.mail_storage_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_target_dir(self, mailbox_id: uuid.UUID | str, email_source_id: uuid.UUID | str, email_date: datetime | None) -> Path:
        dt = email_date or datetime.now(timezone.utc)
        year_month = dt.strftime("%Y-%m")
        target = self.base_dir / str(mailbox_id) / year_month / str(email_source_id)
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _verify_safe_path(self, path: Path) -> Path:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.base_dir):
            raise MailStorageError(f"Path traversal detected: {path} is outside storage root {self.base_dir}")
        return resolved

    def save_raw_email(
        self,
        mailbox_id: uuid.UUID | str,
        email_source_id: uuid.UUID | str,
        raw_bytes: bytes,
        email_date: datetime | None = None,
    ) -> str:
        target_dir = self._get_target_dir(mailbox_id, email_source_id, email_date)
        file_path = target_dir / "raw.eml"
        safe_path = self._verify_safe_path(file_path)
        safe_path.write_bytes(raw_bytes)
        return str(safe_path)

    def save_attachment(
        self,
        mailbox_id: uuid.UUID | str,
        email_source_id: uuid.UUID | str,
        filename: str,
        payload_bytes: bytes,
        email_date: datetime | None = None,
    ) -> str:
        target_dir = self._get_target_dir(mailbox_id, email_source_id, email_date) / "attachments"
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / (str(uuid.uuid4()) + "-" + __import__("cardcue_api.mail.parser", fromlist=["sanitize_filename"]).sanitize_filename(filename))
        safe_path = self._verify_safe_path(file_path)
        safe_path.write_bytes(payload_bytes)
        return str(safe_path)

    def is_file_available(self, storage_path: str) -> bool:
        try:
            file_path = Path(storage_path).resolve()
            safe_path = self._verify_safe_path(file_path)
            return safe_path.exists() and safe_path.is_file()
        except Exception:
            return False

    def read_file(self, storage_path: str) -> bytes:
        file_path = Path(storage_path).resolve()
        safe_path = self._verify_safe_path(file_path)
        if not safe_path.exists() or not safe_path.is_file():
            raise MailStorageError(f"Storage file expired or not found: {storage_path}")
        return safe_path.read_bytes()

    def cleanup_expired_storage(self, max_age_days: int = 180) -> int:
        """Delete raw files older than max_age_days retention period while keeping directories clean."""
        now_ts = time.time()
        max_age_seconds = max_age_days * 86400
        removed_count = 0

        for root, dirs, files in os.walk(self.base_dir, topdown=False):
            for file_name in files:
                fpath = Path(root) / file_name
                try:
                    mtime = fpath.stat().st_mtime
                    if now_ts - mtime > max_age_seconds:
                        fpath.unlink(missing_ok=True)
                        removed_count += 1
                except OSError:
                    pass
            # Clean up empty directories
            try:
                rpath = Path(root)
                if rpath != self.base_dir and not any(rpath.iterdir()):
                    rpath.rmdir()
            except OSError:
                pass

        return removed_count
