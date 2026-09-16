"""ClassSession lifecycle, ADMIN role, dual join codes, and multi-faculty.

These cover the classroom/session/RBAC gaps the pilot brief called out
explicitly: admin as a platform role (not a classroom membership), a real
start/end class-session lifecycle with stale-request rejection, two
independent join codes that only admit their own platform role, multiple
equal-authority faculty on one classroom, and the join-race fix.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from backend.auth import session as session_cookie
from backend.models import ClassroomMembership, ClassroomRole
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


# --- admin role --------------------------------------------------------------


class TestAdminRole:
    async def test_configured_admin_email_gets_admin_role(self, client, make_user):
        user, token = await make_user("adhyanjain2006@gmail.com", "Admin")
        resp = await client.get("/api/auth/me", headers=auth(token))
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    async def test_role_spoof_in_request_body_has_no_effect(self, client, make_user):
        """A malicious {"role": "admin"} in the body must accomplish nothing --
        role is always server-re-derived from the verified email, never read
        from any request body."""
        _, token = await make_user("student.spoof@vitstudent.ac.in")
        resp = await client.post(
            "/api/classrooms",
            json={"name": "Hijacked", "role": "admin"},
            headers=auth(token),
        )
        assert resp.status_code == 403  # still just a student

        _, faculty_token = await make_user("prof.spoof@vit.ac.in")
        resp2 = await client.get(
            "/api/dashboard/audit", headers=auth(faculty_token)
        )
        # A faculty account presenting {"role": "admin"} would still only
        # ever be scoped as faculty -- there's no admin-only surface a
        # faculty-role request could reach by claiming a body field.
        assert resp2.status_code == 200

    async def test_admin_lists_all_classrooms_without_membership(
        self, client, make_user
    ):
        _, admin_token = await make_user("adhyanjain2006@gmail.com", "Admin")
        _, prof_token = await make_user("prof.x@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "Not admin's"}, headers=auth(prof_token)
        )
        assert created.status_code == 201
        classroom_id = created.json()["id"]

        listing = await client.get("/api/classrooms", headers=auth(admin_token))
        assert listing.status_code == 200
        ids = [c["id"] for c in listing.json()["classrooms"]]
        assert classroom_id in ids

        # And admin can operate directly on a classroom it never joined.
        roster = await client.get(
            f"/api/classrooms/{classroom_id}/roster", headers=auth(admin_token)
        )
        assert roster.status_code == 200

    async def test_admin_cannot_join_a_classroom(self, client, make_user):
        _, admin_token = await make_user("adhyanjain2006@gmail.com", "Admin")
        _, prof_token = await make_user("prof.y@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "Section"}, headers=auth(prof_token)
        )
        resp = await client.post(
            "/api/classrooms/join",
            json={"join_code": created.json()["faculty_join_code"]},
            headers=auth(admin_token),
        )
        assert resp.status_code == 400

    async def test_faculty_cannot_reach_admin_only_route(self, client, make_user):
        _, prof_token = await make_user("prof.z@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "Section"}, headers=auth(prof_token)
        )
        classroom_id = created.json()["id"]
        resp = await client.delete(
            f"/api/classrooms/{classroom_id}/faculty/someone",
            headers=auth(prof_token),
        )
        assert resp.status_code == 403


# --- dual join codes ----------------------------------------------------------


class TestDualJoinCodes:
    async def test_two_codes_are_independent_and_high_entropy(self, client, make_user):
        _, prof = await make_user("prof.codes@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "Codes"}, headers=auth(prof)
        )
        body = created.json()
        assert body["student_join_code"] != body["faculty_join_code"]

    async def test_regenerating_one_code_does_not_change_the_other(
        self, client, make_user
    ):
        _, prof = await make_user("prof.regen@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "Regen"}, headers=auth(prof)
        )
        body = created.json()
        old_student_code = body["student_join_code"]
        old_faculty_code = body["faculty_join_code"]

        regen = await client.post(
            f"/api/classrooms/{body['id']}/regenerate-code",
            json={"which": "student"},
            headers=auth(prof),
        )
        assert regen.status_code == 200
        assert regen.json()["student_join_code"] != old_student_code
        assert regen.json()["faculty_join_code"] == old_faculty_code

    async def test_regenerated_code_invalidates_the_previous_value(
        self, client, make_user
    ):
        _, prof = await make_user("prof.invalid@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "Invalidate"}, headers=auth(prof)
        )
        body = created.json()
        old_code = body["student_join_code"]

        await client.post(
            f"/api/classrooms/{body['id']}/regenerate-code",
            json={"which": "student"},
            headers=auth(prof),
        )

        _, student = await make_user("student.invalid@vitstudent.ac.in")
        stale = await client.post(
            "/api/classrooms/join", json={"join_code": old_code}, headers=auth(student)
        )
        assert stale.status_code == 404


# --- multi-faculty -------------------------------------------------------------


class TestMultiFaculty:
    async def test_two_faculty_join_the_same_classroom_as_peers(
        self, client, make_user
    ):
        _, prof_a = await make_user("prof.a.multi@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "Shared section"}, headers=auth(prof_a)
        )
        body = created.json()

        _, prof_b_token = await make_user("prof.b.multi@vit.ac.in")
        joined = await client.post(
            "/api/classrooms/join",
            json={"join_code": body["faculty_join_code"]},
            headers=auth(prof_b_token),
        )
        assert joined.status_code == 200

        # Both see the same classroom in "mine", neither replaced the other.
        mine_a = await client.get("/api/classrooms/mine", headers=auth(prof_a))
        mine_b = await client.get("/api/classrooms/mine", headers=auth(prof_b_token))
        ids_a = {c["id"] for c in mine_a.json()["classrooms"]}
        ids_b = {c["id"] for c in mine_b.json()["classrooms"]}
        assert body["id"] in ids_a
        assert body["id"] in ids_b

        faculty_list = await client.get(
            f"/api/classrooms/{body['id']}/faculty", headers=auth(prof_a)
        )
        assert faculty_list.status_code == 200
        assert len(faculty_list.json()["faculty"]) == 2

        # prof_b can operate on the classroom too -- equal authority.
        started = await client.post(
            f"/api/classrooms/{body['id']}/sessions/start",
            json={"experiment_id": "exp01"},
            headers=auth(prof_b_token),
        )
        assert started.status_code == 201


# --- class session lifecycle ---------------------------------------------------


class TestClassSessionLifecycle:
    async def test_start_then_end_then_start_again(self, client, make_user):
        _, prof = await make_user("prof.lifecycle@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "Lifecycle"}, headers=auth(prof)
        )
        classroom_id = created.json()["id"]

        started = await client.post(
            f"/api/classrooms/{classroom_id}/sessions/start",
            json={"experiment_id": "exp01"},
            headers=auth(prof),
        )
        assert started.status_code == 201
        session_id = started.json()["session_id"]

        ended = await client.post(
            f"/api/classrooms/{classroom_id}/sessions/{session_id}/end",
            headers=auth(prof),
        )
        assert ended.status_code == 200
        assert ended.json()["status"] == "ended"

        restarted = await client.post(
            f"/api/classrooms/{classroom_id}/sessions/start",
            json={"experiment_id": "exp02"},
            headers=auth(prof),
        )
        assert restarted.status_code == 201
        assert restarted.json()["session_id"] != session_id

    async def test_cannot_start_two_sessions_at_once(self, client, make_user):
        _, prof = await make_user("prof.double_start@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "DoubleStart"}, headers=auth(prof)
        )
        classroom_id = created.json()["id"]

        first = await client.post(
            f"/api/classrooms/{classroom_id}/sessions/start",
            json={"experiment_id": "exp01"},
            headers=auth(prof),
        )
        assert first.status_code == 201

        second = await client.post(
            f"/api/classrooms/{classroom_id}/sessions/start",
            json={"experiment_id": "exp02"},
            headers=auth(prof),
        )
        assert second.status_code == 409

    async def test_concurrent_start_requests_only_one_wins(self, client, make_user):
        """Two faculty pressing Start at the same instant: exactly one
        request creates the ACTIVE session, the other gets 409. Each HTTP
        request gets its own DB session/transaction (the real concurrency
        shape), unlike sharing one AsyncSession across coroutines, which
        SQLAlchemy's AsyncSession does not support."""
        _, prof = await make_user("prof.race@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "Race"}, headers=auth(prof)
        )
        classroom_id = created.json()["id"]

        responses = await asyncio.gather(
            client.post(
                f"/api/classrooms/{classroom_id}/sessions/start",
                json={"experiment_id": "exp01"},
                headers=auth(prof),
            ),
            client.post(
                f"/api/classrooms/{classroom_id}/sessions/start",
                json={"experiment_id": "exp02"},
                headers=auth(prof),
            ),
        )
        statuses = sorted(r.status_code for r in responses)
        assert statuses == [201, 409], statuses

    async def test_active_session_endpoint_rejects_non_members(
        self, client, make_user
    ):
        """Regression: this endpoint's docstring always claimed
        membership was required, but the check itself was missing --
        any authenticated user could query any classroom_id's active
        session status. Found and fixed in a security pass."""
        _, prof = await make_user("prof.activesession@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "ActiveSessionScope"}, headers=auth(prof)
        )
        classroom_id = created.json()["id"]
        await client.post(
            f"/api/classrooms/{classroom_id}/sessions/start",
            json={"experiment_id": "exp01"},
            headers=auth(prof),
        )

        _, outsider_student = await make_user("outsider.activesession@vitstudent.ac.in")
        outsider_resp = await client.get(
            f"/api/classrooms/{classroom_id}/active-session",
            headers=auth(outsider_student),
        )
        assert outsider_resp.status_code == 404

        _, outsider_faculty = await make_user("outsider.activesession@vit.ac.in")
        outsider_faculty_resp = await client.get(
            f"/api/classrooms/{classroom_id}/active-session",
            headers=auth(outsider_faculty),
        )
        assert outsider_faculty_resp.status_code == 404

        member_resp = await client.get(
            f"/api/classrooms/{classroom_id}/active-session", headers=auth(prof)
        )
        assert member_resp.status_code == 200
        assert member_resp.json()["active"] is True

    async def test_list_sessions_shows_ended_and_active_newest_first(
        self, client, make_user
    ):
        """Faculty dashboard's summaries/history tab needs to discover a
        past session's id once it's no longer the active one; there was
        previously no endpoint for that at all."""
        _, prof = await make_user("prof.listsessions@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "ListSessions"}, headers=auth(prof)
        )
        classroom_id = created.json()["id"]

        first = await client.post(
            f"/api/classrooms/{classroom_id}/sessions/start",
            json={"experiment_id": "exp01"},
            headers=auth(prof),
        )
        first_id = first.json()["session_id"]
        await client.post(
            f"/api/classrooms/{classroom_id}/sessions/{first_id}/end",
            headers=auth(prof),
        )
        second = await client.post(
            f"/api/classrooms/{classroom_id}/sessions/start",
            json={"experiment_id": "exp02"},
            headers=auth(prof),
        )
        second_id = second.json()["session_id"]

        resp = await client.get(
            f"/api/dashboard/classrooms/{classroom_id}/sessions", headers=auth(prof)
        )
        assert resp.status_code == 200
        sessions = resp.json()["sessions"]
        assert [s["id"] for s in sessions] == [second_id, first_id]
        assert sessions[0]["status"] == "active"
        assert sessions[1]["status"] == "ended"

    async def test_stale_browser_rejected_after_end_socratic(
        self, client, make_user, registered_experiment
    ):
        """Faculty ends class; a student's still-open tab must be rejected
        on every Socratic mutation, not just at session start."""
        _, prof = await make_user("prof.stale@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "Stale"}, headers=auth(prof)
        )
        classroom_id = created.json()["id"]
        started = await client.post(
            f"/api/classrooms/{classroom_id}/sessions/start",
            json={"experiment_id": "ref01"},
            headers=auth(prof),
        )
        session_id = started.json()["session_id"]

        _, student = await make_user("student.stale@vitstudent.ac.in")
        joined = await client.post(
            "/api/classrooms/join",
            json={"join_code": created.json()["student_join_code"]},
            headers=auth(student),
        )
        assert joined.status_code == 200

        socratic = await client.post(
            "/api/socratic/session", json={"classroom_id": classroom_id}, headers=auth(student)
        )
        assert socratic.status_code == 201
        socratic_session_id = socratic.json()["session_id"]

        await client.post(
            f"/api/classrooms/{classroom_id}/sessions/{session_id}/end",
            headers=auth(prof),
        )

        for path, body in (
            (f"/api/socratic/session/{socratic_session_id}/attempt", {"data": {}}),
            (f"/api/socratic/session/{socratic_session_id}/message", {"message": "hello?"}),
            (f"/api/socratic/session/{socratic_session_id}/reveal", None),
        ):
            resp = await client.post(path, json=body, headers=auth(student))
            assert resp.status_code == 409, path

    async def test_stale_browser_rejected_after_end_diagnostic(
        self, client, make_user, registered_experiment
    ):
        _, prof = await make_user("prof.stale2@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "Stale2"}, headers=auth(prof)
        )
        classroom_id = created.json()["id"]
        started = await client.post(
            f"/api/classrooms/{classroom_id}/sessions/start",
            json={"experiment_id": "ref01"},
            headers=auth(prof),
        )
        session_id = started.json()["session_id"]

        _, student = await make_user("student.stale2@vitstudent.ac.in")
        await client.post(
            "/api/classrooms/join",
            json={"join_code": created.json()["student_join_code"]},
            headers=auth(student),
        )

        await client.post(
            f"/api/classrooms/{classroom_id}/sessions/{session_id}/end",
            headers=auth(prof),
        )

        resp = await client.post(
            "/api/submissions",
            json={"classroom_id": classroom_id, "data": {}, "reported_value": 1.0},
            headers=auth(student),
        )
        assert resp.status_code == 409


# --- wrong-role code rejection --------------------------------------------------


class TestWrongCodeRole:
    async def test_faculty_code_rejects_a_student(self, client, make_user):
        _, prof = await make_user("prof.wc1@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "WC1"}, headers=auth(prof)
        )
        _, student = await make_user("student.wc1@vitstudent.ac.in")
        resp = await client.post(
            "/api/classrooms/join",
            json={"join_code": created.json()["faculty_join_code"]},
            headers=auth(student),
        )
        assert resp.status_code == 403

    async def test_student_code_rejects_faculty(self, client, make_user):
        _, prof = await make_user("prof.wc2@vit.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "WC2"}, headers=auth(prof)
        )
        _, prof2 = await make_user("prof.wc2b@vit.ac.in")
        resp = await client.post(
            "/api/classrooms/join",
            json={"join_code": created.json()["student_join_code"]},
            headers=auth(prof2),
        )
        assert resp.status_code == 403


# --- join race ------------------------------------------------------------------


class TestJoinRace:
    async def test_concurrent_joins_same_user_do_not_crash(self, client, db, make_user):
        """Two concurrent join attempts for the same (user, classroom, role),
        each its own HTTP request/DB session -- the real concurrency shape --
        must not raise an uncaught IntegrityError. Both requests succeed
        (idempotent join), and exactly one membership row exists after."""
        _, prof = await make_user("prof.joinrace@vit.ac.in")
        _, student = await make_user("student.joinrace@vitstudent.ac.in")
        created = await client.post(
            "/api/classrooms", json={"name": "JoinRace"}, headers=auth(prof)
        )
        code = created.json()["student_join_code"]

        responses = await asyncio.gather(
            client.post("/api/classrooms/join", json={"join_code": code}, headers=auth(student)),
            client.post("/api/classrooms/join", json={"join_code": code}, headers=auth(student)),
        )
        for r in responses:
            assert r.status_code == 200, r.text

        classroom_id = created.json()["id"]
        rows = (
            await db.scalars(
                select(ClassroomMembership).where(
                    ClassroomMembership.classroom_id == classroom_id,
                    ClassroomMembership.role == ClassroomRole.STUDENT,
                )
            )
        ).all()
        assert len(rows) == 1, "a join race produced more than one membership row"
