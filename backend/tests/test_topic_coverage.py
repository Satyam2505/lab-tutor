"""Deterministic per-experiment coverage/engagement metric for faculty.

Verifies the score against fixture data with a hand-worked expected value
(this repo's testing philosophy: no fabricated expected values) and that
it is reachable through the API for both a genuine faculty member and a
classroom-scoped co-faculty, but not for an unrelated student.
"""

from __future__ import annotations

import pytest

from backend.auth import session as session_cookie
from backend.tests.reference_plugin import reference_plugin

pytestmark = pytest.mark.asyncio


@pytest.fixture
def registered_experiment(monkeypatch):
    from backend.tier1_compute.experiments import registry

    plugin = reference_plugin()
    monkeypatch.setitem(registry._REGISTRY, plugin.id, plugin)
    return plugin


def auth(token: str) -> dict[str, str]:
    return {"Cookie": f"{session_cookie.COOKIE_NAME}={token}"}


async def _make_classroom(client, faculty_token, experiment_id="ref01"):
    created = await client.post(
        "/api/classrooms", json={"name": "Coverage test"}, headers=auth(faculty_token)
    )
    classroom = created.json()
    started = await client.post(
        f"/api/classrooms/{classroom['id']}/sessions/start",
        json={"experiment_id": experiment_id},
        headers=auth(faculty_token),
    )
    classroom["active_session_id"] = started.json()["session_id"]
    return classroom


async def test_coverage_score_is_computed_by_hand_from_known_counts():
    """steps_attempted=2, steps_passed=1, 1 submission, 1 passed diagnosis,
    0 qa messages -> engagement = 10(steps)+10(submission)+0(qa)+10(diag)=30
    (capped at 40, unaffected here); correctness = 30*(1/1 diag passed) +
    30*(1/2 steps passed) = 30 + 15 = 45. Total = 30 + 45 = 75."""
    from backend.summaries.coverage import _score

    score = _score(
        steps_attempted=2, steps_passed=1, submissions=1,
        diagnoses_passed=1, diagnoses_failed=0, diagnoses_escalated=0,
        qa_messages=0,
    )
    assert score == 75


async def test_untouched_experiment_never_appears_in_the_rollup(client, make_user, registered_experiment):
    _, prof = await make_user("coverage.prof@vit.ac.in")
    classroom = await _make_classroom(client, prof)
    _, student = await make_user("coverage.student@vitstudent.ac.in")
    await client.post(
        "/api/classrooms/join",
        json={"join_code": classroom["student_join_code"]},
        headers=auth(student),
    )
    resp = await client.get(
        f"/api/dashboard/classrooms/{classroom['id']}/students/"
        f"{(await client.get('/api/auth/me', headers=auth(student))).json()['id']}/coverage",
        headers=auth(prof),
    )
    assert resp.status_code == 200
    assert resp.json()["topics"] == []


async def test_submission_activity_produces_a_scored_topic_row(
    client, make_user, registered_experiment
):
    _, prof = await make_user("coverage2.prof@vit.ac.in")
    classroom = await _make_classroom(client, prof)
    _, student = await make_user("coverage2.student@vitstudent.ac.in")
    await client.post(
        "/api/classrooms/join",
        json={"join_code": classroom["student_join_code"]},
        headers=auth(student),
    )
    submitted = await client.post(
        "/api/submissions",
        json={"classroom_id": classroom["id"], "data": {}, "reported_value": 1.0},
        headers=auth(student),
    )
    assert submitted.status_code == 201, submitted.text
    student_id = (await client.get("/api/auth/me", headers=auth(student))).json()["id"]

    resp = await client.get(
        f"/api/dashboard/classrooms/{classroom['id']}/students/{student_id}/coverage",
        headers=auth(prof),
    )
    assert resp.status_code == 200
    topics = resp.json()["topics"]
    assert len(topics) == 1
    assert topics[0]["experiment_id"] == "ref01"
    assert topics[0]["submissions"] == 1
    assert 0 <= topics[0]["coverage_score"] <= 100


async def test_promoted_co_faculty_can_view_coverage_for_their_classroom(
    client, make_user, registered_experiment
):
    _, prof = await make_user("coverage3.prof@vit.ac.in")
    classroom = await _make_classroom(client, prof)
    _, promoted = await make_user("coverage3.promoted@vitstudent.ac.in")
    await client.post(
        "/api/classrooms/join",
        json={"join_code": classroom["student_join_code"]},
        headers=auth(promoted),
    )
    promoted_id = (await client.get("/api/auth/me", headers=auth(promoted))).json()["id"]
    await client.post(
        f"/api/classrooms/{classroom['id']}/promote",
        json={"student_user_id": promoted_id},
        headers=auth(prof),
    )

    resp = await client.get(
        f"/api/dashboard/classrooms/{classroom['id']}/coverage", headers=auth(promoted)
    )
    assert resp.status_code == 200


async def test_unrelated_student_cannot_view_classroom_coverage(
    client, make_user, registered_experiment
):
    _, prof = await make_user("coverage4.prof@vit.ac.in")
    classroom = await _make_classroom(client, prof)
    _, outsider = await make_user("coverage4.outsider@vitstudent.ac.in")

    resp = await client.get(
        f"/api/dashboard/classrooms/{classroom['id']}/coverage", headers=auth(outsider)
    )
    assert resp.status_code == 403
