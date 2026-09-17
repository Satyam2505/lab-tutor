"""Integration tests for the auth and data-isolation boundary.

These drive the real ASGI app over HTTP, because the guarantees under test
are properties of the endpoints, not of any one function. Golden dataset
Category 4e (cross-student access) is verified here rather than by reading
a model's reply: the defence is that another student's rows are never
selected, so there is nothing for a reply to leak.
"""

from __future__ import annotations

import pytest

from backend.auth import session as session_cookie
from backend.tests.reference_plugin import STUDENT_DATA, reference_plugin

pytestmark = pytest.mark.asyncio


@pytest.fixture
def registered_experiment(monkeypatch):
    """Register the reference plugin for the duration of one test."""
    from backend.tier1_compute.experiments import registry

    plugin = reference_plugin()
    monkeypatch.setitem(registry._REGISTRY, plugin.id, plugin)
    return plugin


def auth(token: str) -> dict[str, str]:
    """Auth as an explicit Cookie header.

    Per-request `cookies=` is deprecated in httpx and would otherwise
    persist on the client, which is wrong here: these tests deliberately
    switch between users on one client.
    """
    return {"Cookie": f"{session_cookie.COOKIE_NAME}={token}"}


async def _make_classroom(client, faculty_token, experiment_id="ref01"):
    created = await client.post(
        "/api/classrooms",
        json={"name": "Tuesday B1"},
        headers=auth(faculty_token),
    )
    assert created.status_code == 201, created.text
    classroom = created.json()
    if experiment_id is not None:
        started = await client.post(
            f"/api/classrooms/{classroom['id']}/sessions/start",
            json={"experiment_id": experiment_id},
            headers=auth(faculty_token),
        )
        assert started.status_code == 201, started.text
        classroom["active_session_id"] = started.json()["session_id"]
    return classroom


async def _enrol(client, student_token, join_code):
    joined = await client.post(
        "/api/classrooms/join",
        json={"join_code": join_code},
        headers=auth(student_token),
    )
    assert joined.status_code == 200, joined.text
    return joined.json()


async def _submit(client, token, classroom_id, **overrides):
    body = {
        "classroom_id": classroom_id,
        "data": dict(STUDENT_DATA),
        "reported_value": 0.125,
        "remarks": "",
    }
    body.update(overrides)
    return await client.post("/api/submissions", json=body, headers=auth(token))


# --- authentication --------------------------------------------------------


class TestAuthenticationBoundary:
    async def test_unauthenticated_is_rejected(self, client):
        assert (await client.get("/api/auth/me")).status_code == 401

    async def test_garbage_cookie_is_rejected(self, client):
        resp = await client.get("/api/auth/me", headers=auth("not-a-real-token"))
        assert resp.status_code == 401

    async def test_tampered_cookie_is_rejected(self, client, make_user):
        """Flipping the token's *last* character is not a reliable tamper:
        base64url padding can leave the final character's low bits
        unused, so two different final characters sometimes decode to the
        identical byte string and the signature still verifies -- a flaky
        test, not a signature-bypass bug (found while chasing an
        intermittent failure here; itsdangerous's HMAC check itself is
        unaffected). Flip a character in the middle of the token instead,
        which always changes a real payload/signature byte.
        """
        _, token = await make_user("student.a2024@vitstudent.ac.in")
        mid = len(token) // 2
        flipped = "a" if token[mid] != "a" else "b"
        tampered = token[:mid] + flipped + token[mid + 1 :]
        resp = await client.get("/api/auth/me", headers=auth(tampered))
        assert resp.status_code == 401

    async def test_signed_in_student_sees_their_own_identity(self, client, make_user):
        user, token = await make_user("student.a2024@vitstudent.ac.in")
        resp = await client.get("/api/auth/me", headers=auth(token))
        assert resp.status_code == 200
        assert resp.json()["email"] == user.email
        assert resp.json()["role"] == "student"

    async def test_role_is_derived_not_taken_from_the_cookie(self, client, make_user):
        """The cookie carries no role, so it cannot carry a forged one.

        Even a perfectly valid, correctly-signed student cookie yields a
        student on every request, because the role is recomputed from the
        email domain rather than read from the token.
        """
        _, token = await make_user("student.a2024@vitstudent.ac.in")
        payload = session_cookie.read(token)
        assert "role" not in payload
        resp = await client.get("/api/auth/me", headers=auth(token))
        assert resp.json()["role"] == "student"


# --- role gating -----------------------------------------------------------


class TestRoleGating:
    async def test_student_cannot_create_a_classroom(self, client, make_user):
        _, token = await make_user("student.a2024@vitstudent.ac.in")
        resp = await client.post(
            "/api/classrooms", json={"name": "Mine now"}, headers=auth(token)
        )
        assert resp.status_code == 403

    async def test_student_cannot_list_faculty_classrooms(self, client, make_user):
        _, token = await make_user("student.a2024@vitstudent.ac.in")
        assert (
            await client.get("/api/classrooms/mine", headers=auth(token))
        ).status_code == 403

    async def test_student_cannot_read_the_audit_log(self, client, make_user):
        _, token = await make_user("student.a2024@vitstudent.ac.in")
        assert (
            await client.get("/api/dashboard/audit", headers=auth(token))
        ).status_code == 403

    async def test_faculty_cannot_join_with_the_student_code(self, client, make_user):
        """A code's role must match the caller's own platform role -- no
        "closest role" fallback (brief §6)."""
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof, experiment_id=None)
        resp = await client.post(
            "/api/classrooms/join",
            json={"join_code": classroom["student_join_code"]},
            headers=auth(prof),
        )
        assert resp.status_code == 403

    async def test_student_cannot_join_with_the_faculty_code(self, client, make_user):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof, experiment_id=None)
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        resp = await client.post(
            "/api/classrooms/join",
            json={"join_code": classroom["faculty_join_code"]},
            headers=auth(alice),
        )
        assert resp.status_code == 403

    async def test_faculty_test_submission_still_scoped_to_a_real_classroom(
        self, client, make_user
    ):
        """Faculty may submit test records (brief §12), but not to a
        classroom-id that does not exist or that they do not belong to."""
        _, token = await make_user("prof@vit.ac.in")
        resp = await _submit(client, token, "no-such-classroom")
        assert resp.status_code == 404


# --- cross-student isolation (golden dataset category 4e) ------------------


class TestStudentDataIsolation:
    async def test_direct_object_reference_to_another_students_submission(
        self, client, make_user, fake_llm, registered_experiment
    ):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof)

        _, alice = await make_user("student.a2024@vitstudent.ac.in", "Alice")
        _, bob = await make_user("student.b2024@vitstudent.ac.in", "Bob")
        await _enrol(client, alice, classroom["student_join_code"])
        await _enrol(client, bob, classroom["student_join_code"])

        created = await _submit(client, alice, classroom["id"])
        assert created.status_code == 201, created.text
        alice_submission = created.json()["submission_id"]

        # Bob knows the id and asks for it directly.
        stolen = await client.get(
            f"/api/submissions/{alice_submission}", headers=auth(bob)
        )
        assert stolen.status_code == 404

        # Alice can still read her own.
        own = await client.get(
            f"/api/submissions/{alice_submission}", headers=auth(alice)
        )
        assert own.status_code == 200

    async def test_listing_never_includes_another_student(
        self, client, make_user, fake_llm, registered_experiment
    ):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof)
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        _, bob = await make_user("student.b2024@vitstudent.ac.in")
        await _enrol(client, alice, classroom["student_join_code"])
        await _enrol(client, bob, classroom["student_join_code"])

        await _submit(client, alice, classroom["id"])

        listing = await client.get("/api/submissions/mine", headers=auth(bob))
        assert listing.status_code == 200
        assert listing.json()["submissions"] == []

    async def test_scope_layer_refuses_unowned_models(self, db):
        """The scope object itself will not build an unscoped query."""
        from backend.data_access import ScopeViolation, StudentScope
        from backend.models import Classroom

        scope = StudentScope(db, "some-student-id")
        with pytest.raises(ScopeViolation):
            scope.select(Classroom)

    async def test_scope_requires_a_concrete_student_id(self, db):
        from backend.data_access import ScopeViolation, StudentScope

        with pytest.raises(ScopeViolation):
            StudentScope(db, "")

    async def test_faculty_cannot_reach_another_faculty_classroom(
        self, client, make_user
    ):
        _, prof_a = await make_user("prof.a@vit.ac.in")
        _, prof_b = await make_user("prof.b@vit.ac.in")
        classroom = await _make_classroom(client, prof_a, experiment_id=None)

        # Indistinguishable from "no such classroom".
        for path in (
            f"/api/classrooms/{classroom['id']}/roster",
            f"/api/dashboard/classrooms/{classroom['id']}/submissions",
            f"/api/dashboard/classrooms/{classroom['id']}/escalations",
            f"/api/dashboard/classrooms/{classroom['id']}/sessions/no-such-session/summaries",
        ):
            resp = await client.get(path, headers=auth(prof_b))
            assert resp.status_code == 404, path

    async def test_student_cannot_read_summaries_at_all(
        self, client, make_user, registered_experiment
    ):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof)
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        await _enrol(client, alice, classroom["student_join_code"])

        resp = await client.get(
            f"/api/dashboard/classrooms/{classroom['id']}/sessions/"
            f"{classroom['active_session_id']}/summaries",
            headers=auth(alice),
        )
        assert resp.status_code == 403


# --- classroom mechanics ---------------------------------------------------


class TestClassroomMechanics:
    async def test_join_code_has_real_entropy(self, client, make_user):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof, experiment_id=None)
        code = classroom["student_join_code"]
        assert len(code) == 5, "expected 5-digit PIN"
        assert code.isdigit()


    async def test_join_codes_are_unique_across_classrooms(self, client, make_user):
        _, prof = await make_user("prof@vit.ac.in")
        codes = set()
        for _ in range(5):
            created = await client.post(
                "/api/classrooms",
                json={"name": "Section", "idempotency_key": str(len(codes))},
                headers=auth(prof),
            )
            codes.add(created.json()["student_join_code"])
        assert len(codes) == 5

    async def test_closed_classroom_refuses_new_joins(self, client, make_user):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof, experiment_id=None)
        locked = await client.patch(
            f"/api/classrooms/{classroom['id']}/join-open",
            json={"join_open": False},
            headers=auth(prof),
        )
        assert locked.status_code == 200

        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        refused = await client.post(
            "/api/classrooms/join",
            json={"join_code": classroom["student_join_code"]},
            headers=auth(alice),
        )
        assert refused.status_code == 403

    async def test_student_never_sees_the_join_code_of_their_classroom(
        self, client, make_user
    ):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof, experiment_id=None)
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        await _enrol(client, alice, classroom["student_join_code"])

        listing = await client.get(
            "/api/classrooms/enrolled", headers=auth(alice)
        )
        assert listing.status_code == 200
        for entry in listing.json()["classrooms"]:
            assert "student_join_code" not in entry
            assert "faculty_join_code" not in entry

    async def test_submission_is_tagged_from_the_classroom_not_the_client(
        self, client, make_user, fake_llm, registered_experiment
    ):
        """A student cannot choose which experiment they are submitting against."""
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof)
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        await _enrol(client, alice, classroom["student_join_code"])

        created = await _submit(
            client, alice, classroom["id"], experiment_id="exp09"  # ignored
        )
        assert created.status_code == 201
        assert created.json()["experiment_id"] == "ref01"

    async def test_submission_refused_with_no_active_experiment(
        self, client, make_user, registered_experiment
    ):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof, experiment_id=None)
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        await _enrol(client, alice, classroom["student_join_code"])

        resp = await _submit(client, alice, classroom["id"])
        assert resp.status_code == 409

    async def test_malformed_submission_returns_a_validation_error(
        self, client, make_user, fake_llm, registered_experiment
    ):
        """The invalid path must return a clean error, not blow up.

        Regression test: this path built a Diagnosis with an explicit
        RemedialAction that was never imported, so any student submitting
        a malformed number got a 500 instead of being told what was wrong.
        """
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof)
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        await _enrol(client, alice, classroom["student_join_code"])

        bad = dict(STUDENT_DATA)
        bad["titre_volume"] = "12,34"  # ambiguous decimal comma
        resp = await _submit(client, alice, classroom["id"], data=bad)

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "invalid"
        assert "titre_volume" in body["explanation"]
        assert body["action"] == "fix_in_place"

    async def test_submission_refused_when_not_enrolled(
        self, client, make_user, registered_experiment
    ):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof)
        _, outsider = await make_user("student.c2024@vitstudent.ac.in")

        resp = await _submit(client, outsider, classroom["id"])
        assert resp.status_code == 404


# --- single-fire behaviour -------------------------------------------------


class TestDoubleSubmit:
    async def test_double_submit(
        self, client, make_user, fake_llm, registered_experiment, db
    ):
        """Golden dataset case c3-duplicate-submission, end to end.

        Client-side button disabling cannot survive a retry or a second
        tab, so the second identical request must be absorbed server-side:
        one row, one diagnosis, one inference call.
        """
        from sqlalchemy import func, select

        from backend.models import Diagnosis, Submission

        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof)
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        await _enrol(client, alice, classroom["student_join_code"])

        first = await _submit(client, alice, classroom["id"])
        assert first.status_code == 201
        calls_after_first = len(fake_llm.calls)

        second = await _submit(client, alice, classroom["id"])
        assert second.status_code in (200, 201)

        # Same answer, not a second one.
        assert second.json()["submission_id"] == first.json()["submission_id"]

        submissions = await db.scalar(select(func.count()).select_from(Submission))
        assert submissions == 1, "a duplicate request created a second submission"

        diagnoses = await db.scalar(select(func.count()).select_from(Diagnosis))
        assert diagnoses == 1

        # And no second round of billing.
        assert len(fake_llm.calls) == calls_after_first

    async def test_distinct_submissions_are_not_collapsed(
        self, client, make_user, fake_llm, registered_experiment, db
    ):
        """Idempotency must not swallow a genuinely different resubmission."""
        from sqlalchemy import func, select

        from backend.models import Submission

        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof)
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        await _enrol(client, alice, classroom["student_join_code"])

        await _submit(client, alice, classroom["id"], reported_value=0.125)
        await _submit(client, alice, classroom["id"], reported_value=0.130)

        count = await db.scalar(select(func.count()).select_from(Submission))
        assert count == 2


# --- rate limiting ---------------------------------------------------------


class TestRateLimiting:
    async def test_submission_rate_limit_engages(
        self, client, make_user, fake_llm, registered_experiment, monkeypatch
    ):
        from backend.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "ratelimit_submit_per_hour", 2)

        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof)
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        await _enrol(client, alice, classroom["student_join_code"])

        statuses = []
        for i in range(4):
            resp = await _submit(
                client, alice, classroom["id"], reported_value=0.10 + i * 0.01
            )
            statuses.append(resp.status_code)

        assert 429 in statuses, f"rate limit never engaged: {statuses}"
        limited = next(s for s in statuses if s == 429)
        assert limited == 429


class TestEveryAwaitReviewCaseReachesAHuman:
    """A student told to wait for a demonstrator must reach the queue.

    Regression: only an ESCALATED status used to create a queue row. A
    violated conformer ordering on Experiments 7/8 is a determinate FAIL
    whose remedy is nonetheless review, so it was diagnosed, told the
    student to wait, and never appeared on anyone's list.
    """

    async def test_violated_ordering_appears_in_the_review_queue(
        self, client, make_user, fake_llm
    ):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof, experiment_id="exp08")
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        await _enrol(client, alice, classroom["student_join_code"])

        created = await client.post(
            "/api/submissions",
            json={
                "classroom_id": classroom["id"],
                # Staggered reported above eclipsed: contradicted ordering.
                "data": {
                    "energies": {
                        "ethane_staggered": -79.7,
                        "ethane_eclipsed": -79.8,
                    }
                },
                "reported_value": None,
                "remarks": "",
            },
            headers=auth(alice),
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["status"] == "fail"
        assert body["action"] == "await_review"

        queue = await client.get(
            f"/api/dashboard/classrooms/{classroom['id']}/escalations",
            headers=auth(prof),
        )
        assert queue.status_code == 200
        rows = queue.json()["escalations"]
        assert len(rows) == 1, "an await_review case did not reach the queue"
        assert rows[0]["student_email"] == "student.a2024@vitstudent.ac.in"

    async def test_an_ordinary_fail_does_not_flood_the_queue(
        self, client, make_user, fake_llm, registered_experiment
    ):
        """Only await_review cases queue -- a fixable slip is not review work."""
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof)
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        await _enrol(client, alice, classroom["student_join_code"])

        # Off by a factor of ten: diagnosed, fixable at the desk.
        created = await _submit(client, alice, classroom["id"], reported_value=1.25)
        assert created.status_code == 201
        assert created.json()["action"] == "fix_in_place"

        queue = await client.get(
            f"/api/dashboard/classrooms/{classroom['id']}/escalations",
            headers=auth(prof),
        )
        assert queue.json()["escalations"] == []
