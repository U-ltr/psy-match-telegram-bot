"""Global aiogram error handler.

Before this, an unhandled exception inside any handler was only ever
caught by aiogram itself: it gets logged to stdout/stderr and the
update is dropped - the client sees nothing (no crash, no reply) and
nobody is told a request silently failed. That matches the "don't leak
a raw stack trace to the client" half of the spec, but misses the
other half: admins should be told when something breaks so they can
act on it, and the client should see a short human message instead of
just... nothing.

This module wires a Dispatcher-level error handler that does both:
logs the full exception (as before), notifies every admin with the
exception type/message and, when available, which chat triggered it,
and - best-effort, never allowed to raise itself - tells the affected
user a generic apology rather than leaving them looking at a bot that
appears to have ignored their tap/message.
"""
import logging
from collections import deque

from aiogram.types import ErrorEvent

from app.services.admin_notifications import notify_admins
from app.services.telegram_sender import send_message_safely

logger = logging.getLogger(__name__)

CLIENT_FALLBACK_TEXT = (
    "Что-то пошло не так на нашей стороне ⚠️\n\n"
    "Мы уже знаем о проблеме. Попробуйте ещё раз через пару минут "
    "или напишите в поддержку: @egorinforest."
)

# Guard against reporting the SAME Telegram update more than once: a second
# bot process accidentally left running against the same token, aiogram
# redelivering after a hiccup, or any other path that lands this exact
# update here twice must still produce only one admin notification and one
# client fallback - not a debounce window, an exact-repeat filter. A
# genuinely different update_id is never suppressed, so two distinct errors
# always produce two distinct reports. Bounded so a long-running process
# doesn't grow this without limit; recent errors are the only ones that can
# realistically be redelivered, so a few hundred entries is ample headroom.
_RECENTLY_REPORTED_UPDATE_IDS_MAXLEN = 500
_recently_reported_update_ids: "deque[int]" = deque(maxlen=_RECENTLY_REPORTED_UPDATE_IDS_MAXLEN)


def _already_reported(update_id: int | None) -> bool:
    if update_id is None:
        # Nothing to dedupe against (e.g. some update type with no id) -
        # never suppress in this case, only exact known repeats are collapsed.
        return False

    if update_id in _recently_reported_update_ids:
        return True

    _recently_reported_update_ids.append(update_id)
    return False


async def handle_unexpected_error(event: ErrorEvent) -> bool:
    exception = event.exception
    update = event.update

    update_id = getattr(update, "update_id", None)

    logger.exception(
        "Unhandled error while processing update %s: %s",
        update_id if update_id is not None else "?",
        exception,
        exc_info=exception,
    )

    if _already_reported(update_id):
        logger.warning(
            "Update %s already reported once - suppressing duplicate admin/client notification",
            update_id,
        )
        return True

    chat_id: int | None = None
    if update.message is not None:
        chat_id = update.message.chat.id
    elif update.callback_query is not None and update.callback_query.message is not None:
        chat_id = update.callback_query.message.chat.id

    try:
        await notify_admins(
            "Админ-уведомление 🛑\n\n"
            "Необработанная ошибка в боте.\n\n"
            f"Тип: {type(exception).__name__}\n"
            f"Сообщение: {exception}\n"
            f"Update ID: {getattr(update, 'update_id', '?')}\n"
            f"Chat ID: {chat_id or 'не определён'}"
        )
    except Exception as notify_error:
        logger.exception("Failed to notify admins about unhandled error: %s", notify_error)

    if chat_id is not None:
        try:
            await send_message_safely(chat_id, CLIENT_FALLBACK_TEXT)
        except Exception as send_error:
            logger.exception("Failed to send fallback message to client: %s", send_error)

    # True tells aiogram the error was handled - it won't re-raise or
    # crash the polling loop either way, but this keeps intent explicit.
    return True
