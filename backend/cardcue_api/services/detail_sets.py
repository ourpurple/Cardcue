"""Read the effective reviewed-detail snapshot without changing the bill version."""
from sqlalchemy import select

from cardcue_api.persistence import ConfirmedTransaction, DetailSet, DetailSetTransaction


async def effective_details(session, version_id):
    """Return (snapshot metadata or None, rows); old confirmed rows remain readable."""
    latest = (await session.execute(
        select(DetailSet).where(DetailSet.statement_version_id == version_id)
        .order_by(DetailSet.revision.desc()).limit(1)
    )).scalar_one_or_none()
    if latest is not None:
        rows = list((await session.execute(
            select(DetailSetTransaction).where(DetailSetTransaction.detail_set_id == latest.id)
            .order_by(DetailSetTransaction.sequence)
        )).scalars().all())
    else:
        rows = list((await session.execute(
            select(ConfirmedTransaction).where(ConfirmedTransaction.statement_version_id == version_id)
            .order_by(ConfirmedTransaction.sequence)
        )).scalars().all())
    return latest, rows
