"""Dev/staging seed data: a handful of realistic psychologist profiles.

Run with: python -m app.scripts.seed_psychologists

Each psychologist gets several WorkingInterval rows spread across roughly
the next month (not just the first few days) so manual testing has a
realistically large pool of psychologists/slots to pick from, both close-in
and further out, instead of everything clustering in the next 2-4 days.
"""
import asyncio
from datetime import date, timedelta

from sqlalchemy import delete, select

from app.database import async_session, check_db_connection
from app.models.psychologist import Psychologist
from app.models.working_interval import WorkingInterval
from app.models.busy_interval import BusyInterval


PSYCHOLOGISTS = [
    {
        "name": "Анна Смирнова",
        "gender": "female",
        "description": "Работает с тревогой, стрессом, самооценкой и навязчивыми мыслями. Подходит для первого опыта терапии.",
        "education": "МГУ, факультет психологии. Дополнительная подготовка по КПТ.",
        "experience_years": 6,
        "durations": [
            {"minutes": 50, "price": 3000},
            {"minutes": 60, "price": 3500},
        ],
        "specializations": ["cbt_therapist"],
        "help_topics": ["anxiety_stress", "selfesteem", "depressive_state"],
        "styles": ["supportive", "cbt", "practical"],
        "therapy_experience_fit": ["none", "negative", "positive"],
        "work_intervals": [
            {"days_from_now": 1, "start_time": "10:00", "end_time": "15:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 2, "start_time": "11:00", "end_time": "14:00", "duration": 60, "break_minutes": 0},
            {"days_from_now": 7, "start_time": "10:00", "end_time": "15:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 10, "start_time": "11:00", "end_time": "14:00", "duration": 60, "break_minutes": 0},
            {"days_from_now": 14, "start_time": "10:00", "end_time": "15:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 18, "start_time": "11:00", "end_time": "14:00", "duration": 60, "break_minutes": 0},
            {"days_from_now": 22, "start_time": "10:00", "end_time": "15:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 26, "start_time": "11:00", "end_time": "14:00", "duration": 60, "break_minutes": 0},
            {"days_from_now": 29, "start_time": "10:00", "end_time": "15:00", "duration": 50, "break_minutes": 10},
        ],
    },
    {
        "name": "Мария Орлова",
        "gender": "female",
        "description": "Помогает в вопросах отношений, семейных конфликтов, расставаний и переживания утраты.",
        "education": "НИУ ВШЭ, психологическое консультирование. Семейная терапия.",
        "experience_years": 9,
        "durations": [
            {"minutes": 60, "price": 4500},
            {"minutes": 90, "price": 6000},
        ],
        "specializations": ["family_therapist"],
        "help_topics": ["relationships", "family", "loss"],
        "styles": ["supportive", "deep", "universal"],
        "therapy_experience_fit": ["negative", "positive"],
        "work_intervals": [
            {"days_from_now": 1, "start_time": "14:00", "end_time": "19:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 3, "start_time": "12:00", "end_time": "16:00", "duration": 90, "break_minutes": 0},
            {"days_from_now": 7, "start_time": "14:00", "end_time": "19:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 10, "start_time": "12:00", "end_time": "16:00", "duration": 90, "break_minutes": 0},
            {"days_from_now": 14, "start_time": "14:00", "end_time": "19:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 18, "start_time": "12:00", "end_time": "16:00", "duration": 90, "break_minutes": 0},
            {"days_from_now": 22, "start_time": "14:00", "end_time": "19:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 26, "start_time": "12:00", "end_time": "16:00", "duration": 90, "break_minutes": 0},
            {"days_from_now": 29, "start_time": "14:00", "end_time": "19:00", "duration": 60, "break_minutes": 10},
        ],
    },
    {
        "name": "Илья Ковалёв",
        "gender": "male",
        "description": "Работает с выгоранием, карьерными трудностями, прокрастинацией и поиском опоры.",
        "education": "СПбГУ, психология. Коучинговый и КПТ-подход.",
        "experience_years": 5,
        "durations": [
            {"minutes": 50, "price": 3500},
            {"minutes": 60, "price": 4000},
        ],
        "specializations": ["cbt_therapist"],
        "help_topics": ["burnout_work", "self_understanding", "selfesteem"],
        "styles": ["practical", "cbt", "behavior"],
        "therapy_experience_fit": ["none", "positive"],
        "work_intervals": [
            {"days_from_now": 2, "start_time": "18:00", "end_time": "21:00", "duration": 60, "break_minutes": 0},
            {"days_from_now": 4, "start_time": "10:00", "end_time": "13:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 7, "start_time": "18:00", "end_time": "21:00", "duration": 60, "break_minutes": 0},
            {"days_from_now": 10, "start_time": "10:00", "end_time": "13:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 14, "start_time": "18:00", "end_time": "21:00", "duration": 60, "break_minutes": 0},
            {"days_from_now": 18, "start_time": "10:00", "end_time": "13:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 22, "start_time": "18:00", "end_time": "21:00", "duration": 60, "break_minutes": 0},
            {"days_from_now": 26, "start_time": "10:00", "end_time": "13:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 29, "start_time": "18:00", "end_time": "21:00", "duration": 60, "break_minutes": 0},
        ],
    },
    {
        "name": "Екатерина Волкова",
        "gender": "female",
        "description": "Подходит для бережной работы с подавленным состоянием, апатией, потерей смысла и переживанием сложных периодов.",
        "education": "МГППУ, клиническая психология. Работа с кризисными состояниями.",
        "experience_years": 11,
        "durations": [
            {"minutes": 60, "price": 5000},
            {"minutes": 90, "price": 7000},
        ],
        "specializations": ["clinical"],
        "help_topics": ["depressive_state", "loss", "crisis"],
        "styles": ["deep", "supportive", "universal"],
        "therapy_experience_fit": ["negative", "positive"],
        "work_intervals": [
            {"days_from_now": 3, "start_time": "13:00", "end_time": "17:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 7, "start_time": "13:00", "end_time": "17:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 10, "start_time": "13:00", "end_time": "17:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 14, "start_time": "13:00", "end_time": "17:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 18, "start_time": "13:00", "end_time": "17:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 22, "start_time": "13:00", "end_time": "17:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 26, "start_time": "13:00", "end_time": "17:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 29, "start_time": "13:00", "end_time": "17:00", "duration": 60, "break_minutes": 10},
        ],
    },
    {
        "name": "Дмитрий Соколов",
        "gender": "male",
        "description": "Работает с паническими атаками, социальной тревожностью и трудностями в общении. Практикует короткие структурированные сессии.",
        "education": "РГГУ, клиническая психология. Подготовка по КПТ и работе с тревожными расстройствами.",
        "experience_years": 4,
        "durations": [
            {"minutes": 30, "price": 2000},
            {"minutes": 50, "price": 3000},
        ],
        "specializations": ["cbt_therapist"],
        "help_topics": ["anxiety_stress", "self_understanding"],
        "styles": ["cbt", "practical", "behavior"],
        "therapy_experience_fit": ["none", "positive"],
        "work_intervals": [
            {"days_from_now": 1, "start_time": "09:00", "end_time": "12:00", "duration": 30, "break_minutes": 5},
            {"days_from_now": 2, "start_time": "16:00", "end_time": "20:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 7, "start_time": "09:00", "end_time": "12:00", "duration": 30, "break_minutes": 5},
            {"days_from_now": 10, "start_time": "16:00", "end_time": "20:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 14, "start_time": "09:00", "end_time": "12:00", "duration": 30, "break_minutes": 5},
            {"days_from_now": 18, "start_time": "16:00", "end_time": "20:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 22, "start_time": "09:00", "end_time": "12:00", "duration": 30, "break_minutes": 5},
            {"days_from_now": 26, "start_time": "16:00", "end_time": "20:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 29, "start_time": "09:00", "end_time": "12:00", "duration": 30, "break_minutes": 5},
        ],
    },
    {
        "name": "Ольга Сергеева",
        "gender": "female",
        "description": "Работает с зависимостями, созависимостью, семейными трудностями и повторяющимися сценариями.",
        "education": "Институт практической психологии. Работа с зависимостями и семейными системами.",
        "experience_years": 8,
        "durations": [
            {"minutes": 50, "price": 4000},
            {"minutes": 60, "price": 4500},
            {"minutes": 90, "price": 6500},
        ],
        "specializations": ["family_therapist"],
        "help_topics": ["addictions", "family", "relationships"],
        "styles": ["practical", "behavior", "supportive"],
        "therapy_experience_fit": ["none", "negative", "positive"],
        "work_intervals": [
            {"days_from_now": 1, "start_time": "09:00", "end_time": "13:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 4, "start_time": "15:00", "end_time": "19:00", "duration": 90, "break_minutes": 0},
            {"days_from_now": 7, "start_time": "09:00", "end_time": "13:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 10, "start_time": "15:00", "end_time": "19:00", "duration": 90, "break_minutes": 0},
            {"days_from_now": 14, "start_time": "09:00", "end_time": "13:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 18, "start_time": "15:00", "end_time": "19:00", "duration": 90, "break_minutes": 0},
            {"days_from_now": 22, "start_time": "09:00", "end_time": "13:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 26, "start_time": "15:00", "end_time": "19:00", "duration": 90, "break_minutes": 0},
            {"days_from_now": 29, "start_time": "09:00", "end_time": "13:00", "duration": 50, "break_minutes": 10},
        ],
    },
    {
        "name": "Виктория Морозова",
        "gender": "female",
        "description": "Работает с одиночеством, поиском себя и чувством вины через глубинный гештальт-подход.",
        "education": "Московский институт гештальта и психодрамы.",
        "experience_years": 10,
        "durations": [
            {"minutes": 60, "price": 4500},
            {"minutes": 90, "price": 6500},
        ],
        "specializations": ["gestalt_therapist"],
        "help_topics": ["loneliness", "self_understanding", "guilt"],
        "styles": ["deep", "universal"],
        "therapy_experience_fit": ["none", "positive"],
        "work_intervals": [
            {"days_from_now": 1, "start_time": "12:00", "end_time": "16:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 4, "start_time": "12:00", "end_time": "16:00", "duration": 90, "break_minutes": 0},
            {"days_from_now": 8, "start_time": "12:00", "end_time": "16:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 12, "start_time": "12:00", "end_time": "16:00", "duration": 90, "break_minutes": 0},
            {"days_from_now": 16, "start_time": "12:00", "end_time": "16:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 20, "start_time": "12:00", "end_time": "16:00", "duration": 90, "break_minutes": 0},
            {"days_from_now": 24, "start_time": "12:00", "end_time": "16:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 28, "start_time": "12:00", "end_time": "16:00", "duration": 90, "break_minutes": 0},
        ],
    },
    {
        "name": "Артём Никитин",
        "gender": "male",
        "description": "Психоаналитический подход к глубинным переживаниям, чувству вины и депрессивным состояниям.",
        "education": "Восточно-Европейский институт психоанализа.",
        "experience_years": 13,
        "durations": [
            {"minutes": 50, "price": 5000},
            {"minutes": 60, "price": 5500},
        ],
        "specializations": ["psychoanalyst"],
        "help_topics": ["self_understanding", "depressive_state", "guilt"],
        "styles": ["deep", "universal"],
        "therapy_experience_fit": ["negative", "positive"],
        "work_intervals": [
            {"days_from_now": 2, "start_time": "09:00", "end_time": "13:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 6, "start_time": "09:00", "end_time": "13:00", "duration": 60, "break_minutes": 0},
            {"days_from_now": 9, "start_time": "09:00", "end_time": "13:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 13, "start_time": "09:00", "end_time": "13:00", "duration": 60, "break_minutes": 0},
            {"days_from_now": 17, "start_time": "09:00", "end_time": "13:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 21, "start_time": "09:00", "end_time": "13:00", "duration": 60, "break_minutes": 0},
            {"days_from_now": 25, "start_time": "09:00", "end_time": "13:00", "duration": 50, "break_minutes": 10},
            {"days_from_now": 30, "start_time": "09:00", "end_time": "13:00", "duration": 60, "break_minutes": 0},
        ],
    },
    {
        "name": "Наталья Ковальчук",
        "gender": "female",
        "description": "Детский и подростковый психолог, помогает разобраться с семейными и возрастными трудностями.",
        "education": "МГППУ, детская и семейная психология.",
        "experience_years": 7,
        "durations": [
            {"minutes": 45, "price": 3500},
            {"minutes": 60, "price": 4000},
        ],
        "specializations": ["child_teen"],
        "help_topics": ["family", "relationships", "selfesteem"],
        "styles": ["supportive", "practical"],
        "therapy_experience_fit": ["none", "positive"],
        "work_intervals": [
            {"days_from_now": 1, "start_time": "15:00", "end_time": "19:00", "duration": 45, "break_minutes": 5},
            {"days_from_now": 5, "start_time": "15:00", "end_time": "19:00", "duration": 60, "break_minutes": 0},
            {"days_from_now": 9, "start_time": "15:00", "end_time": "19:00", "duration": 45, "break_minutes": 5},
            {"days_from_now": 13, "start_time": "15:00", "end_time": "19:00", "duration": 60, "break_minutes": 0},
            {"days_from_now": 17, "start_time": "15:00", "end_time": "19:00", "duration": 45, "break_minutes": 5},
            {"days_from_now": 21, "start_time": "15:00", "end_time": "19:00", "duration": 60, "break_minutes": 0},
            {"days_from_now": 25, "start_time": "15:00", "end_time": "19:00", "duration": 45, "break_minutes": 5},
            {"days_from_now": 29, "start_time": "15:00", "end_time": "19:00", "duration": 60, "break_minutes": 0},
        ],
    },
    {
        "name": "Павел Григорьев",
        "gender": "male",
        "description": "Клинический психолог, работает с кризисными состояниями, тревогой и депрессией.",
        "education": "СПбГУ, клиническая психология. Опыт кризисного консультирования.",
        "experience_years": 15,
        "durations": [
            {"minutes": 60, "price": 5500},
            {"minutes": 90, "price": 7500},
        ],
        "specializations": ["clinical"],
        "help_topics": ["crisis", "depressive_state", "anxiety_stress"],
        "styles": ["universal", "deep"],
        "therapy_experience_fit": ["none", "negative", "positive"],
        "work_intervals": [
            {"days_from_now": 3, "start_time": "10:00", "end_time": "14:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 7, "start_time": "10:00", "end_time": "14:00", "duration": 90, "break_minutes": 0},
            {"days_from_now": 11, "start_time": "10:00", "end_time": "14:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 15, "start_time": "10:00", "end_time": "14:00", "duration": 90, "break_minutes": 0},
            {"days_from_now": 19, "start_time": "10:00", "end_time": "14:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 23, "start_time": "10:00", "end_time": "14:00", "duration": 90, "break_minutes": 0},
            {"days_from_now": 27, "start_time": "10:00", "end_time": "14:00", "duration": 60, "break_minutes": 10},
            {"days_from_now": 30, "start_time": "10:00", "end_time": "14:00", "duration": 90, "break_minutes": 0},
        ],
    },
]


async def seed() -> None:
    # Schema must already exist - run `alembic upgrade head` first.
    await check_db_connection()

    async with async_session() as session:
        existing = (await session.execute(select(Psychologist))).scalars().all()
        existing_ids = [p.id for p in existing]

        if existing_ids:
            await session.execute(delete(WorkingInterval).where(WorkingInterval.psychologist_id.in_(existing_ids)))
            await session.execute(delete(BusyInterval).where(BusyInterval.psychologist_id.in_(existing_ids)))
            await session.execute(delete(Psychologist))
            await session.commit()

        today = date.today()

        for item in PSYCHOLOGISTS:
            work_intervals = item.pop("work_intervals")

            psychologist = Psychologist(is_active=True, **item)
            session.add(psychologist)
            await session.flush()

            for interval in work_intervals:
                session.add(
                    WorkingInterval(
                        psychologist_id=psychologist.id,
                        date=(today + timedelta(days=interval["days_from_now"])).strftime("%Y-%m-%d"),
                        start_time=interval["start_time"],
                        end_time=interval["end_time"],
                        consultation_duration=interval["duration"],
                        break_minutes=interval["break_minutes"],
                    )
                )

        await session.commit()

        count = len((await session.execute(select(Psychologist))).scalars().all())
        print(f"Seed completed. Psychologists created: {count}")


if __name__ == "__main__":
    asyncio.run(seed())
