## Purpose

Runs async post-upload processing: when an image attachment is marked `ready`, a background worker generates a thumbnail and updates the attachment's `status` and `thumbnail_key`. Failed processing is retried 3× with exponential backoff; permanent failures move the attachment to `failed`.

## ADDED Requirements

### Requirement: Thumbnail generation runs async on ready attachments
The system SHALL enqueue a thumbnail-generation job for every `ready` image attachment. The worker SHALL resize the image to a max width of 400 px (preserving aspect ratio) and store the result at `<original_key>.thumb`.

#### Scenario: Image attachment completed
- **WHEN** client calls `POST /api/uploads/{id}/complete` for a JPEG image
- **THEN** worker receives a job within 5 seconds and produces a thumbnail; attachment's `thumbnail_key` is set and `status` becomes `ready`

#### Scenario: Non-image attachment
- **WHEN** the attachment is a video (content_type starts with `video/`)
- **THEN** worker skips thumbnail generation; `thumbnail_key` remains `null`; status remains `ready`

#### Scenario: Already-processed attachment
- **WHEN** worker picks up a job for an attachment that already has a `thumbnail_key`
- **THEN** worker is a no-op (idempotent — protects against duplicate jobs)

### Requirement: Failed processing retries with exponential backoff
The system SHALL retry transient failures up to 3 times with delays 1s, 4s, 16s. On final failure, the system SHALL mark the attachment `failed`.

#### Scenario: Transient failure recovered
- **WHEN** worker tries to fetch the image and gets a 503 from storage on attempt 1
- **THEN** worker retries; if a later retry succeeds, the thumbnail is generated normally

#### Scenario: Permanent failure
- **WHEN** worker's retries all fail (corrupt image, storage permanently unavailable)
- **THEN** attachment's `status` becomes `failed`; `thumbnail_key` is `null`

### Requirement: Attachment status is queryable
The system SHALL expose the current `status` of an attachment via `GET /api/uploads/{attachment_id}`. The `status` field is one of `pending | processing | ready | failed | expired`.

#### Scenario: Status query while processing
- **WHEN** client queries an attachment whose worker is currently generating the thumbnail
- **THEN** response includes `status: "processing"`

#### Scenario: Status query when done
- **WHEN** client queries a fully processed image attachment
- **THEN** response includes `status: "ready"` and a non-null `thumbnail_key`

### Requirement: Processing emits structured log events
The system SHALL emit a `processing_started` and a `processing_completed` (or `processing_failed`) log line for each attachment the worker handles.

#### Scenario: Successful processing
- **WHEN** worker completes a thumbnail
- **THEN** logs include `processing_started attachment=<id>` followed by `processing_completed attachment=<id> key=<thumb_key> duration_ms=<n>`

#### Scenario: Failed processing
- **WHEN** worker's retries are exhausted
- **THEN** logs include `processing_failed attachment=<id> attempts=3 reason=<error>`
