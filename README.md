# psy-match-telegram-bot

Telegram-бот для подбора психолога: клиент отвечает на анкету и получает
подобранных специалистов, психологи ведут анкету/расписание/записи в
своём кабинете, оплата — через ЮKassa, есть бесплатная 15-минутная
консультация «помогите выбрать».

## Архитектура кратко

- **aiogram 3** — обработчики в `app/handlers/*` (клиент, психолог,
  админ), состояния FSM в `app/states/*`.
- **PostgreSQL + SQLAlchemy 2.0 (async, asyncpg)** — модели в
  `app/models/*`. Схема версионируется через **Alembic**
  (`migrations/`) — `Base.metadata.create_all()` больше не используется в
  рантайме.
- **Бизнес-логика** — в `app/services/*`, каждый файл отвечает за одну
  область (цены — `pricing.py`, записи и защита от овербукинга —
  `bookings.py`, финансы/выплаты — `payouts.py`, и т.д.). Хендлеры не
  должны напрямую работать с БД в обход этих сервисов.
- **ЮKassa** — `app/services/yookassa_payments.py` создаёт платёж и
  синхронизирует статус; вебхук (`app/payment_webhook.py`) никогда не
  применяет тело запроса напрямую — он берёт из него только `payment_id`
  и перепроверяет реальный статус через API ЮKassa своими же ключами.
- **Фоновые циклы** (`app/bot.py`, запускаются вместе с ботом):
  напоминания (1 час / 10 минут до консультации), синхронизация зависших
  платежей ЮKassa, снятие истёкших неоплаченных резервов.

## Локальный запуск

```bash
# 1. Поднять Postgres (слушает только 127.0.0.1:5433)
docker compose up -d postgres

# 2. Виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # requirements.txt + pytest/aiosqlite

# 3. Настроить .env
cp .env.example .env
# заполнить BOT_TOKEN как минимум; DATABASE_URL по умолчанию уже
# соответствует docker-compose.yml

# 4. Применить миграции (создаёт всю схему БД)
alembic upgrade head

# 5. (опционально) тестовые данные — несколько психологов с расписанием
python -m app.scripts.seed_psychologists

# 6. Тесты
pytest

# 7. Запуск бота
python -m app.bot
```

Проверка после запуска:

```bash
curl -s http://localhost:8080/ | python3 -m json.tool   # {"ok": true, "service": "payment_webhook"}
```
и в Telegram: `/start` клиенту, `/start` психологу (после того как админ
выдал доступ через `/admin` → «Добавить психолога»), `/admin` — если
`ADMIN_IDS` включает ваш Telegram ID.

## Деплой (Ubuntu + systemd, Postgres в Docker)

```bash
sudo useradd --system --home /opt/psy-match-telegram-bot --shell /usr/sbin/nologin psybot
sudo mkdir -p /opt/psy-match-telegram-bot
sudo chown psybot:psybot /opt/psy-match-telegram-bot

# скопировать код в /opt/psy-match-telegram-bot (git clone/rsync), затем:
cd /opt/psy-match-telegram-bot
sudo -u psybot python3 -m venv .venv
sudo -u psybot .venv/bin/pip install -r requirements.txt
sudo -u psybot cp .env.example .env
sudo -u psybot vim .env   # заполнить реальные значения

# Postgres, слушает только 127.0.0.1 (см. docker-compose.yml)
docker compose up -d postgres

# Схема БД
sudo -u psybot .venv/bin/alembic upgrade head

# systemd
sudo cp deploy/psybot.service /etc/systemd/system/psybot.service
sudo systemctl daemon-reload
sudo systemctl enable --now psybot

# Проверка
sudo systemctl status psybot
curl -s http://127.0.0.1:8080/
sudo journalctl -u psybot -f
```

Обновление версии (redeploy):

```bash
cd /opt/psy-match-telegram-bot
git pull
sudo -u psybot .venv/bin/pip install -r requirements.txt
sudo -u psybot .venv/bin/alembic upgrade head
sudo systemctl restart psybot
sudo systemctl status psybot
```

Если нужен вебхук ЮKassa снаружи (обычно да) — поставьте перед ботом
reverse-proxy с TLS (nginx/caddy), который проксирует
`https://ваш-домен/yookassa/webhook` на `127.0.0.1:8080/yookassa/webhook`,
и укажите этот публичный URL в настройках ЮKassa.

## Ссылки на видеовстречу

По умолчанию психолог **добавляет ссылку сам** в своём кабинете
(«Добавить/изменить ссылку встречи», принимает `https://`, `http://` или
`t.me/`-ссылку) — эта ручная ссылка всегда в приоритете и никогда не
перезаписывается автоматически.

Если психолог ничего не добавил, бот сам генерирует бесплатную ссылку на
`meet.jit.si` (`app/services/jitsi.py`) в момент подтверждения записи
(успешная оплата через ЮKassa или выдача бесплатной 15-минутной
консультации). Jitsi Meet не требует ни API-ключа, ни регистрации, ни
настройки — ссылка вида `https://meet.jit.si/<комната>` сама и есть
встреча: комната создаётся в момент первого перехода по ссылке. Имя
комнаты включает id записи и случайный суффикс, поэтому её нельзя
подобрать или перепутать с чужой встречей. В отличие от прежней
интеграции с Яндекс.Телемостом (требовавшей OAuth-токен для Яндекс 360
для бизнеса, который так и не был получен), это не зависит от внешнего
API и не может «не сработать» из-за настроек или сети.

За 10 минут до консультации:

- если ссылка есть (ручная или сгенерированная Jitsi) — уходит клиенту;
- в редком случае, если по какой-то причине ссылки всё ещё нет —
  клиент получает честное сообщение «пришлём отдельным сообщением», а
  психологу и всем админам уходит срочное уведомление «добавьте ссылку
  прямо сейчас».

## Финансы и выплаты

Каждая **успешно оплаченная** запись (реальный платёж через ЮKassa)
получает одну запись `Payout` (`app/models/payout.py`): сумма платежа,
комиссия платформы (`PLATFORM_COMMISSION_PERCENT`, по умолчанию 30%) и
сумма к выплате психологу. Бесплатная 15-минутная консультация выплату
никогда не создаёт. Статусы: `pending` → `ready` → `paid` (или
`cancelled`), меняются вручную админом в разделе «Финансы» админ-панели —
сама выплата на карту/счёт психолога происходит вне бота, бот только
считает и отслеживает.

## Тесты

```bash
pytest            # весь набор
pytest -v tests/test_bookings.py   # один файл
```

Юнит-тесты используют in-memory SQLite вместо реального Postgres (см.
`tests/conftest.py`) — это проверяет бизнес-логику, но не полную
гарантию блокировки строк на уровне БД (`SELECT ... FOR UPDATE`), которая
специфична для Postgres. Как минимум один раз перед боевым деплоем стоит
также вручную прогнать сценарий «два клиента одновременно жмут на один и
тот же слот» против реального Postgres.

## Известные ограничения

- Автоматическое тестирование в среде, где готовился этот код, не
  запускалось «вживую» (нет доступа к PyPI) — набор тестов написан и
  проверен вручную, но первый реальный прогон `pytest` стоит сделать
  сразу после клонирования репозитория.
- Выплаты психологам считаются ботом, но не отправляются автоматически —
  это сознательное решение (не подключён ни один платёжный API для
  массовых выплат), см. раздел «Финансы и выплаты».
- Процент комиссии платформы (`PLATFORM_COMMISSION_PERCENT`) — заглушка
  30%, значение не согласовано с владельцем. См. `docs/final_report_2026-09-round2.md`.

## Переменные окружения

См. `.env.example` — там же комментарии к каждой переменной.
