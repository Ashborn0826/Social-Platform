const TOKEN_KEY = 'access_token'
const USER_ID_KEY = 'user_id'
const DISPLAY_NAME_KEY = 'display_name'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
export function getUserId(): number | null {
  const v = localStorage.getItem(USER_ID_KEY)
  return v ? Number(v) : null
}
export function getDisplayName(): string | null {
  return localStorage.getItem(DISPLAY_NAME_KEY)
}
export function setAuth(token: string, userId: number, displayName: string) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_ID_KEY, String(userId))
  localStorage.setItem(DISPLAY_NAME_KEY, displayName)
}
export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_ID_KEY)
  localStorage.removeItem(DISPLAY_NAME_KEY)
}

export interface User {
  id: number
  email: string
  display_name: string
  created_at: string
}

export interface Attachment {
  id: number
  content_type: string
  url: string
  thumbnail_url: string | null
}

export interface Post {
  id: number
  text: string
  created_at: string
  author: { id: number; display_name: string }
  attachments: Attachment[]
}

export interface Chat {
  chat_id: number
  peer: { id: number; display_name: string }
  last_message: { id: number; sender_id: number; text: string; created_at: string } | null
}

export interface Message {
  id: number
  chat_id: number
  sender_id: number
  text: string
  created_at: string
}

export interface AttachmentMeta {
  id: number
  content_type: string
  size_bytes: number
  status: string
  thumbnail_key: string | null
  created_at: string
}

async function authFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken()
  const headers = new Headers(init.headers || {})
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (
    !headers.has('Content-Type') &&
    init.body &&
    typeof init.body === 'string'
  ) {
    headers.set('Content-Type', 'application/json')
  }
  return fetch(url, { ...init, headers })
}

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, body: unknown) {
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : JSON.stringify(body)
    super(`HTTP ${status}: ${detail}`)
    this.status = status
    this.detail = body
  }
}

async function handle<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let body: unknown = null
    try {
      body = await r.json()
    } catch {
      // ignore non-JSON bodies
    }
    throw new ApiError(r.status, body)
  }
  return (await r.json()) as T
}

export const api = {
  // Auth
  async signup(email: string, password: string, displayName: string) {
    const r = await fetch('/api/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, display_name: displayName }),
    })
    return handle<{ access_token: string; refresh_token: string; user: User }>(r)
  },
  async login(email: string, password: string) {
    const r = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    return handle<{ access_token: string; refresh_token: string; user: User }>(r)
  },
  // Posts
  async createPost(text: string, attachmentIds: number[] = []) {
    const r = await authFetch('/api/posts', {
      method: 'POST',
      body: JSON.stringify({ text, attachment_ids: attachmentIds }),
    })
    return handle<Post>(r)
  },
  async getPost(id: number) {
    return handle<Post>(await authFetch(`/api/posts/${id}`))
  },
  async getUserPosts(userId: number, limit = 20, before?: number) {
    const params = new URLSearchParams({ limit: String(limit) })
    if (before) params.set('before', String(before))
    return handle<{ posts: Post[]; next_cursor: number | null }>(
      await authFetch(`/api/users/${userId}/posts?${params}`)
    )
  },
  async getFeed(limit = 20, before?: number) {
    const params = new URLSearchParams({ limit: String(limit) })
    if (before) params.set('before', String(before))
    return handle<{ posts: Post[]; next_cursor: number | null }>(
      await authFetch(`/api/feed?${params}`)
    )
  },
  // Follows
  async follow(userId: number) {
    await handle(await authFetch(`/api/users/${userId}/follow`, { method: 'POST' }))
  },
  async unfollow(userId: number) {
    await handle(
      await authFetch(`/api/users/${userId}/follow`, { method: 'DELETE' })
    )
  },
  // Chats
  async listChats() {
    return handle<{ chats: Chat[] }>(await authFetch('/api/chats'))
  },
  async openChatWithPeer(peerId: number) {
    return handle<{ chat_id: number }>(
      await authFetch(`/api/chats/${peerId}`, { method: 'POST' })
    )
  },
  async getMessages(chatId: number, limit = 50, before?: number) {
    const params = new URLSearchParams({ limit: String(limit) })
    if (before) params.set('before', String(before))
    return handle<{ messages: Message[] }>(
      await authFetch(`/api/chats/${chatId}/messages?${params}`)
    )
  },
  // Uploads
  async requestUpload(contentType: string, sizeBytes: number) {
    return handle<{ upload_url: string; attachment_id: number; storage_key: string }>(
      await authFetch('/api/uploads', {
        method: 'POST',
        body: JSON.stringify({ content_type: contentType, size_bytes: sizeBytes }),
      })
    )
  },
  async completeUpload(attachmentId: number) {
    return handle<{ attachment_id: number; status: string }>(
      await authFetch(`/api/uploads/${attachmentId}/complete`, { method: 'POST' })
    )
  },
  async getAttachment(id: number) {
    return handle<AttachmentMeta>(await authFetch(`/api/uploads/${id}`))
  },
}

export function chatWebSocket(): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const token = getToken() ?? ''
  return new WebSocket(
    `${proto}//${window.location.host}/api/chats/ws?token=${token}`
  )
}