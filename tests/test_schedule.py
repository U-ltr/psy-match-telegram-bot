"""Slot generation and time-range helpers: app/services/schedule.py."""
from app.services.schedule import (
    time_to_minutes,
    minutes_to_time,
    is_valid_time,
    is_valid_date,
    intervals_overlap,
    generate_available_slots_from_intervals,
    compute_available_start_times,
)
from app.models.working_interval import WorkingInterval
from app.models.busy_interval import BusyInterval


# Far enough in the future that "is this slot in the past" filtering never
# makes these tests flaky, whatever day they happen to run on.
FUTURE_DATE = "2099-01-10"


def working_interval(**kwargs):
    defaults = dict(
        id=1,
        psychologist_id=1,
        date=FUTURE_DATE,
        start_time="10:00",
        end_time="12:00",
        consultation_duration=60,
        break_minutes=10,
    )
    defaults.update(kwargs)
    return WorkingInterval(**defaults)


def busy_interval(**kwargs):
    defaults = dict(
        id=1,
        psychologist_id=1,
        date=FUTURE_DATE,
        start_time="10:00",
        end_time="11:00",
        reason="занято",
    )
    defaults.update(kwargs)
    return BusyInterval(**defaults)


def test_time_to_minutes():
    assert time_to_minutes("00:00") == 0
    assert time_to_minutes("10:30") == 630
    assert time_to_minutes("23:59") == 1439


def test_minutes_to_time():
    assert minutes_to_time(0) == "00:00"
    assert minutes_to_time(630) == "10:30"
    assert minutes_to_time(1439) == "23:59"


def test_time_minutes_roundtrip():
    for value in ["00:00", "09:05", "17:45", "23:59"]:
        assert minutes_to_time(time_to_minutes(value)) == value


def test_is_valid_time():
    assert is_valid_time("09:30") is True
    assert is_valid_time("23:59") is True
    assert is_valid_time("24:00") is False
    assert is_valid_time("9:30") is False  # must be zero-padded, len == 5
    assert is_valid_time("09-30") is False
    assert is_valid_time("") is False


def test_is_valid_date():
    assert is_valid_date("2026-09-07") is True
    assert is_valid_date("2026/09/07") is False
    assert is_valid_date("2026-09") is False


def test_intervals_overlap_true_when_ranges_cross():
    assert intervals_overlap(600, 660, 630, 690) is True  # 10:00-11:00 vs 10:30-11:30


def test_intervals_overlap_false_when_adjacent():
    # Back-to-back, not overlapping: [10:00,11:00) and [11:00,12:00)
    assert intervals_overlap(600, 660, 660, 720) is False


def test_intervals_overlap_false_when_disjoint():
    assert intervals_overlap(600, 660, 900, 960) is False


def test_generate_available_slots_basic_grid():
    intervals = [working_interval(start_time="10:00", end_time="12:00", consultation_duration=60, break_minutes=0)]
    slots = generate_available_slots_from_intervals(intervals, [])

    times = [s["time"] for s in slots]
    assert times == ["10:00", "11:00"]  # 12:00 itself doesn't fit another 60-min slot


def test_generate_available_slots_respects_break_minutes():
    intervals = [working_interval(start_time="10:00", end_time="12:00", consultation_duration=50, break_minutes=10)]
    slots = generate_available_slots_from_intervals(intervals, [])

    times = [s["time"] for s in slots]
    # 10:00-10:50, break to 11:00, 11:00-11:50, break to 12:00 (no room left)
    assert times == ["10:00", "11:00"]


def test_generate_available_slots_skips_slots_overlapping_busy_interval():
    intervals = [working_interval(start_time="10:00", end_time="13:00", consultation_duration=60, break_minutes=0)]
    busy = [busy_interval(start_time="11:00", end_time="12:00")]

    slots = generate_available_slots_from_intervals(intervals, busy)
    times = [s["time"] for s in slots]

    assert "11:00" not in times
    assert "10:00" in times


def test_generate_available_slots_filters_past_dates():
    past_intervals = [working_interval(date="2020-01-01")]
    slots = generate_available_slots_from_intervals(past_intervals, [])
    assert slots == []


def test_generate_available_slots_no_slot_when_duration_longer_than_window():
    intervals = [working_interval(start_time="10:00", end_time="10:30", consultation_duration=60)]
    slots = generate_available_slots_from_intervals(intervals, [])
    assert slots == []


class TestComputeAvailableStartTimes:
    """compute_available_start_times: the client-chosen-duration, real-overlap
    availability computation described in the scheduling requirements - a
    working interval is just an availability WINDOW, and the client's chosen
    duration (not WorkingInterval.consultation_duration) drives which start
    times are offered. See its docstring for how this differs from
    generate_available_slots_from_intervals above."""

    def test_matches_the_worked_example_from_the_spec(self):
        # "10:00-15:00 window, an existing 12:00-13:00 booking, 60-minute
        # duration -> must not offer anything overlapping 12:00-13:00, and
        # must not offer a consultation ending after 15:00."
        intervals = [working_interval(start_time="10:00", end_time="15:00")]
        busy = {FUTURE_DATE: [(720, 780)]}  # 12:00-13:00

        slots = compute_available_start_times(intervals, 60, busy)
        times = [s["time"] for s in slots]

        # Every offered start must produce [start, start+60) that avoids [12:00,13:00)
        # and stays within the window (last valid start is 14:00).
        assert "14:05" not in times  # would end at 15:05, past the window
        assert all(time_to_minutes(t) + 60 <= 900 for t in times)  # 900 = 15:00
        for t in times:
            start = time_to_minutes(t)
            end = start + 60
            assert not intervals_overlap(start, end, 720, 780), f"{t} overlaps the 12:00-13:00 booking"
        assert "10:00" in times
        assert "11:00" in times  # 11:00-12:00 ends exactly when the booking starts - fine
        assert "13:00" in times  # 13:00-14:00 starts exactly when the booking ends - fine

    def test_touching_boundaries_are_not_conflicts(self):
        # A booking ending exactly when a candidate begins (or vice versa)
        # must not be treated as an overlap.
        intervals = [working_interval(start_time="09:00", end_time="12:00")]
        busy = {FUTURE_DATE: [(600, 660)]}  # 10:00-11:00

        slots = compute_available_start_times(intervals, 60, busy)
        times = [s["time"] for s in slots]

        assert "09:00" in times  # 09:00-10:00, ends exactly when busy starts
        assert "11:00" in times  # 11:00-12:00, starts exactly when busy ends
        assert "10:00" not in times  # would be identical to the busy range

    def test_partial_overlap_from_left_and_right_both_excluded(self):
        intervals = [working_interval(start_time="09:00", end_time="12:00")]
        busy = {FUTURE_DATE: [(630, 690)]}  # 10:30-11:30

        slots = compute_available_start_times(intervals, 60, busy)
        times = [s["time"] for s in slots]

        assert "10:00" not in times  # 10:00-11:00 overlaps 10:30-11:30 from the left
        assert "11:00" not in times  # 11:00-12:00 overlaps 10:30-11:30 from the right

    def test_several_bookings_inside_one_working_interval(self):
        intervals = [working_interval(start_time="08:00", end_time="18:00")]
        busy = {FUTURE_DATE: [(540, 600), (720, 780), (900, 960)]}  # 09-10, 12-13, 15-16

        slots = compute_available_start_times(intervals, 60, busy)
        times = {s["time"] for s in slots}

        for busy_start, busy_end in [(540, 600), (720, 780), (900, 960)]:
            for t in times:
                start = time_to_minutes(t)
                assert not intervals_overlap(start, start + 60, busy_start, busy_end)
        assert "08:00" in times
        assert "10:00" in times
        assert "13:00" in times
        assert "16:00" in times

    def test_several_working_intervals_same_day_both_contribute(self):
        intervals = [
            working_interval(start_time="09:00", end_time="10:00"),
            working_interval(start_time="14:00", end_time="15:00"),
        ]
        slots = compute_available_start_times(intervals, 30, {})
        times = {s["time"] for s in slots}
        assert "09:00" in times
        assert "14:00" in times

    def test_adjacent_working_intervals_do_not_create_a_gap(self):
        intervals = [
            working_interval(start_time="09:00", end_time="10:00"),
            working_interval(start_time="10:00", end_time="11:00"),
        ]
        slots = compute_available_start_times(intervals, 60, {})
        times = {s["time"] for s in slots}
        assert times == {"09:00", "10:00"}

    def test_overlapping_working_intervals_deduplicate_candidates(self):
        intervals = [
            working_interval(start_time="09:00", end_time="11:00"),
            working_interval(start_time="10:00", end_time="12:00"),
        ]
        slots = compute_available_start_times(intervals, 60, {})
        times = [s["time"] for s in slots]
        # No duplicate (date, time) pairs even though both intervals offer 10:00.
        assert len(times) == len(set(times))
        assert "10:00" in times

    def test_no_slot_when_duration_longer_than_window(self):
        intervals = [working_interval(start_time="10:00", end_time="10:30")]
        assert compute_available_start_times(intervals, 60, {}) == []

    def test_malformed_overnight_interval_produces_no_crash_and_no_slots(self):
        # end_time <= start_time isn't representable within one `date` in
        # this schema (see the midnight-boundary requirement) - must not
        # crash, and must never offer a slot.
        intervals = [working_interval(start_time="23:00", end_time="01:00")]
        assert compute_available_start_times(intervals, 30, {}) == []

    def test_past_working_interval_is_filtered_out(self):
        intervals = [working_interval(date="2020-01-01", start_time="10:00", end_time="12:00")]
        assert compute_available_start_times(intervals, 30, {}) == []

    def test_zero_or_negative_duration_never_crashes(self):
        intervals = [working_interval(start_time="10:00", end_time="12:00")]
        assert compute_available_start_times(intervals, 0, {}) == []
        assert compute_available_start_times(intervals, -30, {}) == []

    def test_every_offered_duration_30_50_60_90_respects_the_window(self):
        intervals = [working_interval(start_time="10:00", end_time="13:00")]
        window_end = time_to_minutes("13:00")
        for duration in (30, 50, 60, 90):
            slots = compute_available_start_times(intervals, duration, {})
            for slot in slots:
                start = time_to_minutes(slot["time"])
                assert start + duration <= window_end
            assert slots, f"expected at least one {duration}-minute slot in a 3-hour window"
