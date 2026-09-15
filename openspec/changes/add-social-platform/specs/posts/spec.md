## Purpose

Lets authenticated users create text posts and retrieve them by id or by author. Posts may reference media attachments (see `media-uploads` capability) but the post itself is just text + author + timestamp. The fan-out of posts to follower timelines is the `feed` capability's responsibility.

## ADDED Requirements

### Requirement: User can create a text post
The system SHALL allow an authenticated user to create a post via `POST /api/posts` with `{text, attachment_ids?}`. `text` MUST be 1–2000 characters after trimming. `attachment_ids` is an optional list of attachment ids previously uploaded via the media-uploads capability.

#### Scenario: Successful post
- **WHEN** authenticated client POSTs `{text: "hello world"}`
- **THEN** system responds `201` with `{id, author_id, text, attachment_ids, created_at}`

#### Scenario: Empty text
- **WHEN** client POSTs `{text: ""}` or `{text: "   "}` (whitespace only)
- **THEN** system responds `422`

#### Scenario: Text too long
- **WHEN** client POSTs text > 2000 characters
- **THEN** system responds `422`

#### Scenario: Attachment from another user
- **WHEN** client POSTs `attachment_ids` referencing an attachment owned by a different user
- **THEN** system responds `403`

#### Scenario: Attachment not in `ready` state
- **WHEN** client POSTs an `attachment_ids` list including an attachment whose status is `pending`, `processing`, or `failed`
- **THEN** system responds `409` with `{"error": "attachment_not_ready"}`

### Requirement: User can retrieve a post by id
The system SHALL allow any client (authenticated or not) to retrieve a single post via `GET /api/posts/{id}`.

#### Scenario: Known post
- **WHEN** client requests `GET /api/posts/42`
- **THEN** system responds `200` with `{id, author_id, text, attachment_ids, created_at, author: {id, display_name}}`

#### Scenario: Unknown post
- **WHEN** client requests an unknown id
- **THEN** system responds `404`

### Requirement: User can list posts by author
The system SHALL allow listing posts by author via `GET /api/users/{user_id}/posts?limit=20&before=<post_id>` with cursor-based pagination.

#### Scenario: First page
- **WHEN** client requests the first page of a user's posts
- **THEN** system responds `200` with `{posts: [...], next_cursor: <id-or-null>}` ordered by `created_at DESC`

#### Scenario: Empty
- **WHEN** user has no posts
- **THEN** system responds `200` with `{posts: [], next_cursor: null}`

### Requirement: Posts cannot be edited or deleted via the API
The system SHALL NOT expose endpoints to edit or delete posts in v1. Posts are immutable once created.

#### Scenario: No edit or delete endpoints
- **WHEN** client attempts `PATCH /api/posts/{id}`, `PUT /api/posts/{id}`, or `DELETE /api/posts/{id}`
- **THEN** system responds `405 Method Not Allowed`
