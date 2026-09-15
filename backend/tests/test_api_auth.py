import pytest


async def test_signup_success(client):
    r = await client.post(
        "/auth/signup",
        json={
            "email": "alice@example.com",
            "password": "CorrectHorse9",
            "display_name": "Alice",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "alice@example.com"
    assert data["user"]["display_name"] == "Alice"
    assert isinstance(data["user"]["id"], int)


async def test_signup_returns_distinct_tokens(client):
    """Access and refresh tokens should be different (different `type` claim)."""
    r = await client.post(
        "/auth/signup",
        json={"email": "alice@example.com", "password": "CorrectHorse9", "display_name": "Alice"},
    )
    data = r.json()
    assert data["access_token"] != data["refresh_token"]


async def test_signup_duplicate_email_returns_409(client):
    await client.post(
        "/auth/signup",
        json={"email": "alice@example.com", "password": "CorrectHorse9", "display_name": "Alice"},
    )
    r = await client.post(
        "/auth/signup",
        json={"email": "alice@example.com", "password": "OtherPass123", "display_name": "Alice2"},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "email_taken"


async def test_signup_weak_password_returns_422(client):
    r = await client.post(
        "/auth/signup",
        json={"email": "bob@example.com", "password": "short", "display_name": "Bob"},
    )
    assert r.status_code == 422


async def test_signup_malformed_email_returns_422(client):
    r = await client.post(
        "/auth/signup",
        json={"email": "not-email", "password": "CorrectHorse9", "display_name": "Bob"},
    )
    assert r.status_code == 422


async def test_login_success(client):
    await client.post(
        "/auth/signup",
        json={"email": "alice@example.com", "password": "CorrectHorse9", "display_name": "Alice"},
    )
    r = await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "CorrectHorse9"},
    )
    assert r.status_code == 200
    assert "access_token" in r.json()


async def test_login_wrong_password_returns_401(client):
    await client.post(
        "/auth/signup",
        json={"email": "alice@example.com", "password": "CorrectHorse9", "display_name": "Alice"},
    )
    r = await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "WrongPassword99"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_credentials"


async def test_login_unknown_email_returns_same_401(client):
    """Don't leak which emails are registered."""
    r = await client.post(
        "/auth/login",
        json={"email": "ghost@example.com", "password": "Anything1234"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_credentials"


async def test_refresh_success(client):
    signup = await client.post(
        "/auth/signup",
        json={"email": "alice@example.com", "password": "CorrectHorse9", "display_name": "Alice"},
    )
    refresh = signup.json()["refresh_token"]
    r = await client.post("/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["refresh_token"] != refresh  # rotated


async def test_refresh_invalid_token_returns_401(client):
    r = await client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert r.status_code == 401


async def test_access_token_cannot_be_used_for_refresh(client):
    """An access token presented to /refresh must be rejected."""
    signup = await client.post(
        "/auth/signup",
        json={"email": "alice@example.com", "password": "CorrectHorse9", "display_name": "Alice"},
    )
    access = signup.json()["access_token"]
    r = await client.post("/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 401