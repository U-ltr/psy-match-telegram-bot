from sqlalchemy import select

from app.database import async_session
from app.models.psychologist import Psychologist


async def get_all_psychologists() -> list[Psychologist]:
    async with async_session() as session:
        result = await session.execute(
            select(Psychologist).order_by(Psychologist.id)
        )
        return list(result.scalars().all())


async def get_psychologist_by_telegram_id(telegram_id: int) -> Psychologist | None:
    async with async_session() as session:
        result = await session.execute(
            select(Psychologist).where(Psychologist.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def create_psychologist_access(telegram_id: int) -> Psychologist:
    async with async_session() as session:
        existing_result = await session.execute(
            select(Psychologist).where(Psychologist.telegram_id == telegram_id)
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            return existing

        psychologist = Psychologist(
            telegram_id=telegram_id,
            name=f"Психолог {telegram_id}",
            gender=None,
            description="Анкета пока не заполнена.",
            education="Не указано",
            experience_years=0,
            specializations=[],
            styles=[],
            durations=[],
            therapy_experience_fit=[],
            is_active=True,
        )

        session.add(psychologist)
        await session.commit()
        await session.refresh(psychologist)

        return psychologist


async def set_psychologist_active(psychologist_id: int, is_active: bool) -> bool:
    async with async_session() as session:
        psychologist = await session.get(Psychologist, psychologist_id)

        if not psychologist:
            return False

        psychologist.is_active = is_active
        await session.commit()

        return True
