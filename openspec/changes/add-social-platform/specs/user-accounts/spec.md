## Purpose

Lets users register with the platform, log in, and obtain a short-lived JWT access token plus a long-lived refresh token. Owns the auth boundary — every authenticated endpoint validates the bearer token against this capability's contract.

## ADDED Requirements

### Requirement: User can sign up
The system SHALL allow new users to register with `POST /auth/signup`. The system SHALL reject duplicate emails with 409, weak passwords with 422, malformed emails with 422, and SHALL store passwords using bcrypt (cost factor ≥ 12).

#### Scenario: Successful signup
- **WHEN** client POSTs `{email: "alice@example.com", password: "CorrectHorse9", display_name: "Alice"}`
- **THEN** system responds `201` with `{user_id, email, display_name, created_at}` and stores the password hash

#### Scenario: Duplicate email
- **WHEN** client POSTs with an email already registered
- **THEN** system responds `409` with `{"error": "email_taken"}`

#### Scenario: Weak password
- **WHEN** client POSTs with a password shorter than 8 characters
- **THEN** system responds `422` with a validation error

#### Scenario: Malformed email
- **WHEN** client POSTs with `email: "not-an-email"`
- **THEN** system responds `422` with a validation error

### Requirement: User can log in
The system SHALL authenticate users with `POST /auth/login`. On success the system SHALL issue a JWT access token (TTL 15 minutes) and a refresh token (TTL 7 days).

#### Scenario: Successful login
- **WHEN** client POSTs `{email, password}` matching a stored user
- **THEN** system responds `200` with `{access_token, refresh_token, user: {id, email, display_name}}`

#### Scenario: Wrong password
- **WHEN** client POSTs with a correct email but wrong password
- **THEN** system responds `401` with `{"error": "invalid_credentials"}`

#### Scenario: Unknown email
- **WHEN** client POSTs with an email that does not exist
- **THEN** system responds `401` with the same `invalid_credentials` error (do not leak which emails are registered)

### Requirement: Access token can be refreshed
The system SHALL accept a refresh token at `POST /auth/refresh` and issue a new access + refresh token pair if the refresh token is valid and not revoked.

#### Scenario: Valid refresh
- **WHEN** client POSTs a valid, unexpired, unrevoked refresh token
- **THEN** system responds `200` with a new `{access_token, refresh_token}` (rotated)

#### Scenario: Expired or revoked refresh
- **WHEN** client POSTs an invalid, expired, or revoked refresh token
- **THEN** system responds `401`

### Requirement: Authenticated endpoints require a valid token
Every endpoint other than `/auth/*`, `/health`, and any public read endpoint SHALL require a valid JWT in the `Authorization: Bearer ...` header. Invalid or missing tokens MUST be rejected with 401.

#### Scenario: Valid token
- **WHEN** request includes `Authorization: Bearer <valid-jwt>`
- **THEN** request is processed as the authenticated user

#### Scenario: Missing token
- **WHEN** request omits the Authorization header on a protected endpoint
- **THEN** system responds `401`

#### Scenario: Expired token
- **WHEN** request includes an expired JWT
- **THEN** system responds `401`
