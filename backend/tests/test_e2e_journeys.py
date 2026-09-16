"""Live end-to-end verification that Q&A, Socratic, diagnostic and summary
pipelines actually work together for one real student journey, driven
entirely through the real HTTP routes (not unit-level engine calls).

This exists because unit tests for each piece passing does not prove the
pieces compose: a student's real path is join -> class starts -> ask a
question -> work a guided session step by step to completion -> reveal ->
submit a finished record for diagnosis -> class ends -> a summary is
queued and generated -- and every stage's output must be exactly what the
next stage consumes.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.auth import session as session_cookie
from backend.tests.reference_plugin import (
    EXPECTED_ENDPOINT,
    EXPECTED_FINAL_VALUE,
    STUDENT_DATA,
    reference_plugin,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def registered_experiment(monkeypatch):
    from backend.tier1_compute.experiments import registry

    plugin = reference_plugin()
    monkeypatch.setitem(registry._REGISTRY, plugin.id, plugin)
    return plugin


def auth(token: str) -> dict[str, str]:
    return {"Cookie": f"{session_cookie.COOKIE_NAME}={token}"}


async def test_full_student_journey_qa_socratic_diagnostic_summary(
    client, make_user, registered_experiment
):
    # --- faculty starts class -----------------------------------------
    _, prof = await make_user("e2e.prof@vit.ac.in")
    created = await client.post(
        "/api/classrooms", json={"name": "E2E section"}, headers=auth(prof)
    )
    assert created.status_code == 201, created.text
    classroom = created.json()
    started = await client.post(
        f"/api/classrooms/{classroom['id']}/sessions/start",
        json={"experiment_id": "ref01"},
        headers=auth(prof),
    )
    assert started.status_code == 201, started.text
    class_session_id = started.json()["session_id"]

    # --- student joins and completes onboarding ------------------------
    _, student = await make_user("e2e.student@vitstudent.ac.in")
    completed = await client.post(
        "/api/auth/complete-profile",
        json={"name": "E2E Student", "reg_no": "21BCE9999"},
        headers=auth(student),
    )
    assert completed.status_code == 200
    assert completed.json()["profile_complete"] is True

    joined = await client.post(
        "/api/classrooms/join",
        json={"join_code": classroom["student_join_code"]},
        headers=auth(student),
    )
    assert joined.status_code == 200, joined.text

    # --- Q&A: grounded chatbot, cited answer, then a follow-up ---------
    ask1 = await client.post(
        "/api/qa/ask",
        json={"classroom_id": classroom["id"], "message": "What is Beer-Lambert law?"},
        headers=auth(student),
    )
    assert ask1.status_code == 200, ask1.text
    body1 = ask1.json()
    assert "reply" in body1 and "citations" in body1

    ask2 = await client.post(
        "/api/qa/ask",
        json={"classroom_id": classroom["id"], "message": "Can you say more about that?"},
        headers=auth(student),
    )
    assert ask2.status_code == 200, ask2.text

    history = await client.get(
        f"/api/qa/history?classroom_id={classroom['id']}", headers=auth(student)
    )
    assert history.status_code == 200
    assert len(history.json()["messages"]) == 4  # 2 student + 2 tutor turns

    # --- Socratic: full lifecycle, step by step, to completion ---------
    session_resp = await client.post(
        "/api/socratic/session", json={"classroom_id": classroom["id"]}, headers=auth(student)
    )
    assert session_resp.status_code == 201, session_resp.text
    socratic = session_resp.json()
    session_id = socratic["session_id"]
    assert socratic["complete"] is False

    step0 = await client.post(
        f"/api/socratic/session/{session_id}/attempt",
        json={
            "data": {
                "standard_normality": STUDENT_DATA["standard_normality"],
                "standard_volume": STUDENT_DATA["standard_volume"],
            },
            "value": STUDENT_DATA["standard_normality"] * STUDENT_DATA["standard_volume"],
        },
        headers=auth(student),
    )
    assert step0.status_code == 200, step0.text
    assert step0.json()["passed"] is True

    step1 = await client.post(
        f"/api/socratic/session/{session_id}/attempt",
        json={
            "data": {
                "titrant_volumes": STUDENT_DATA["titrant_volumes"],
                "conductance": STUDENT_DATA["conductance"],
            },
            "value": EXPECTED_ENDPOINT,
        },
        headers=auth(student),
    )
    assert step1.status_code == 200, step1.text
    assert step1.json()["passed"] is True

    step2 = await client.post(
        f"/api/socratic/session/{session_id}/attempt",
        json={
            "data": {
                "standard_normality": STUDENT_DATA["standard_normality"],
                "standard_volume": STUDENT_DATA["standard_volume"],
                "titre_volume": STUDENT_DATA["titre_volume"],
            },
            "value": EXPECTED_FINAL_VALUE,
        },
        headers=auth(student),
    )
    assert step2.status_code == 200, step2.text
    final = step2.json()
    assert final["passed"] is True
    assert final["complete"] is True

    reveal = await client.post(
        f"/api/socratic/session/{session_id}/reveal", headers=auth(student)
    )
    assert reveal.status_code == 200, reveal.text

    # --- diagnostic: independent submission, correctly diagnosed --------
    submitted = await client.post(
        "/api/submissions",
        json={
            "classroom_id": classroom["id"],
            "data": {
                "standard_normality": STUDENT_DATA["standard_normality"],
                "standard_volume": STUDENT_DATA["standard_volume"],
                "titre_volume": STUDENT_DATA["titre_volume"],
            },
            "reported_value": EXPECTED_FINAL_VALUE,
        },
        headers=auth(student),
    )
    assert submitted.status_code == 201, submitted.text
    diag = submitted.json()
    assert diag["status"] == "pass"
    assert diag["tier"] == 1

    mine = await client.get("/api/submissions/mine", headers=auth(student))
    assert mine.status_code == 200
    assert len(mine.json()["submissions"]) == 1
    assert mine.json()["submissions"][0]["status"] == "pass"

    # --- faculty view: submissions dashboard sees the real student's work
    dash = await client.get(
        f"/api/dashboard/classrooms/{classroom['id']}/submissions", headers=auth(prof)
    )
    assert dash.status_code == 200
    assert len(dash.json()["submissions"]) == 1
    assert dash.json()["submissions"][0]["actor_type"] == "student"

    # --- end class: summary auto-queued, generated, faculty-visible only
    ended = await client.post(
        f"/api/classrooms/{classroom['id']}/sessions/{class_session_id}/end",
        headers=auth(prof),
    )
    assert ended.status_code == 200, ended.text

    summaries = None
    for _ in range(40):
        summaries = await client.get(
            f"/api/dashboard/classrooms/{classroom['id']}/sessions/"
            f"{class_session_id}/summaries",
            headers=auth(prof),
        )
        if summaries.status_code == 200 and summaries.json()["summaries"]:
            break
        await asyncio.sleep(0.05)
    assert summaries is not None and summaries.status_code == 200
    rows = summaries.json()["summaries"]
    assert len(rows) == 1
    assert rows[0]["text"]

    # Never returned on any student route.
    student_side = await client.get(
        f"/api/dashboard/classrooms/{classroom['id']}/sessions/"
        f"{class_session_id}/summaries",
        headers=auth(student),
    )
    assert student_side.status_code == 403

    # Stale session enforcement: further Q&A/submission attempts after
    # class end must be rejected, even though the student never reloaded
    # (same "stale tab" scenario the goal calls out).
    stale_ask = await client.post(
        "/api/qa/ask",
        json={"classroom_id": classroom["id"], "message": "one more thing"},
        headers=auth(student),
    )
    assert stale_ask.status_code == 409

    stale_submit = await client.post(
        "/api/submissions",
        json={"classroom_id": classroom["id"], "data": {}, "reported_value": 1.0},
        headers=auth(student),
    )
    assert stale_submit.status_code == 409


async def test_full_faculty_testing_journey_never_touches_student_analytics(
    client, make_user, registered_experiment
):
    """Faculty exercise the same engines a student would (Socratic testing,
    diagnostic testing) without an active class session, and none of it
    counts as, or is visible mixed in with, real student activity."""
    _, prof = await make_user("e2e2.prof@vit.ac.in")
    created = await client.post(
        "/api/classrooms", json={"name": "E2E faculty testing"}, headers=auth(prof)
    )
    classroom = created.json()

    # No active class session yet -- faculty ask still works.
    ask = await client.post(
        "/api/qa/ask",
        json={"classroom_id": classroom["id"], "message": "What is a titration endpoint?"},
        headers=auth(prof),
    )
    assert ask.status_code == 200, ask.text

    # Faculty Socratic test session, explicit experiment_id (no active class).
    session_resp = await client.post(
        "/api/socratic/session",
        json={"classroom_id": classroom["id"], "experiment_id": "ref01"},
        headers=auth(prof),
    )
    assert session_resp.status_code == 201, session_resp.text
    session_id = session_resp.json()["session_id"]
    assert session_resp.json().get("actor_type") == "faculty_test"

    # Faculty diagnostic test submission, same explicit-experiment override.
    submitted = await client.post(
        "/api/submissions",
        json={
            "classroom_id": classroom["id"],
            "experiment_id": "ref01",
            "data": {
                "standard_normality": STUDENT_DATA["standard_normality"],
                "standard_volume": STUDENT_DATA["standard_volume"],
                "titre_volume": STUDENT_DATA["titre_volume"],
            },
            "reported_value": EXPECTED_FINAL_VALUE,
        },
        headers=auth(prof),
    )
    assert submitted.status_code == 201, submitted.text

    # Faculty test activity shows up on the dashboard, correctly tagged --
    # never silently mixed into "student" rows.
    dash = await client.get(
        f"/api/dashboard/classrooms/{classroom['id']}/submissions", headers=auth(prof)
    )
    assert dash.status_code == 200
    rows = dash.json()["submissions"]
    assert len(rows) == 1
    assert rows[0]["actor_type"] == "faculty_test"

    # A real student's own submissions/coverage never include this.
    _, student = await make_user("e2e2.student@vitstudent.ac.in")
    await client.post(
        "/api/classrooms/join",
        json={"join_code": classroom["student_join_code"]},
        headers=auth(student),
    )
    mine = await client.get("/api/submissions/mine", headers=auth(student))
    assert mine.status_code == 200
    assert mine.json()["submissions"] == []
