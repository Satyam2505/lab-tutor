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


def cookies_for(token: str) -> dict[str, str]:
    return {session_cookie.COOKIE_NAME: token}


async def _make_classroom(client, faculty_token, experiment_id="ref01"):
    created = await client.post(
        "/api/classrooms",
        json={"name": "Tuesday B1"},
        cookies=cookies_for(faculty_token),
    )
    assert created.status_code == 201, created.text
    classroom = created.json()
    activated = await client.patch(
        f"/api/classrooms/{classroom['id']}/active-experiment",
        json={"experiment_id": experiment_id},
        cookies=cookies_for(faculty_token),
    )
    assert activated.status_code == 200, activated.text
    return classroom


async def _enrol(client, student_token, join_code):
    joined = await client.post(
        "/api/classrooms/join",
        json={"join_code": join_code},
        cookies=cookies_for(student_token),
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
    return await client.post("/api/submissions", json=body, cookies=cookies_for(token))


# --- authentication --------------------------------------------------------


class TestAuthenticationBoundary:
    async def test_unauthenticated_is_rejected(self, client):
        assert (await client.get("/api/auth/me")).status_code == 401

    async def test_garbage_cookie_is_rejected(self, client):
        resp = await client.get("/api/auth/me", cookies=cookies_for("not-a-real-token"))
        assert resp.status_code == 401

    async def test_tampered_cookie_is_rejected(self, client, make_user):
        _, token = await make_user("student.a2024@vitstudent.ac.in")
        # Flip a character in the signature.
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        resp = await client.get("/api/auth/me", cookies=cookies_for(tampered))
        assert resp.status_code == 401

    async def test_signed_in_student_sees_their_own_identity(self, client, make_user):
        user, token = await make_user("student.a2024@vitstudent.ac.in")
        resp = await client.get("/api/auth/me", cookies=cookies_for(token))
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
        resp = await client.get("/api/auth/me", cookies=cookies_for(token))
        assert resp.json()["role"] == "student"


# --- role gating -----------------------------------------------------------


class TestRoleGating:
    async def test_student_cannot_create_a_classroom(self, client, make_user):
        _, token = await make_user("student.a2024@vitstudent.ac.in")
        resp = await client.post(
            "/api/classrooms", json={"name": "Mine now"}, cookies=cookies_for(token)
        )
        assert resp.status_code == 403

    async def test_student_cannot_list_faculty_classrooms(self, client, make_user):
        _, token = await make_user("student.a2024@vitstudent.ac.in")
        assert (
            await client.get("/api/classrooms/mine", cookies=cookies_for(token))
        ).status_code == 403

    async def test_student_cannot_read_the_audit_log(self, client, make_user):
        _, token = await make_user("student.a2024@vitstudent.ac.in")
        assert (
            await client.get("/api/dashboard/audit", cookies=cookies_for(token))
        ).status_code == 403

    async def test_faculty_cannot_join_as_a_student(self, client, make_user):
        _, token = await make_user("prof@vit.ac.in")
        resp = await client.post(
            "/api/classrooms/join",
            json={"join_code": "AAAAA-BBBBB-CCCCC-DDDDD"},
            cookies=cookies_for(token),
        )
        assert resp.status_code == 403

    async def test_faculty_cannot_submit_as_a_student(self, client, make_user):
        _, token = await make_user("prof@vit.ac.in")
        resp = await _submit(client, token, "any-classroom")
        assert resp.status_code == 403


# --- cross-student isolation (golden dataset category 4e) ------------------


class TestStudentDataIsolation:
    async def test_direct_object_reference_to_another_students_submission(
        self, client, make_user, fake_llm, registered_experiment
    ):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof)

        _, alice = await make_user("student.a2024@vitstudent.ac.in", "Alice")
        _, bob = await make_user("student.b2024@vitstudent.ac.in", "Bob")
        await _enrol(client, alice, classroom["join_code"])
        await _enrol(client, bob, classroom["join_code"])

        created = await _submit(client, alice, classroom["id"])
        assert created.status_code == 201, created.text
        alice_submission = created.json()["submission_id"]

        # Bob knows the id and asks for it directly.
        stolen = await client.get(
            f"/api/submissions/{alice_submission}", cookies=cookies_for(bob)
        )
        assert stolen.status_code == 404

        # Alice can still read her own.
        own = await client.get(
            f"/api/submissions/{alice_submission}", cookies=cookies_for(alice)
        )
        assert own.status_code == 200

    async def test_listing_never_includes_another_student(
        self, client, make_user, fake_llm, registered_experiment
    ):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof)
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        _, bob = await make_user("student.b2024@vitstudent.ac.in")
        await _enrol(client, alice, classroom["join_code"])
        await _enrol(client, bob, classroom["join_code"])

        await _submit(client, alice, classroom["id"])

        listing = await client.get("/api/submissions/mine", cookies=cookies_for(bob))
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
            f"/api/dashboard/classrooms/{classroom['id']}/summaries",
        ):
            resp = await client.get(path, cookies=cookies_for(prof_b))
            assert resp.status_code == 404, path

    async def test_student_cannot_read_summaries_at_all(
        self, client, make_user, registered_experiment
    ):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof)
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        await _enrol(client, alice, classroom["join_code"])

        resp = await client.get(
            f"/api/dashboard/classrooms/{classroom['id']}/summaries",
            cookies=cookies_for(alice),
        )
        assert resp.status_code == 403


# --- classroom mechanics ---------------------------------------------------


class TestClassroomMechanics:
    async def test_join_code_has_real_entropy(self, client, make_user):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof, experiment_id=None)
        code = classroom["join_code"]
        alphabet_chars = [c for c in code if c != "-"]
        assert len(alphabet_chars) == 20, "expected 20 code characters"
        # 31-symbol alphabet, 20 characters -> ~99 bits. Well past guessable.
        assert len(set(alphabet_chars)) > 5

    async def test_join_codes_are_unique_across_classrooms(self, client, make_user):
        _, prof = await make_user("prof@vit.ac.in")
        codes = set()
        for _ in range(5):
            created = await client.post(
                "/api/classrooms",
                json={"name": "Section", "idempotency_key": str(len(codes))},
                cookies=cookies_for(prof),
            )
            codes.add(created.json()["join_code"])
        assert len(codes) == 5

    async def test_closed_classroom_refuses_new_joins(self, client, make_user):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof, experiment_id=None)
        locked = await client.patch(
            f"/api/classrooms/{classroom['id']}/join-open",
            json={"join_open": False},
            cookies=cookies_for(prof),
        )
        assert locked.status_code == 200

        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        refused = await client.post(
            "/api/classrooms/join",
            json={"join_code": classroom["join_code"]},
            cookies=cookies_for(alice),
        )
        assert refused.status_code == 403

    async def test_student_never_sees_the_join_code_of_their_classroom(
        self, client, make_user
    ):
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof, experiment_id=None)
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        await _enrol(client, alice, classroom["join_code"])

        listing = await client.get(
            "/api/classrooms/enrolled", cookies=cookies_for(alice)
        )
        assert listing.status_code == 200
        for entry in listing.json()["classrooms"]:
            assert "join_code" not in entry

    async def test_submission_is_tagged_from_the_classroom_not_the_client(
        self, client, make_user, fake_llm, registered_experiment
    ):
        """A student cannot choose which experiment they are submitting against."""
        _, prof = await make_user("prof@vit.ac.in")
        classroom = await _make_classroom(client, prof)
        _, alice = await make_user("student.a2024@vitstudent.ac.in")
        await _enrol(client, alice, classroom["join_code"])

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
        await _enrol(client, alice, classroom["join_code"])

        resp = await _submit(client, alice, classroom["id"])
        assert resp.status_code == 409

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
        await _enrol(client, alice, classroom["join_code"])

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
        await _enrol(client, alice, classroom["join_code"])

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
        await _enrol(client, alice, classroom["join_code"])

        statuses = []
        for i in range(4):
            resp = await _submit(
                client, alice, classroom["id"], reported_value=0.10 + i * 0.01
            )
            statuses.append(resp.status_code)

        assert 429 in statuses, f"rate limit never engaged: {statuses}"
        limited = next(s for s in statuses if s == 429)
        assert limited == 429
