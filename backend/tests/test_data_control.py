import io
import json
import zipfile

import pytest
from conftest import PASSWORD, login
from sqlalchemy import select

from app.models.security_models import AuditEvent


async def test_sensitive_actions_are_audited(user_client):
    assert (await user_client.put("/ai-settings", json={"provider": "ollama", "model": "llama3"})).status_code == 200
    story = (await user_client.post("/stories", json={"title": "Audit story"})).json()
    assert (await user_client.delete(f"/stories/{story['id']}")).status_code == 204

    response = await user_client.get("/account/audit")
    assert response.status_code == 200
    actions = [event["action"] for event in response.json()["events"]]
    assert "provider_changed" in actions
    assert "story_trashed" in actions


async def test_export_contains_every_story_wiki_and_markdown(user_client):
    story = (await user_client.post("/stories", json={"title": "The Long Room"})).json()
    chapter = (await user_client.post(
        f"/stories/{story['id']}/chapters",
        json={"title": "First light", "content": "The room was quiet."},
    )).json()
    assert chapter["id"]

    response = await user_client.get("/account/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment;" in response.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert "stillroom-export.json" in names
        assert any(name.startswith("stories/01-") and name.endswith(".md") for name in names)
        manifest = json.loads(archive.read("stillroom-export.json"))
        markdown = archive.read(next(name for name in names if name.startswith("stories/01-"))).decode()
    assert manifest["user"]["email"] == "writer@example.com"
    assert manifest["stories"][0]["story"]["title"] == "The Long Room"
    assert "The room was quiet." in markdown

    audit = (await user_client.get("/account/audit")).json()["events"]
    assert any(event["action"] == "data_export" for event in audit)


@pytest.mark.asyncio
async def test_deleting_an_account_requires_typed_confirmation(user_client):
    wrong = await user_client.request(
        "DELETE",
        "/account",
        json={"password": PASSWORD, "confirmation": "not-the-username"},
    )
    assert wrong.status_code == 400
    missing_password = await user_client.request(
        "DELETE",
        "/account",
        json={"password": "wrong password", "confirmation": "writer"},
    )
    assert missing_password.status_code == 400
    assert (await user_client.get("/me")).status_code == 200


@pytest.mark.asyncio
async def test_deleting_an_account_removes_its_data_and_keeps_an_audit_snapshot(
    user_client, session
):
    story = (await user_client.post("/stories", json={"title": "Doomed story"})).json()
    assert (await user_client.post(
        f"/stories/{story['id']}/chapters",
        json={"title": "One", "content": "text"},
    )).status_code == 201

    response = await user_client.request(
        "DELETE",
        "/account",
        json={"password": PASSWORD, "confirmation": "writer"},
    )
    assert response.status_code == 200
    assert (await user_client.get("/me")).status_code == 401
    assert (await login(user_client, "writer@example.com")).status_code == 401

    event = await session.scalar(
        select(AuditEvent).where(AuditEvent.action == "account_deleted")
    )
    assert event is not None
    assert event.user_id is None
    assert event.email == ""