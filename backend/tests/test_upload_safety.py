import pytest

from app.config import settings


def upload(client, filename: str, content: bytes, media_type: str = "application/octet-stream"):
    return client.post(
        "/editing/files",
        files={"file": (filename, content, media_type)},
    )


@pytest.mark.asyncio
async def test_text_upload_download_and_preview_are_safe(user_client):
    created = await upload(user_client, "notes.txt", b"A quiet first scene.")
    assert created.status_code == 201
    body = created.json()
    assert body["media_type"] == "text/plain"

    download = await user_client.get(f"/editing/files/{body['id']}/content")
    assert download.status_code == 200
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff"

    preview = await user_client.get(f"/editing/files/{body['id']}/content?inline=true")
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("text/plain")
    assert preview.headers["content-security-policy"].startswith("sandbox")
    assert preview.headers["x-frame-options"] == "SAMEORIGIN"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("fake.pdf", b"<html><script>alert(1)</script></html>"),
        ("page.txt", b"<!doctype html><html><body>no</body></html>"),
        ("vector.md", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"),
        ("binary.txt", b"hello\x00world"),
        ("fake.docx", b"not a zip"),
        ("fake.doc", b"not an OLE file"),
        ("fake.rtf", b"plain text"),
    ],
)
async def test_uploads_with_wrong_signatures_are_rejected(user_client, filename, content):
    response = await upload(user_client, filename, content)
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_upload_storage_quota_is_enforced(user_client, monkeypatch):
    monkeypatch.setattr(settings, "USER_STORAGE_QUOTA_BYTES", 8)
    response = await upload(user_client, "too-large.txt", b"more than eight bytes")
    assert response.status_code == 413
    assert "storage limit" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_file_count_is_enforced(user_client, monkeypatch):
    monkeypatch.setattr(settings, "USER_FILE_LIMIT", 1)
    assert (await upload(user_client, "one.txt", b"one")).status_code == 201
    second = await upload(user_client, "two.txt", b"two")
    assert second.status_code == 409
    assert "already holds 1 files" in second.json()["detail"]


@pytest.mark.asyncio
async def test_valid_pdf_signature_is_accepted(user_client):
    response = await upload(user_client, "real.pdf", b"%PDF-1.4\n% test\n")
    assert response.status_code == 201
    preview = await user_client.get(f"/editing/files/{response.json()['id']}/content?inline=true")
    assert preview.headers["content-type"].startswith("application/pdf")