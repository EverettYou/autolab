"""Progress reporting for long-running lab cells.

Long training or eval loops should emit flushed progress on a timer (default 10 min) so
monitors see *progress*, not just process liveness. Lives in ``labs/_tools/`` with ``paths`` (see README).

Usage — wrap the work loop, call ``tick()`` per batch:

    from progress import Progress
    prog = Progress("sweep", target=60_000)
    for i in range(0, target, BATCH):
        ...
        prog.tick(done=done, extra=f"fails {fails}")
"""

from __future__ import annotations

import time


class Progress:
    """Throttle stdout progress for long loops (training sweeps, large evals).

    Each line is flushed immediately so process monitors see forward motion, not only PID liveness.
    Rate and ETA appear only after ~1 s of wall time and ``done > 0`` (early ticks omit bogus rates).

    The **first** :meth:`tick` always prints; the tick at ``done >= target`` always prints even if
    the interval has not elapsed.
    """

    def __init__(self, label: str, target: int, *, every: float = 600.0) -> None:
        """Start a progress scope.

        Args:
            label: Short name in the log line (e.g. ``"sweep"``, ``"dmrg"``).
            target: Total units expected (batches, shots, epochs) for percent and ETA.
            every: Minimum seconds between periodic lines (default 600 = 10 minutes).
        """
        self.label = label
        self.target = target
        self.every = every
        self.t0 = time.time()
        self._last = 0.0          # 0.0 rather than t0 so the first tick always prints

    def tick(self, done: int, *, extra: str = "", force: bool = False) -> None:
        """Maybe print a progress line for ``done`` units completed so far.

        Prints when any of: ``force``, first call, ``done >= target``, or ``every`` seconds since
        the last line.

        Args:
            done: Cumulative work units finished (monotonic).
            extra: Optional suffix (e.g. ``"fails 3"``) appended to the line.
            force: Print even if the throttle window has not elapsed.
        """
        now = time.time()
        final = done >= self.target
        if not (force or final or now - self._last >= self.every):
            return
        self._last = now
        elapsed = now - self.t0
        pct = 100.0 * done / self.target if self.target else 0.0
        head = (f"    [{elapsed:7.0f}s] {self.label}: {done}/{self.target} ({pct:.1f}%)"
                + (f"  {extra}" if extra else ""))
        # Below ~1 s of elapsed time a rate is meaningless — the first tick would otherwise report
        # something like 5e7 shots/s and an ETA of 0, which is precisely the kind of fabricated
        # number that gets quoted. Print no estimate rather than a wrong one.
        if elapsed < 1.0 or done <= 0:
            print(head + "  (rate not yet measurable)", flush=True)
            return
        rate = done / elapsed
        eta = (self.target - done) / rate / 60.0
        print(head + f"  {rate:.1f}/s  ETA {eta:.0f} min", flush=True)

    def done(self, done: int, *, extra: str = "") -> None:
        """Force one closing line when the loop ends before ``target`` (time cap, early stop).

        Same format as :meth:`tick`; always prints regardless of the throttle timer.
        """
        self.tick(done, extra=extra, force=True)
