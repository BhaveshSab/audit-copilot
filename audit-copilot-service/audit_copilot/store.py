"""Durable local proposals/receipts. No bearer tokens. Single-node MVP store."""

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path


class StateConflict(Exception):
    pass


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = path
        with self.connect() as db:
            db.executescript("""PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS finding(id TEXT PRIMARY KEY,owner TEXT NOT NULL,payload TEXT NOT NULL,
              state TEXT NOT NULL,review TEXT,receipt TEXT,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS event(id INTEGER PRIMARY KEY, finding_id TEXT,actor TEXT,state TEXT,at REAL);
            """)
        os.chmod(path, 0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def create(self, owner, payload):
        fid = str(uuid.uuid4())
        state = "REFUSED" if payload["finding"]["refused"] else "AWAITING_REVIEW"
        with self.connect() as db:
            db.execute(
                "INSERT INTO finding VALUES(?,?,?,?,NULL,NULL,?)",
                (fid, owner, json.dumps(payload), state, time.time()),
            )
            db.execute(
                "INSERT INTO event(finding_id,actor,state,at) VALUES(?,?,?,?)",
                (fid, owner, state, time.time()),
            )
        return self.get(fid, owner)

    def get(self, fid, owner):
        with self.connect() as db:
            r = db.execute(
                "SELECT * FROM finding WHERE id=? AND owner=?", (fid, owner)
            ).fetchone()
        if not r:
            raise KeyError("Finding not found")
        return {
            **dict(r),
            "payload": json.loads(r["payload"]),
            "review": json.loads(r["review"]) if r["review"] else None,
            "receipt": json.loads(r["receipt"]) if r["receipt"] else None,
        }

    def list(self, owner):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id,state,created FROM finding WHERE owner=? ORDER BY created DESC LIMIT 100",
                    (owner,),
                )
            ]

    def transition(self, fid, owner, expected, state, review=None, receipt=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            r = db.execute(
                "SELECT state,review,receipt FROM finding WHERE id=? AND owner=?",
                (fid, owner),
            ).fetchone()
            if not r:
                raise KeyError("Finding not found")
            if r["state"] not in expected:
                raise StateConflict("Finding is not in a reviewable state")
            db.execute(
                "UPDATE finding SET state=?,review=?,receipt=? WHERE id=?",
                (
                    state,
                    json.dumps(review) if review else r["review"],
                    json.dumps(receipt) if receipt else r["receipt"],
                    fid,
                ),
            )
            db.execute(
                "INSERT INTO event(finding_id,actor,state,at) VALUES(?,?,?,?)",
                (fid, owner, state, time.time()),
            )
