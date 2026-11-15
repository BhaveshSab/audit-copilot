import json

import httpx
import pytest
from audit_copilot.app import create_app
from audit_copilot.config import Settings


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(state_path=str(tmp_path / "state.db")))


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer demo"},
    ) as c:
        yield c


async def propose(c):
    r = await c.post(
        "/api/investigations",
        json={
            "cycle_id": "demo-cycle",
            "item_id": "demo-item",
            "question": "missing asset transfer custody human approval",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_complete_demo_human_approval_and_retry(client, app):
    row = await propose(client)
    assert row["payload"]["verification"] == "fixture-only"
    assert row["state"] == "AWAITING_REVIEW"
    assert app.state.demo.mark == "MISSING"
    body = {"action": "approve", "note": "Demo human reviewed source facts"}
    r = await client.post(f"/api/findings/{row['id']}/review", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "APPLIED"
    retry = await client.post(f"/api/findings/{row['id']}/review", json=body)
    assert retry.json()["receipt"] == r.json()["receipt"]
    with app.state.store.connect() as db:
        assert (
            db.execute("SELECT count(*) FROM event WHERE state='APPLIED'").fetchone()[0]
            == 1
        )
    assert "Bearer" not in json.dumps(app.state.store.get(row["id"], "demo-reviewer"))


async def test_reject_never_applies(client, app):
    row = await propose(client)
    r = await client.post(
        f"/api/findings/{row['id']}/review",
        json={"action": "reject", "note": "Need better evidence"},
    )
    assert r.status_code == 200 and r.json()["state"] == "REJECTED"
    assert not app.state.demo.applied
    assert (
        await client.post(
            f"/api/findings/{row['id']}/review",
            json={"action": "approve", "note": "Changed mind"},
        )
    ).status_code == 409


async def test_stale_proposal(client, app):
    row = await propose(client)
    app.state.demo.version = "2026-02-01T00:00:00.000Z"
    assert (
        await client.post(
            f"/api/findings/{row['id']}/review",
            json={"action": "approve", "note": "Approve"},
        )
    ).status_code == 409
    assert not app.state.demo.applied


async def test_ambiguous_write_retry_reuses_key(client, app, monkeypatch):
    row = await propose(client)
    original = app.state.demo.apply
    called = 0

    async def flaky(*a, **kw):
        nonlocal called
        result = await original(*a, **kw)
        called += 1
        if called == 1:
            raise httpx.ReadTimeout("response lost")
        return result

    monkeypatch.setattr(app.state.demo, "apply", flaky)
    body = {"action": "approve", "note": "Stable approval"}
    assert (
        await client.post(f"/api/findings/{row['id']}/review", json=body)
    ).status_code == 502
    assert app.state.store.get(row["id"], "demo-reviewer")["state"] == "APPLYING"
    wrong = await client.post(
        f"/api/findings/{row['id']}/review", json={**body, "note": "Changed"}
    )
    assert wrong.status_code == 409
    retry = await client.post(f"/api/findings/{row['id']}/review", json=body)
    assert retry.status_code == 200 and retry.json()["state"] == "APPLIED"
    assert len(app.state.demo.applied) == 1


async def test_auth_validation_and_scope(client):
    assert (
        await client.get("/api/findings", headers={"Authorization": ""})
    ).status_code == 401
    assert (
        await client.get("/api/findings", headers={"Authorization": "Bearer wrong"})
    ).status_code == 401
    assert (
        await client.post(
            "/api/investigations", json={"cycle_id": "../secret", "item_id": "x"}
        )
    ).status_code == 422
    assert (
        await client.post(
            "/api/investigations",
            json={"cycle_id": "demo-cycle", "item_id": "demo-item", "role": "ADMIN"},
        )
    ).status_code == 422
    assert (
        await client.post(
            "/api/investigations", json={"cycle_id": "other", "item_id": "demo-item"}
        )
    ).status_code == 409
    assert (await client.get("/api/findings/not-found")).status_code == 404
    r = await client.post("/api/investigations", content="x" * 16001)
    assert r.status_code == 413


async def test_owner_isolation_and_expiry(client, app):
    row = await propose(client)
    with app.state.store.connect() as db:
        db.execute("UPDATE finding SET owner='different' WHERE id=?", (row["id"],))
    assert (await client.get(f"/api/findings/{row['id']}")).status_code == 404
    with app.state.store.connect() as db:
        db.execute(
            "UPDATE finding SET owner='demo-reviewer',created=0 WHERE id=?",
            (row["id"],),
        )
    assert (
        await client.post(
            f"/api/findings/{row['id']}/review",
            json={"action": "approve", "note": "Approve"},
        )
    ).status_code == 409


async def test_headers_list_and_health(client):
    row = await propose(client)
    r = await client.get("/api/findings")
    assert r.json()[0]["id"] == row["id"]
    assert r.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert (await client.get("/health")).json()["mode"] == "demo"
