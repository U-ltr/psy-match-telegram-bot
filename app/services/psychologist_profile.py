from sqlalchemy import select

from app.database import async_session
from app.models.psychologist import Psychologist


async def get_psychologist_by_telegram_id(telegram_id: int) -> Psychologist | None:
    async with async_session() as session:
        result = await session.execute(
            select(Psychologist).where(Psychologist.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def update_psychologist_field(
    telegram_id: int,
    field_name: str,
    value,
) -> Psychologist | None:
    async with async_session() as session:
        result = await session.execute(
            select(Psychologist).where(Psychologist.telegram_id == telegram_id)
        )
        psychologist = result.scalar_one_or_none()

        if not psychologist:
            return None

        setattr(psychologist, field_name, value)

        await session.commit()
        await session.refresh(psychologist)

        return psychologist
