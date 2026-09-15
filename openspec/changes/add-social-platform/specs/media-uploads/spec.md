## Purpose

Lets users upload media (images primarily, optionally video) that can then be attached to posts or chat messages. The upload goes directly from the client to object storage via a presigned URL — the API server never sees the bytes. This is the standard pattern for production social apps because the API server would otherwise be a bottleneck for large files and a memory-pressure risk.

## ADDED Requirements

### Requirement: User can request a presigned upload URL
The system SHALL allow an authenticated user to request a presigned upload URL via `POST /api/uploads` with `{content_type, size_bytes}`.

#### Scenario: Successful URL issued
- **WHEN** authenticated client POSTs `{content_type: "image/jpeg", size_bytes: 1048576}`
- **THEN** system responds `201` with `{upload_url, attachment_id, expires_at, storage_key}` where `upload_url` is a presigned PUT URL valid for 15 minutes

#### Scenario: Disallowed content type
- **WHEN** client POSTs `content_type: "application/x-msdownload"`
- **THEN** system responds `422` with `{"error": "unsupported_content_type"}` (only `image/*` and `video/*` allowed in v1)

#### Scenario: File too large
- **WHEN** client POSTs `size_bytes > 50_000_000` (50 MB)
- **THEN** system responds `422` with `{"error": "file_too_large"}`

### Requirement: Client uploads directly to object storage
The system SHALL issue a presigned URL that accepts a PUT request with the file content. The URL SHALL embed the content type and expiry.

#### Scenario: Successful direct upload
- **WHEN** client PUTs file content to the presigned URL with the matching content type
- **THEN** object storage accepts the upload; the object exists at the storage key

#### Scenario: Upload to URL after expiry
- **WHEN** client PUTs to the URL more than 15 minutes after issuance
- **THEN** object storage rejects with 403 (signature expired)

### Requirement: User can mark an upload as completed
The system SHALL accept `POST /api/uploads/{attachment_id}/complete` to mark the upload as finalized and ready to be referenced. The system SHALL verify the object exists in storage before transitioning the attachment to `ready` state and enqueueing media-processing.

#### Scenario: Successful completion
- **WHEN** client POSTs `/complete` and the object exists in storage with size > 0
- **THEN** system responds `200` with `{attachment_id, status: "ready"}` and the attachment can now be referenced by posts or chat messages

#### Scenario: Object missing in storage
- **WHEN** client POSTs `/complete` but the object does not exist in storage
- **THEN** system responds `409` with `{"error": "object_not_found"}`

#### Scenario: Empty object in storage
- **WHEN** client POSTs `/complete` but the stored object is 0 bytes
- **THEN** system responds `409` with `{"error": "object_empty"}`

### Requirement: Attachments are isolated to the owner
The system SHALL scope each attachment to its creating user. Other users SHALL NOT be able to read the object or reference it.

#### Scenario: Owner reads own attachment
- **WHEN** the owner requests `GET /api/uploads/{attachment_id}`
- **THEN** system responds `200` with `{attachment_id, content_type, size_bytes, status, storage_key, thumbnail_key?}`

#### Scenario: Non-owner reads attachment
- **WHEN** another user requests the same attachment
- **THEN** system responds `404` (do not leak existence)

### Requirement: Failed or abandoned uploads expire
The system SHALL mark attachments as `expired` if `complete` is not called within 1 hour of URL issuance. An expired attachment SHALL be eligible for garbage collection.

#### Scenario: Abandoned upload
- **WHEN** more than 1 hour passes since URL issuance and `complete` was not called
- **THEN** system marks the attachment `expired`; the object (if any) becomes eligible for GC

#### Scenario: Read an expired attachment
- **WHEN** owner requests an expired attachment
- **THEN** system responds `200` with `status: "expired"`
