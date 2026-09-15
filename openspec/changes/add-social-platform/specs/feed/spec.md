## Purpose

Lets a user see posts from people they follow, in reverse-chronological order, with sub-100ms read latency. Achieved via **fan-out on write**: when a post is created, it's appended to every follower's personal timeline in Postgres (durable) and in the Redis feed cache (fast reads). The feed read is then an O(1) range query against the timeline.

## ADDED Requirements

### Requirement: User can follow another user
The system SHALL allow an authenticated user to follow another user via `POST /api/users/{user_id}/follow`.

#### Scenario: Successful follow
- **WHEN** authenticated user A POSTs `/api/users/B/follow`
- **THEN** system responds `201` with `{follower_id: A, followee_id: B, created_at}` and B's future posts appear in A's feed

#### Scenario: Self-follow
- **WHEN** user A POSTs `/api/users/A/follow`
- **THEN** system responds `400`

#### Scenario: Already following
- **WHEN** user A POSTs `/api/users/B/follow` when already following B
- **THEN** system responds `409` with `{"error": "already_following"}`

### Requirement: User can unfollow another user
The system SHALL allow `DELETE /api/users/{user_id}/follow`.

#### Scenario: Successful unfollow
- **WHEN** user A DELETEs `/api/users/B/follow`
- **THEN** system responds `204`; B's new posts no longer appear in A's feed

#### Scenario: Not following
- **WHEN** user A DELETEs `/api/users/B/follow` and was not following B
- **THEN** system responds `404`

### Requirement: Fan-out on write populates follower timelines
When a post is created, the system SHALL append the post id to each follower's timeline in Postgres AND in the Redis feed cache.

#### Scenario: Post with 100 followers
- **WHEN** user B creates a post and has 100 followers
- **THEN** system appends the post id to all 100 timelines (Postgres + Redis); the fan-out completes within 5 seconds

#### Scenario: User with no followers
- **WHEN** user B creates a post and has 0 followers
- **THEN** system does not perform fan-out; the post exists in `posts` but no timeline rows are created

#### Scenario: Fan-out runs async
- **WHEN** user B creates a post
- **THEN** the `POST /api/posts` request returns `201` BEFORE fan-out completes (fan-out is enqueued + processed by a worker)

### Requirement: User can read their own feed
The system SHALL serve `GET /api/feed?limit=20&before=<post_id>` returning posts from the user's timeline in reverse-chronological order, hydrated with full post + author + attachment info.

#### Scenario: Populated feed
- **WHEN** authenticated user requests their feed with timeline entries
- **THEN** system responds `200` with `{posts: [{id, author, text, attachments, created_at}, ...], next_cursor: <id-or-null>}`

#### Scenario: Empty feed
- **WHEN** user follows no one
- **THEN** system responds `200` with `{posts: [], next_cursor: null}`

### Requirement: Feed attachments include presigned download URLs
The feed endpoint SHALL return each attachment with a presigned GET URL valid for 15 minutes.

#### Scenario: Post with image attachment in feed
- **WHEN** feed includes a post whose attachment is `ready`
- **THEN** response `posts[i].attachments[j]` includes `{id, content_type, url: <presigned-download-url>, thumbnail_url: <presigned-thumb-url>}`

#### Scenario: Post with non-image attachment
- **WHEN** feed includes a post whose attachment is a video (no thumbnail)
- **THEN** `thumbnail_url` is `null`; `url` is the presigned video URL
