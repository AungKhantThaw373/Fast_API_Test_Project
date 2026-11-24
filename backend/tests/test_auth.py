from conftest import PASSWORD, login, register


async def test_register_and_me(client):
    response = await register(client, "writer", "writer@example.com")
    assert response.status_code == 201
    assert response.json()["email"] == "writer@example.com"

    assert (await login(client, "writer@example.com")).status_code == 200
    me = await client.get("/me")
    assert me.status_code == 200
    assert me.json()["username"] == "writer"


async def test_login_is_case_insensitive_after_mixed_case_registration(client):
    assert (await register(client, "writer", "User@Example.com")).status_code == 201
    response = await login(client, "user@example.com")
    assert response.status_code == 200


async def test_registering_the_same_email_in_another_case_conflicts(client):
    assert (await register(client, "writer", "User@Example.com")).status_code == 201
    duplicate = await register(client, "second", "USER@example.com")
    assert duplicate.status_code == 409


async def test_wrong_case_and_wrong_password_is_rejected(client):
    assert (await register(client, "writer", "User@Example.com")).status_code == 201
    assert (await login(client, "USER@example.com", "wrong password")).status_code == 401


async def test_logout_clears_the_session(client):
    assert (await register(client, "writer", "writer@example.com")).status_code == 201
    assert (await login(client, "writer@example.com")).status_code == 200
    assert (await client.get("/me")).status_code == 200

    assert (await client.post("/logout")).status_code == 200
    assert (await client.get("/me")).status_code == 401


async def test_short_password_is_rejected(client):
    response = await register(client, "writer", "writer@example.com", password="short")
    assert response.status_code == 422


async def test_unauthenticated_requests_are_rejected(client):
    assert (await client.get("/me")).status_code == 401
    assert (await client.get("/stories")).status_code == 401


async def test_login_does_not_leak_whether_an_account_exists(client):
    assert (await register(client, "writer", "writer@example.com")).status_code == 201
    missing = await login(client, "nobody@example.com", PASSWORD)
    wrong = await login(client, "writer@example.com", "another password")
    assert missing.status_code == wrong.status_code == 401
    assert missing.json()["detail"] == wrong.json()["detail"]
