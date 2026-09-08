import asyncio
import logging

from aiohttp import web

from app.config import settings
from app.services.yookassa_payments import sync_yookassa_payment_status


logger = logging.getLogger(__name__)


async def yookassa_webhook_handler(request: web.Request) -> web.Response:
    """Handle a YooKassa webhook.

    SECURITY: the POSTed body is untrusted - anyone who finds this URL can
    send an arbitrary "payment.succeeded" payload. We never apply the
    webhook body's status/amount directly. Instead we take only the
    payment id out of it and re-fetch the authoritative status straight
    from YooKassa's API with our own shop credentials
    (sync_yookassa_payment_status), and apply THAT. A forged webhook for a
    payment that doesn't exist or isn't actually paid simply has no effect.
    """
    try:
        data = await request.json()
    except Exception:
        logger.warning("YooKassa webhook invalid json")
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    payment_object = data.get("object") or {}
    payment_id = payment_object.get("id")

    if not payment_id:
        logger.warning("YooKassa webhook missing payment id")
        return web.json_response({"ok": False, "error": "missing payment id"}, status=400)

    logger.info("YooKassa webhook received for payment %s, re-verifying via API", payment_id)

    success = await sync_yookassa_payment_status(payment_id)

    if not success:
        # not necessarily an error - "not finished yet" also returns False
        return web.json_response({"ok": True, "note": "not applied"}, status=200)

    return web.json_response({"ok": True})


async def healthcheck_handler(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "payment_webhook"})


async def start_payment_webhook_server() -> None:
    app = web.Application()

    app.router.add_get("/", healthcheck_handler)
    app.router.add_post("/", yookassa_webhook_handler)
    app.router.add_post("/yookassa/webhook", yookassa_webhook_handler)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(
        runner,
        host=settings.payment_server_host,
        port=settings.payment_server_port,
    )

    await site.start()

    logger.info(
        "Payment webhook server started on %s:%s",
        settings.payment_server_host,
        settings.payment_server_port,
    )

    while True:
        await asyncio.sleep(3600)
