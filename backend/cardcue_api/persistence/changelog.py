"""Change log for sync protocol (S1-07).

Every write operation appends a row in the same transaction. The sequence
number provides a total order per owner for incremental sync.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, func, Sequence
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cardcue_api.persistence.models import Base


# Global sequence for ordering changes
change_seq = Sequence("change_seq", start=1, increment=1)


class ChangeLog(Base):
    __tablename__ = "change_log"

    id: Mapped[int] = mapped_column(BigInteger, change_seq, primary_key=True, server_default=change_seq.next_value())
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="account / card / statement / version / payment")
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False, comment="create / update / delete")
    snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="Entity state after change")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
