"""Telegram delivery, hardened per the "one Bot, real timeouts, real retries,
never lie about delivery" requirements.

Previously this created a brand-new aiogram Bot (new TCP connection, new
aiohttp session) for every single message and swallowed every exception,
returning nothing - so callers had no way to know whether a send actually
succeeded, and reminder flags were being set to True even when delivery
failed. Both are fixed here:

* one shared Bot/aiohttp session for the whole process, with short,
  explicit timeouts, so a slow/unreachable Telegram API cannot block the
  scheduler loops for minutes;
* a bounded number of retries with backoff for transient errors
  (timeouts, network errors, Telegram's own 429/5xx via TelegramRetryAfter
  and TelegramServerError);
* every send returns True/False - callers MUST use this to decide whether
  something (a reminder-sent flag, a "delivered" state) may be marked done.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)

from app.config import settings

logger = logging.getLogger(__name__)

# Short-ish timeouts so one bad request cannot stall a background loop for
# minutes - individual retries still add up to a bounded worst case below.
_REQUEST_TIMEOUT_SECONDS = 15

_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.5

_bot: Bot | None = None
_bot_lock = asyncio.Lock()


async def get_shared_bot() -> Bot:
    """One Bot/aiohttp session, reused for the life of the process."""
    global _bot
    if _bot is not None:
        return _bot

    async with _bot_lock:
        if _bot is None:
            session = AiohttpSession(timeout=_REQUEST_TIMEOUT_SECONDS)
            _bot = Bot(token=settings.bot_token, session=session)

        return _bot


async def close_shared_bot() -> None:
    global _bot
    if _bot is not None:
        await _bot.session.close()
        _bot = None


async def send_message_safely(chat_id: int, text: str, **kwargs) -> bool:
    """Send a Telegram message with retry/backoff. Returns True only if the
    message was actually accepted by Telegram - callers must not mark
    anything as "delivered" or "reminder sent" unless this returns True."""

    bot = await get_shared_bot()

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            return True

        except TelegramForbiddenError:
            # user blocked the bot / chat not found - retrying will never help
            logger.warning("Cannot deliver to %s: bot is blocked or chat is gone", chat_id)
            return False

        except TelegramRetryAfter as error:
            wait_seconds = min(error.retry_after, 30)
            logger.warning("Rate limited sending to %s, waiting %.1fs", chat_id, wait_seconds)
            await asyncio.sleep(wait_seconds)

        except (TelegramNetworkError, TelegramAPIError) as error:
            logger.warning(
                "Send to %s failed (attempt %s/%s): %s", chat_id, attempt, _MAX_ATTEMPTS, error
            )
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BACKOFF_BASE_SECONDS * attempt)

        except Exception as error:  # noqa: BLE001 - last-resort safety net, never crash a caller
            logger.exception("Unexpected error sending to %s: %s", chat_id, error)
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BACKOFF_BASE_SECONDS * attempt)

    logger.error("Giving up sending to %s after %s attempts", chat_id, _MAX_ATTEMPTS)
    return False
