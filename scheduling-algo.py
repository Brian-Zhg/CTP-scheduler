"""
Greedy task scheduler (Person B).

Input schema (matches Person A's Gemini extraction output):
    tasks = [
        {
            "title": str,
            "duration_minutes": int,
            "priority": int,                 # higher = more important
            "deadline": str | None,          # ISO 8601 datetime, or None
            "preferred_time": str | None,     # "morning" | "afternoon" | "evening" | None
        },
        ...
    ]

    free_blocks = [
        {"start": str, "end": str},          # ISO 8601 datetimes, non-overlapping, sorted
        ...
    ]

Output:
    {
        "scheduled": [
            {"title": str, "start": str, "end": str, "priority": int},
            ...
        ],
        "unscheduled": [task, ...]            # original task dicts that didn't fit anywhere
    }
"""

# --- Imports ---
# datetime/timedelta: all scheduling math (comparing, adding, subtracting time)
# is done with real datetime objects, not raw strings.
# Optional: type hint for arguments that may legitimately be None (e.g. no
# deadline, no time-of-day preference).
from datetime import datetime, timedelta
from typing import Optional

# --- Time-of-day preference lookup ---
# Maps a task's human-readable preference to an (inclusive-start, exclusive-end)
# hour range. Used by _fits_preference() below to decide whether a given block
# start time honors what the task asked for.
TIME_OF_DAY_RANGES = {
    "morning": (0, 12),
    "afternoon": (12, 17),
    "evening": (17, 24),
}


def _fits_preference(start: datetime, preferred_time: Optional[str]) -> bool:
    """Return True if `start` falls inside the task's preferred time-of-day window.

    No preference (None/empty) always passes. An unrecognized preference string
    falls back to the full-day range (0, 24) so it never wrongly blocks a task.
    """
    if not preferred_time:
        return True
    lo, hi = TIME_OF_DAY_RANGES.get(preferred_time, (0, 24))
    return lo <= start.hour < hi


def _normalize_blocks(free_blocks: list) -> list:
    """Turn raw free_blocks input into clean, mergeable [start, end] datetime pairs.

    This is what makes the scheduler resilient to messy upstream input instead
    of assuming free_blocks always arrives sorted and non-overlapping:
      1. Parse every block's ISO strings into real datetimes.
      2. Drop any block where end <= start (garbage/zero-length blocks).
      3. Sort by start time, so the placement loop always walks the day in order.
      4. Merge blocks that overlap or touch back-to-back into one bigger block,
         so a task's duration is checked against true continuous free time
         instead of being wrongly split/truncated by a duplicate or overlapping
         block from upstream.
    An empty input list naturally produces an empty output list, which is the
    "zero free slots" case — no special-casing needed here.
    """
    parsed = [
        [datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"])]
        for b in free_blocks
    ]
    parsed = [b for b in parsed if b[1] > b[0]]
    parsed.sort(key=lambda b: b[0])

    merged = []
    for block in parsed:
        if merged and block[0] <= merged[-1][1]:
            # Overlaps (or exactly touches) the last merged block: extend it
            # instead of adding a separate, potentially overlapping entry.
            merged[-1][1] = max(merged[-1][1], block[1])
        else:
            merged.append(block)

    return merged


def schedule_tasks(tasks: list, free_blocks: list) -> dict:
    """Greedy sort-and-place scheduler.

    Algorithm (per CLAUDE.md's Person B spec):
      1. Sort tasks by priority (highest first), then by deadline (earliest first).
      2. Walk the day's free blocks in chronological order.
      3. For each task, place it in the first block that both (a) has enough
         remaining time for its duration and (b) matches its preferred
         time-of-day, if any. Shrink that block from the front so the next
         task sees only the time left over.
      4. Any task that never finds a fitting block goes into `unscheduled`
         instead of blocking/crashing the rest of the run.
    No re-solving or backtracking: once a task is placed, its slot is final.
    """

    # --- Step 1: sort tasks so the most important/urgent get first pick of slots ---
    def sort_key(task):
        deadline = task.get("deadline")
        # Tasks with no deadline sort last among equal-priority tasks.
        deadline_dt = datetime.fromisoformat(deadline) if deadline else datetime.max
        return (-task["priority"], deadline_dt)

    sorted_tasks = sorted(tasks, key=sort_key)

    # --- Step 2: build the day's available time, cleaned up via _normalize_blocks ---
    # Mutable [start, end] pairs so a block can be shrunk as tasks fill it.
    blocks = _normalize_blocks(free_blocks)

    scheduled = []
    unscheduled = []

    # --- Step 3: greedily place each task into the first block that fits ---
    for task in sorted_tasks:
        duration = timedelta(minutes=task["duration_minutes"])
        placed = False

        for block in blocks:
            block_start, block_end = block

            # Not enough room left in this block for the task's duration.
            if block_end - block_start < duration:
                continue
            # Room exists, but it's not the time of day the task asked for.
            if not _fits_preference(block_start, task.get("preferred_time")):
                continue

            # This block works: place the task at the very front of it.
            task_end = block_start + duration
            scheduled.append({
                "title": task["title"],
                "start": block_start.isoformat(),
                "end": task_end.isoformat(),
                "priority": task["priority"],
            })
            block[0] = task_end  # shrink the block so later tasks see only what's left
            placed = True
            break

        # --- Step 4: nothing fit anywhere for this task ---
        if not placed:
            unscheduled.append(task)

    return {"scheduled": scheduled, "unscheduled": unscheduled}
# ------------------------------------------------------------------------------------

if __name__ == "__main__":
    # --- Hardcoded example: a normal day with tasks of mixed priority,
    # deadlines, and time-of-day preferences, plus enough free time for
    # everything to fit. This is the "happy path" the demo relies on. ---
    sample_tasks = [
        {"title": "Finish essay", "duration_minutes": 90, "priority": 3,
         "deadline": "2026-08-28T23:59:00", "preferred_time": None},
        {"title": "Gym", "duration_minutes": 60, "priority": 2,
         "deadline": None, "preferred_time": "morning"},
        {"title": "Read chapter 4", "duration_minutes": 45, "priority": 1,
         "deadline": "2026-08-30T23:59:00", "preferred_time": "evening"},
        {"title": "Team check-in", "duration_minutes": 30, "priority": 3,
         "deadline": "2026-08-27T17:00:00", "preferred_time": "afternoon"},
    ]

    sample_free_blocks = [
        {"start": "2026-08-27T09:00:00", "end": "2026-08-27T12:00:00"},
        {"start": "2026-08-27T13:00:00", "end": "2026-08-27T17:00:00"},
        {"start": "2026-08-27T19:00:00", "end": "2026-08-27T21:00:00"},
    ]

    # Run the scheduler and print the result so it's visually inspectable too.
    result = schedule_tasks(sample_tasks, sample_free_blocks)

    print("Scheduled:")
    for t in result["scheduled"]:
        print(f"  {t['title']}: {t['start']} -> {t['end']} (priority {t['priority']})")

    print("\nUnscheduled:")
    for t in result["unscheduled"]:
        print(f"  {t['title']}")

    # --- Automated sanity checks against the hardcoded example above ---
    # These turn the printed output into an actual pass/fail test instead of
    # something that has to be eyeballed every time the script runs.
    scheduled_by_title = {t["title"]: t for t in result["scheduled"]}

    # Everything should fit: 3 free blocks, 4 short tasks, no conflicts.
    assert len(result["scheduled"]) == 4, "expected all 4 sample tasks to fit"
    assert len(result["unscheduled"]) == 0, "expected nothing left unscheduled"

    # Priority sorting: both are priority 3, but Finish essay has an earlier
    # tiebreak (see sort_key) and no time preference, so it should claim the
    # 9am slot before the priority-2 Gym task gets placed.
    gym_start = datetime.fromisoformat(scheduled_by_title["Gym"]["start"])
    essay_start = datetime.fromisoformat(scheduled_by_title["Finish essay"]["start"])
    assert essay_start <= gym_start, "higher-priority task should be placed first"

    # Time-of-day preference: confirms _fits_preference actually constrains
    # placement rather than just being checked and ignored.
    checkin_start = datetime.fromisoformat(scheduled_by_title["Team check-in"]["start"])
    assert 12 <= checkin_start.hour < 17, "Team check-in should land in the afternoon"
    chapter_start = datetime.fromisoformat(scheduled_by_title["Read chapter 4"]["start"])
    assert chapter_start.hour >= 17, "Read chapter 4 should land in the evening"

    # No double-booking: sort all scheduled intervals and confirm each one
    # ends before (or exactly when) the next one starts.
    intervals = sorted(
        (datetime.fromisoformat(t["start"]), datetime.fromisoformat(t["end"]))
        for t in result["scheduled"]
    )
    for (start_a, end_a), (start_b, _end_b) in zip(intervals, intervals[1:]):
        assert end_a <= start_b, "scheduled tasks must not overlap"

    print("\nAll sanity checks passed.")

    # --- Edge case 1: zero free slots ---
    # No free time at all should degrade gracefully (every task unscheduled)
    # instead of raising, since _normalize_blocks([]) just returns [].
    zero_slot_result = schedule_tasks(sample_tasks, [])
    assert zero_slot_result["scheduled"] == [], "no free blocks means nothing can be scheduled"
    assert len(zero_slot_result["unscheduled"]) == len(sample_tasks), "every task should be unscheduled"
    print("Zero-free-slots check passed.")

    # --- Edge case 2: overlapping free blocks should be merged, not truncated ---
    # Simulates messy upstream input: two windows that overlap by an hour
    # (09:00-11:00 and 10:00-12:00) should behave as one continuous
    # 09:00-12:00 window, letting a task longer than either individual block
    # (150 minutes) still be placed.
    overlapping_blocks = [
        {"start": "2026-08-27T09:00:00", "end": "2026-08-27T11:00:00"},
        {"start": "2026-08-27T10:00:00", "end": "2026-08-27T12:00:00"},
    ]
    overlap_task = [{"title": "Study session", "duration_minutes": 150, "priority": 1,
                      "deadline": None, "preferred_time": None}]
    overlap_result = schedule_tasks(overlap_task, overlapping_blocks)
    assert len(overlap_result["scheduled"]) == 1, "task should fit in the merged 09:00-12:00 window"
    assert overlap_result["unscheduled"] == [], "task should not be unscheduled"
    session = overlap_result["scheduled"][0]
    assert session["start"] == "2026-08-27T09:00:00", "should start at the earliest merged block start"
    print("Overlapping-blocks check passed.")
