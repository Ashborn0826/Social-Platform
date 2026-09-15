import pytest


async def _signup_and_token(client, email: str = "alice@example.com", password: str = "CorrectHorse9") -> str:
    r = await client.post(
        "/auth/signup",
        json={"email": email, "password": password, "display_name": "Alice"},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_create_post_requires_auth(client):
    r = await client.post("/api/posts", json={"text": "hello"})
    assert r.status_code == 401


async def test_create_post_invalid_token_returns_401(client):
    r = await client.post(
        "/api/posts",
        json={"text": "hello"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 401


async def test_create_post_success(client):
    token = await _signup_and_token(client)
    r = await client.post(
        "/api/posts",
        json={"text": "hello world"},
        headers=_auth(token),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["text"] == "hello world"
    assert data["author_id"] >= 1
    assert data["author"] is not None
    assert data["author"]["email"] == "alice@example.com"


async def test_create_post_empty_text_rejected(client):
    token = await _signup_and_token(client)
    r = await client.post(
        "/api/posts",
        json={"text": "   "},
        headers=_auth(token),
    )
    assert r.status_code == 422


async def test_create_post_too_long_rejected(client):
    token = await _signup_and_token(client)
    r = await client.post(
        "/api/posts",
        json={"text": "x" * 2001},
        headers=_auth(token),
    )
    assert r.status_code == 422


async def test_create_post_text_is_trimmed(client):
    """Leading/trailing whitespace is stripped; internal whitespace preserved."""
    token = await _signup_and_token(client)
    r = await client.post(
        "/api/posts",
        json={"text": "  hello   world  "},
        headers=_auth(token),
    )
    assert r.status_code == 201
    assert r.json()["text"] == "hello   world"


async def test_get_post_success(client):
    token = await _signup_and_token(client)
    create = await client.post(
        "/api/posts", json={"text": "hello"}, headers=_auth(token)
    )
    post_id = create.json()["id"]
    r = await client.get(f"/api/posts/{post_id}")
    assert r.status_code == 200
    assert r.json()["text"] == "hello"
    assert r.json()["author"] is not None


async def test_get_post_unknown_returns_404(client):
    r = await client.get("/api/posts/99999")
    assert r.status_code == 404


async def test_list_user_posts_empty(client):
    token = await _signup_and_token(client)
    me = await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "CorrectHorse9"},
    )
    user_id = me.json()["user"]["id"]
    r = await client.get(f"/api/users/{user_id}/posts")
    assert r.status_code == 200
    assert r.json() == {"posts": [], "next_cursor": None}


async def test_list_user_posts_returns_in_desc_order(client):
    token = await _signup_and_token(client)
    for i in range(3):
        await client.post(
            "/api/posts",
            json={"text": f"post {i}"},
            headers=_auth(token),
        )
    me = await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "CorrectHorse9"},
    )
    user_id = me.json()["user"]["id"]

    r = await client.get(f"/api/users/{user_id}/posts")
    data = r.json()
    assert len(data["posts"]) == 3
    # Newest first: post 2, post 1, post 0
    assert data["posts"][0]["text"] == "post 2"
    assert data["posts"][2]["text"] == "post 0"


async def test_list_user_posts_pagination_no_overlap(client):
    token = await _signup_and_token(client)
    for i in range(5):
        await client.post(
            "/api/posts",
            json={"text": f"post {i}"},
            headers=_auth(token),
        )
    me = await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "CorrectHorse9"},
    )
    user_id = me.json()["user"]["id"]

    r = await client.get(f"/api/users/{user_id}/posts?limit=2")
    data = r.json()
    assert len(data["posts"]) == 2
    assert data["next_cursor"] is not None

    r2 = await client.get(
        f"/api/users/{user_id}/posts?limit=2&before={data['next_cursor']}"
    )
    data2 = r2.json()
    assert len(data2["posts"]) == 2

    page1_ids = {p["id"] for p in data["posts"]}
    page2_ids = {p["id"] for p in data2["posts"]}
    assert page1_ids.isdisjoint(page2_ids)


async def test_list_user_posts_last_page_has_null_cursor(client):
    token = await _signup_and_token(client)
    for i in range(2):
        await client.post(
            "/api/posts",
            json={"text": f"post {i}"},
            headers=_auth(token),
        )
    me = await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "CorrectHorse9"},
    )
    user_id = me.json()["user"]["id"]

    r = await client.get(f"/api/users/{user_id}/posts?limit=10")
    assert r.json()["next_cursor"] is None


async def test_list_user_posts_unknown_user_returns_404(client):
    r = await client.get("/api/users/99999/posts")
    assert r.status_code == 404