## Purpose

Lets two users exchange 1-on-1 direct messages in real time. The client opens a WebSocket connection; messages typed in the browser reach the recipient's open session within ~200ms regardless of which API server instance they're connected to. Achieved by routing every send through Redis pub/sub so any worker can deliver any message.

## ADDED Requirements

### Requirement: User can list their chat rooms
The system SHALL allow an authenticated user to list their chat rooms via `GET /api/chats`. A chat room is created lazily when a user sends or receives their first message to another user.

#### Scenario: User with chats
- **WHEN** user A has chats with B and C
- **THEN** system responds `200` with `{chats: [{chat_id, peer: {id, display_name}, last_message: {id, text, sender_id, created_at}, unread: N}, ...]}`

#### Scenario: No chats
- **WHEN** user has no chat history
- **THEN** system responds `200` with `{chats: []}`

### Requirement: User can fetch message history
The system SHALL return messages in a chat via `GET /api/chats/{chat_id}/messages?limit=50&before=<msg_id>` for cursor-based pagination.

#### Scenario: Participant fetches history
- **WHEN** authenticated user is a participant in the chat
- **THEN** system responds `200` with `{messages: [{id, sender_id, text, created_at, attachment_ids?}, ...]}` ordered by `created_at DESC`

#### Scenario: Non-participant fetches history
- **WHEN** user is not a participant in the chat
- **THEN** system responds `403`

### Requirement: User can send a message via WebSocket
The system SHALL accept a WebSocket message of the form `{"type": "send", "chat_id": "<id>", "text": "<text>"}` from an authenticated connection, persist the message, and broadcast it to all currently-connected participants of that chat.

#### Scenario: Both users connected on the same worker
- **WHEN** sender A sends a message and recipient B has an open WebSocket on the same worker
- **THEN** B's WebSocket receives `{"type": "message", "chat_id": "<id>", "message": {id, sender_id, text, created_at}}` within 200ms

#### Scenario: Users connected on different workers
- **WHEN** sender A sends a message and recipient B is connected on a different worker
- **THEN** B's WebSocket still receives the message within 200ms (delivered via Redis pub/sub)

#### Scenario: Recipient is offline
- **WHEN** sender A sends a message and recipient B is not connected
- **THEN** message is persisted to Postgres; B sees it on next `GET /api/chats/{chat_id}/messages`

### Requirement: WebSocket connection requires authentication
The system SHALL reject WebSocket connections without a valid JWT in the query string `?token=...`.

#### Scenario: Authenticated connection
- **WHEN** client opens `wss://api/chats/ws?token=<valid-jwt>`
- **THEN** connection is accepted and `{"type": "ready"}` is sent

#### Scenario: Unauthenticated connection
- **WHEN** client opens without `?token=` or with an invalid token
- **THEN** connection is closed with code `4401`

### Requirement: Chat messages persist in Postgres
The system SHALL persist every sent message to the `messages` table before broadcasting, so message history is durable across reconnects.

#### Scenario: Sender with successful broadcast
- **WHEN** sender A sends a message
- **THEN** a row appears in `messages` with the same id and content; all currently-connected participants receive it via WebSocket

### Requirement: Sending a message to a non-existent chat creates the chat lazily
The system SHALL create a new chat room if the sender's `chat_id` does not exist AND the recipient can be inferred from the message.

#### Scenario: First message to a new peer
- **WHEN** sender A sends `{"type": "send", "to_user_id": "B", "text": "hi"}` and no chat exists between A and B
- **THEN** system creates a new chat with A and B as participants, persists the message, and broadcasts to B if connected
