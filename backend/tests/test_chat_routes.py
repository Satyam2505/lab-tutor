"""Unified Chat routes tests: /api/chat/threads and /api/chat/messages.
"""

from __future__ import annotations

import pytest

from backend.auth import session as session_cookie

pytestmark = pytest.mark.asyncio


def auth(token: str) -> dict[str, str]:
    return {"Cookie": f"{session_cookie.COOKIE_NAME}={token}"}


async def _classroom_with_active_session(
    client, prof_token: str, experiment_id: str = "exp01"
) -> tuple[str, str, str]:
    created = await client.post(
        "/api/classrooms", json={"name": "Chat Classroom"}, headers=auth(prof_token)
    )
    classroom_id = created.json()["id"]
    student_code = created.json()["student_join_code"]
    started = await client.post(
        f"/api/classrooms/{classroom_id}/sessions/start",
        json={"experiment_id": experiment_id},
        headers=auth(prof_token),
    )
    assert started.status_code == 201
    return classroom_id, student_code, started.json()["session_id"]


class TestChatThreads:
    async def test_thread_lifecycle(self, client, make_user):
        _, prof = await make_user("prof.chat@vit.ac.in")
        classroom_id, student_code, _ = await _classroom_with_active_session(client, prof, "exp01")
        _, student = await make_user("student.chat@vitstudent.ac.in")
        await client.post(
            "/api/classrooms/join", json={"join_code": student_code}, headers=auth(student)
        )

        # 1. Create thread
        created = await client.post(
            "/api/chat/threads",
            json={"classroom_id": classroom_id, "experiment_id": "exp01", "title": "My first chat"},
            headers=auth(student),
        )
        assert created.status_code == 201
        thread_id = created.json()["id"]
        assert created.json()["title"] == "My first chat"

        # 2. List threads
        listed = await client.get(
            f"/api/chat/threads?classroom_id={classroom_id}&experiment_id=exp01",
            headers=auth(student),
        )
        assert listed.status_code == 200
        threads = listed.json()["threads"]
        assert any(t["id"] == thread_id for t in threads)

        # 3. Rename thread
        renamed = await client.patch(
            f"/api/chat/threads/{thread_id}",
            json={"title": "Renamed Chat Title"},
            headers=auth(student),
        )
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "Renamed Chat Title"

        # 4. Delete thread
        deleted = await client.delete(
            f"/api/chat/threads/{thread_id}",
            headers=auth(student),
        )
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True

    async def test_send_message_in_chat(self, client, make_user):
        _, prof = await make_user("prof.chat2@vit.ac.in")
        classroom_id, student_code, _ = await _classroom_with_active_session(client, prof, "exp01")
        _, student = await make_user("student.chat2@vitstudent.ac.in")
        await client.post(
            "/api/classrooms/join", json={"join_code": student_code}, headers=auth(student)
        )

        # Send message
        resp = await client.post(
            "/api/chat/messages",
            json={
                "classroom_id": classroom_id,
                "experiment_id": "exp01",
                "message": "What is the principle of EMF measurement?",
            },
            headers=auth(student),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "thread_id" in data
        assert "message" in data
        assert data["message"]["author"] == "tutor"
        assert "content" in data["message"]

        # Fetch messages for thread
        thread_id = data["thread_id"]
        msgs_resp = await client.get(
            f"/api/chat/threads/{thread_id}/messages",
            headers=auth(student),
        )
        assert msgs_resp.status_code == 200
        msgs = msgs_resp.json()["messages"]
        assert len(msgs) == 2  # user + tutor
        assert msgs[0]["author"] == "student"
        assert msgs[1]["author"] == "tutor"

    async def test_diagnostic_message_in_chat(self, client, make_user):
        _, prof = await make_user("prof.chat3@vit.ac.in")
        classroom_id, student_code, _ = await _classroom_with_active_session(client, prof, "exp01")
        _, student = await make_user("student.chat3@vitstudent.ac.in")
        await client.post(
            "/api/classrooms/join", json={"join_code": student_code}, headers=auth(student)
        )

        # Send diagnostic readings message with valid exp01 fields
        resp = await client.post(
            "/api/chat/messages",
            json={
                "classroom_id": classroom_id,
                "experiment_id": "exp01",
                "message": "Here are my readings: ecell=1.1, reported_value=-212.3",
            },
            headers=auth(student),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"]["kind"] == "diagnostic"
        assert "metadata" in data["message"]
        assert "status" in data["message"]["metadata"]

    async def test_step_calculation_guidance_in_chat(self, client, make_user):
        _, prof = await make_user("prof.chat4@vit.ac.in")
        classroom_id, student_code, _ = await _classroom_with_active_session(client, prof, "exp01")
        _, student = await make_user("student.chat4@vitstudent.ac.in")
        await client.post(
            "/api/classrooms/join", json={"join_code": student_code}, headers=auth(student)
        )

        resp = await client.post(
            "/api/chat/messages",
            json={
                "classroom_id": classroom_id,
                "experiment_id": "exp01",
                "message": "Can you guide me through step 1 calculation?",
            },
            headers=auth(student),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"]["kind"] in ("qa", "socratic")
        meta = data["message"]["metadata"]
        assert meta["type"] == "socratic"
        assert meta["prompt"] is not None
        assert meta["current_step"] is not None
        assert meta["total_steps"] == 2
        assert "could not find enough" not in data["message"]["content"]

    async def test_exp02_socratic_and_diagnostic_flow(self, client, make_user):
        _, prof = await make_user("prof.exp02@vit.ac.in")
        classroom_id, student_code, _ = await _classroom_with_active_session(client, prof, "exp02")
        _, student = await make_user("student.exp02@vitstudent.ac.in")
        await client.post(
            "/api/classrooms/join", json={"join_code": student_code}, headers=auth(student)
        )

        # 1. Socratic flow: calculation guidance question
        resp_qa = await client.post(
            "/api/chat/messages",
            json={
                "classroom_id": classroom_id,
                "experiment_id": "exp02",
                "message": "Can you guide me through step 1 calculation for rate constant k1 prime?",
            },
            headers=auth(student),
        )
        assert resp_qa.status_code == 200
        data_qa = resp_qa.json()
        assert data_qa["message"]["kind"] in ("qa", "socratic")
        meta_qa = data_qa["message"]["metadata"]
        assert meta_qa["type"] == "socratic"
        assert meta_qa["current_step"] is not None
        assert meta_qa["total_steps"] == 2
        assert meta_qa["prompt"] is not None

        # 2. Diagnostic flow: numeric readings submission
        resp_diag = await client.post(
            "/api/chat/messages",
            json={
                "classroom_id": classroom_id,
                "experiment_id": "exp02",
                "message": "time_min: 0, 10, 20, 30, titre_volume_ml: 10.0, 15.0, 18.0, 20.0, titre_volume_at_completion_ml: 30.0, reported_value: 0.02",
            },
            headers=auth(student),
        )
        assert resp_diag.status_code == 200
        data_diag = resp_diag.json()
        assert data_diag["message"]["kind"] in ("diagnostic", "socratic")
        assert "passed" in data_diag["message"]["metadata"] or "status" in data_diag["message"]["metadata"]

    async def test_exp03_socratic_and_diagnostic_flow(self, client, make_user):
        _, prof = await make_user("prof.exp03@vit.ac.in")
        classroom_id, student_code, _ = await _classroom_with_active_session(client, prof, "exp03")
        _, student = await make_user("student.exp03@vitstudent.ac.in")
        await client.post(
            "/api/classrooms/join", json={"join_code": student_code}, headers=auth(student)
        )

        # 1. Socratic flow
        resp_qa = await client.post(
            "/api/chat/messages",
            json={
                "classroom_id": classroom_id,
                "experiment_id": "exp03",
                "message": "Can you guide me through step 1 calculation for unknown concentration?",
            },
            headers=auth(student),
        )
        assert resp_qa.status_code == 200
        data_qa = resp_qa.json()
        assert data_qa["message"]["kind"] in ("qa", "socratic")
        meta_qa = data_qa["message"]["metadata"]
        assert meta_qa["type"] == "socratic"
        assert meta_qa["current_step"] is not None
        assert meta_qa["total_steps"] == 2
        assert meta_qa["prompt"] is not None

        # 2. Diagnostic flow
        resp_diag = await client.post(
            "/api/chat/messages",
            json={
                "classroom_id": classroom_id,
                "experiment_id": "exp03",
                "message": "standard_conc_ppm: 2, 4, 6, 8, standard_absorbance: 0.1, 0.2, 0.3, 0.4, unknown_absorbance: 0.25, reported_value: 5.0",
            },
            headers=auth(student),
        )
        assert resp_diag.status_code == 200
        data_diag = resp_diag.json()
        assert data_diag["message"]["kind"] in ("diagnostic", "socratic")
        assert "passed" in data_diag["message"]["metadata"] or "status" in data_diag["message"]["metadata"]

    async def test_exp07_socratic_and_diagnostic_flow(self, client, make_user):
        _, prof = await make_user("prof.exp07@vit.ac.in")
        classroom_id, student_code, _ = await _classroom_with_active_session(client, prof, "exp07")
        _, student = await make_user("student.exp07@vitstudent.ac.in")
        await client.post(
            "/api/classrooms/join", json={"join_code": student_code}, headers=auth(student)
        )

        # 1. Socratic flow
        resp_qa = await client.post(
            "/api/chat/messages",
            json={
                "classroom_id": classroom_id,
                "experiment_id": "exp07",
                "message": "Can you guide me through step 1 calculation for HOMO and LUMO energies?",
            },
            headers=auth(student),
        )
        assert resp_qa.status_code == 200
        data_qa = resp_qa.json()
        assert data_qa["message"]["kind"] in ("qa", "socratic")
        meta_qa = data_qa["message"]["metadata"]
        assert meta_qa["type"] == "socratic"
        assert meta_qa["current_step"] is not None
        assert meta_qa["total_steps"] == 2
        assert meta_qa["prompt"] is not None

        # 2. Diagnostic flow
        resp_diag = await client.post(
            "/api/chat/messages",
            json={
                "classroom_id": classroom_id,
                "experiment_id": "exp07",
                "message": "energy_before: -40.5, energy_after: -40.52, homo_energy: -0.25, lumo_energy: 0.05",
            },
            headers=auth(student),
        )
        assert resp_diag.status_code == 200
        data_diag = resp_diag.json()
        assert data_diag["message"]["kind"] in ("diagnostic", "socratic")
        assert "passed" in data_diag["message"]["metadata"] or "status" in data_diag["message"]["metadata"]

    async def test_exp08_socratic_and_diagnostic_flow(self, client, make_user):
        _, prof = await make_user("prof.exp08@vit.ac.in")
        classroom_id, student_code, _ = await _classroom_with_active_session(client, prof, "exp08")
        _, student = await make_user("student.exp08@vitstudent.ac.in")
        await client.post(
            "/api/classrooms/join", json={"join_code": student_code}, headers=auth(student)
        )

        # 1. Socratic flow
        resp_qa = await client.post(
            "/api/chat/messages",
            json={
                "classroom_id": classroom_id,
                "experiment_id": "exp08",
                "message": "Can you guide me through step 3 calculation for cyclohexane conformer energies?",
            },
            headers=auth(student),
        )
        assert resp_qa.status_code == 200
        data_qa = resp_qa.json()
        assert data_qa["message"]["kind"] in ("qa", "socratic")
        meta_qa = data_qa["message"]["metadata"]
        assert meta_qa["type"] == "socratic"
        assert meta_qa["current_step"] is not None
        assert meta_qa["total_steps"] == 4
        assert meta_qa["prompt"] is not None

        # 2. Diagnostic flow
        resp_diag = await client.post(
            "/api/chat/messages",
            json={
                "classroom_id": classroom_id,
                "experiment_id": "exp08",
                "message": "ethane_staggered: -79.8, ethane_eclipsed: -79.795, cyclohexane_chair: -235.5, cyclohexane_boat: -235.48",
            },
            headers=auth(student),
        )
        assert resp_diag.status_code == 200
        data_diag = resp_diag.json()
        assert data_diag["message"]["kind"] in ("diagnostic", "socratic")
        assert "passed" in data_diag["message"]["metadata"] or "status" in data_diag["message"]["metadata"]

