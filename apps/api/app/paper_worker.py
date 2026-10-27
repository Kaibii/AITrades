"""Durable historical replay worker. Never instantiates a network brokerage adapter."""

import argparse
import logging
import signal
import threading
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.database import PaperSession, PaperWorkerHeartbeat, SessionLocal
from app.logging import configure_logging
from app.paper import advance, risk_event


def process_once(session_factory=SessionLocal, worker_id: str = "manual-worker") -> int:
    with session_factory() as db:
        pulse = db.get(PaperWorkerHeartbeat, worker_id)
        if pulse is None:
            db.add(PaperWorkerHeartbeat(id=worker_id, last_seen=datetime.now(UTC)))
        else:
            pulse.last_seen = datetime.now(UTC)
        db.commit()
        candidates = list(
            db.execute(
                select(PaperSession.id, PaperSession.cursor)
                .where(PaperSession.status == "running")
                .order_by(PaperSession.created_at)
                .limit(100)
            )
        )
    processed = 0
    for session_id, cursor in candidates:
        try:
            with session_factory() as db:
                account = advance(db, session_id, cursor, skip_locked=True)
                if account and account.cursor > cursor:
                    processed += 1
                db.commit()
        except Exception:
            # Replay fills have no external side effects: rollback is enough to undo a tick.
            with session_factory() as db:
                account = db.scalar(
                    select(PaperSession).where(PaperSession.id == session_id).with_for_update()
                )
                if account and account.status == "running":
                    risk_event(db, account, "Worker error; replay suspended for review", None)
                    db.commit()
            logging.getLogger("quantpilot").error("paper_replay_tick_failed")
    return processed


def main():
    parser = argparse.ArgumentParser(
        description="Historical paper replay worker (no broker access)"
    )
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.interval <= 60:
        parser.error("interval must be between 1 and 60 seconds")
    configure_logging()
    worker_id = str(uuid4())
    stopped = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stopped.set())
    while not stopped.is_set():
        process_once(worker_id=worker_id)
        if args.once:
            break
        stopped.wait(args.interval)


if __name__ == "__main__":
    main()
