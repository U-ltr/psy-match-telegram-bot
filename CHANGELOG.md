# Changelog

## 6.3.0 — multi-duration preview, "Подбор" flow state bug, dead "Назад" (2026-09)

Round 6: follow-up reports on the same psychologist from round 5, after
his profile was fully priced. No schema changes.

### Fixed
- A psychologist who priced several durations (e.g. 30/50/60/90 minutes)
  only ever showed slots for ONE of them (whichever value happened to be
  stored on their WorkingInterval row) in "Ближайшие слоты" and in every
  client-facing listing. `get_active_psychologists_with_slots()` now
  generates preview slots per priced duration via
  `compute_available_start_times` (the same real engine used once a
  client has picked a duration), so every priced duration can appear.
- The "Подобрать психолога" (questionnaire get-matched) flow kept its own
  separate state (`ranked_psychologist_ids`) and a second, incomplete card
  renderer without a photo or help_topics/styles. Worse: its card's
  "Выбрать время"/"Следующий"/"Предыдущий" buttons only understood the
  *other* flows' state shape, so tapping them silently fell back to the
  first active psychologist in the whole database - a different
  psychologist than the one on screen. Unified onto the same
  `matched_psychologists` state and `show_psychologist_card` renderer
  every other matching flow already used; removed the now-unreachable
  duplicate flow.
- "Назад" on the duration-choice screen called back into the function
  that renders that very screen, so it looked like nothing happened -
  the only way out was "Начать заново". It now returns to the
  psychologist's card.

## 6.2.0 — invisible-psychologist bug, free-text options, Jitsi meeting links (2026-09)

Round 5: two more reports from real usage, plus a feature request. No
schema changes.

### Fixed
- A psychologist with a fully completed, correctly priced profile could
  still be completely invisible to clients ("Ближайший психолог" never
  showed them). Root cause: every new free interval was saved with a
  hardcoded `consultation_duration=50`, which silently dropped every
  preview slot for a psychologist who never priced exactly 50 minutes -
  the existence check in `get_active_psychologists_with_slots()` is
  gated on that same list being non-empty. New intervals now use the
  psychologist's own shortest priced duration; adding an interval is
  blocked with a clear message until at least one duration is priced.
  A one-off script (`app/scripts/fix_working_interval_durations.py`)
  repairs intervals that were already saved with the old hardcoded
  value.

### Added
- A psychologist can add their own free-text specialization / help topic
  / style instead of being limited to the fixed catalog ("➕ Свой
  вариант" on each multi-select screen). Stored inline via a `custom:`
  marker so every existing display path (own profile, client card,
  admin card) shows it correctly with no extra wiring.
- Free, no-signup video meeting links via Jitsi Meet
  (`app/services/jitsi.py`), replacing the earlier Yandex Telemost
  integration (removed - its OAuth token never materialized, so it was
  always a no-op in practice). If the psychologist hasn't added a link
  manually, the bot generates one automatically on booking confirmation;
  a manual link is never overwritten.

### Removed
- `app/services/telemost.py` and its `YANDEX_CLIENT_ID` /
  `YANDEX_CLIENT_SECRET` / `YANDEX_OAUTH_TOKEN` settings/env vars -
  nothing reads them anymore.

## 6.1.1 — manual E2E bug-fix pass (2026-09)

Third audit-driven pass, this time from real manual Telegram testing
rather than a code review. No schema changes.

### Fixed
- A raw internal code (e.g. "family_therapist") could leak into a
  psychologist's card, search results, or the admin view instead of its
  Russian label. Root cause: the code-to-label mapping for
  specializations/help_topics/styles was duplicated across three places
  that had drifted apart, one of them (`app/handlers/client.py`'s
  `show_current_psychologist`) using an entirely wrong dict. Centralized
  into `app.services.answer_formatting.format_code_list`, used
  everywhere against the existing `app.keyboards.psychologist` option
  dicts.
- Opening "Анкета" (the psychologist cabinet's profile screen) crashed
  with `NameError: name 'format_list' is not defined` every time -
  `format_list` was never defined or imported anywhere. This is also why
  the profile edit flow (already fully implemented - name, photo,
  description, education, experience, gender, specializations,
  help_topics, styles, durations/prices) looked broken from the outside:
  it crashed before ever reaching the edit menu.
- The "not found" message after a name search read as dry/technical
  ("Не удалось найти активного психолога..."); replaced with a warmer,
  respectful message, keeping the same retry/get-matched/menu keyboard.
- One underlying error could produce more than one identical admin
  notification and client fallback message. Added an update_id-keyed
  dedup guard in the global error handler so one Telegram update is
  reported at most once, while two genuinely distinct updates still each
  notify separately.

### Changed
- Dev/staging seed data: extended every psychologist's availability out
  to roughly a month ahead (previously only 1-4 days) and added 4 more
  psychologist profiles (10 total) for a wider manual-testing pool.

### Verified unchanged (regression audit)
- Psychologist matching, card switching, duration selection, price
  display, Moscow time handling, nearest-slot search, the client menu,
  the single "Начать заново" button, and psychologist schedule editing -
  none of these needed or received changes this pass.

## 6.1.0 — scheduling rework, real Telemost, financial audit (2026-09)

Second audit-driven pass, on top of 6.0.0. Assumed dev/seed data only, no
real production data to preserve — schema was free to change (in the
event, no schema changes were needed this round).

### Added
- Real per-duration availability: the psychologist now sets free working
  intervals (not fixed slots), and the client picks
  psychologist → duration → an actual computed start time
  (`app/services/schedule.py: compute_available_start_times`) that
  accounts for every other active booking against that interval. Every
  duration the psychologist prices is now selectable, not just one fixed
  one (`app/keyboards/client.py: durations_keyboard`).
- A full overlap-matrix test suite for booking creation (exact-duplicate,
  contained, containing, cancelled/expired reservations ignored,
  concurrent double-booking via `asyncio.gather`).
- Real Yandex Telemost integration (`app/services/telemost.py`):
  `POST /v1/telemost-api/conferences` with `waiting_room_level=PUBLIC`,
  gated behind `YANDEX_OAUTH_TOKEN`; never fabricates a link, and falls
  back to manual entry the moment the token is unset. Auto-attempted on
  successful payment and on the free 15-minute booking.
- Optional phone/email in the client flow, including the free
  15-minute path, with a working "Пропустить" (Skip) option on both.
- A global aiogram error handler (`app/error_handling.py`): unhandled
  exceptions are logged, admins are notified with the exception details,
  and the client gets a short generic apology instead of silence.
- `PLATFORM_COMMISSION_PERCENT` is flagged as an unconfirmed placeholder
  in both `app/config.py` and `.env.example` — see
  `docs/final_report_2026-09-round2.md` for the decision this needs from
  the business owner.
- A 6th seed psychologist, so `seed_psychologists.py` now creates 6
  profiles with near-term (1-4 day) availability for manual testing.

### Fixed
- Russian pluralization/declension bugs across answer formatting,
  pricing, and admin/psychologist-facing text (year counts, minute
  counts, record counts).
- The client's bottom reply keyboard had three buttons; trimmed to a
  single "Начать заново", and fixed it not responding while mid-FSM
  (an earlier, filterless handler was swallowing the tap).
- Removed a real dead-code surface found while investigating the
  questionnaire flow: two orphaned questions (Q5 "when to start", Q7
  "priorities") whose UI was never reachable — the live flow skips them
  with hardcoded defaults — plus duplicate/undecorated shadow copies of
  `switch_psychologist_handler` and `client_help_handler`, and a
  duplicated `client_answers_snapshot` assignment.

### Verified unchanged (regression audit)
- Free 15-minute consultation still never creates a YooKassa payment
  (price is hardcoded to 0 in three places, gated by `price <= 0`).
- Reminder-sent flags are still only set after `send_message_safely`
  confirms delivery.
- No `create_all()`/ad-hoc `ALTER TABLE` anywhere in live code; Alembic
  remains the only schema-change mechanism, and no schema changed this
  round, so no new migration was added.
- Postgres still published only on `127.0.0.1`; `.env` still untracked;
  no secrets found in `git log -p`.

### Known limitations
- Full Yandex OAuth (authorization-code + refresh token) is not
  implemented — `YANDEX_OAUTH_TOKEN` is a static token obtained once
  manually. See README's "Известные ограничения".
- No real image asset exists for a logo/photo ahead of the start text
  requested in a voice-note addendum; not fabricated — flagged instead.
- Live `pytest`/`alembic upgrade head` execution was not possible in the
  sandbox this pass was done in (no PyPI network access) — same caveat
  as the 6.0.0 pass. Test count: 114 (up from 82), all reviewed by hand
  and via standalone logic execution where real imports were unavailable.

## 6.0.0 — production-readiness pass (2026-09)

Audit-driven overhaul of the existing bot. Assumed dev/seed data only, no
real production data to preserve — schema was free to change.

### Added
- Per-duration pricing for psychologists (`app/services/pricing.py`) —
  replaces a single flat price; each session length has its own price.
- Real overlap/double-booking protection: row lock (`SELECT ... FOR
  UPDATE`) on the psychologist plus actual `[start, end)` time-range
  overlap comparison, not exact start-time string matching.
- Finance/payout tracking (`app/models/payout.py`,
  `app/services/payouts.py`): gross/commission/psychologist-amount split
  per paid booking, admin "Финансы" panel to advance payout status. Never
  created for the free consultation.
- Real Alembic migration history (`migrations/`) replacing
  `Base.metadata.create_all()` + a hand-rolled `ALTER TABLE`.
- `pytest` suite (`tests/`) covering declension, formatting, slot
  generation, overlap detection, per-duration pricing, payment
  idempotency, free booking, reminder windows, meeting-link fallback.
- `deploy/psybot.service` (systemd unit) and a documented Ubuntu +
  systemd + Docker(Postgres-only) deployment story in `README.md`.
- `.env.example`, `CHANGELOG.md`, `VERSION`.

### Fixed
- Free 15-minute "selection" consultation is now genuinely free (a stale
  non-zero config default made it non-free despite the free-path code
  already existing).
- "Reservation expired" notification to the client essentially never
  fired in practice — two different code paths raced to expire the same
  booking with different status values; unified into one.
- Raw internal status codes (`reserved/pending`, `cancelled/expired`, ...)
  and a literal `\n` (not a real line break) were shown directly to
  psychologists/admins in several places.
- Russian numeral declension for "years of experience" (was hardcoded to
  "лет" regardless of the number: "1 лет" instead of "1 год").
- Telegram delivery: one shared `Bot`/session for the whole process
  (previously polling used a separate `Bot` from every outbound send);
  retries with backoff; a send now returns whether it actually succeeded,
  and reminder-sent flags are only set on confirmed delivery.
- YooKassa webhook no longer trusts the POSTed body directly — re-fetches
  the authoritative status from YooKassa's API before applying anything.
- `Booking.slot_id` was a dangling foreign key to a `slots` table that no
  longer existed.

### Removed
- Legacy `Slot` model and its dead read paths.
- Three duplicate generations of the psychologist-cabinet handlers,
  collapsed into one.
- Several unused/orphaned files (`services/payments.py`,
  `services/scheduler.py`, `services/telemost.py`,
  `handlers/payments.py`, `keyboards/admin.py`, `texts/errors.py`,
  `texts/legal.py`, an empty `Dockerfile`, two stray empty root files).

### Known limitations
See `README.md`'s "Известные ограничения" section — most notably: Yandex
Telemost API integration was never implemented (manual meeting-link entry
by the psychologist is the supported path), and the test suite was
written but could not be executed in the sandbox this pass was done in
(no PyPI network access) — run `pytest` as the first step after cloning.

## Earlier history

Not tracked before this pass — see `docs/feature_update_2026-07.md` for
the one prior documented change (separating `specializations` from
`help_topics`), now superseded by the Alembic migration above.
