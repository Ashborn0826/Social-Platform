import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ApiError,
  api,
  chatWebSocket,
  clearAuth,
  getUserId,
  type Chat,
  type Message,
} from '../api'

export default function ChatsPage() {
  const { chatId: chatIdParam } = useParams()
  const chatId = chatIdParam ? Number(chatIdParam) : null
  const nav = useNavigate()

  const [chats, setChats] = useState<Chat[]>([])
  const [peerInput, setPeerInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [text, setText] = useState('')
  const [wsStatus, setWsStatus] = useState<'connecting' | 'open' | 'closed'>(
    'closed'
  )
  const wsRef = useRef<WebSocket | null>(null)
  const chatIdRef = useRef<number | null>(chatId)
  const messagesEndRef = useRef<HTMLDivElement | null>(null)

  // Keep the latest chatId in a ref so the WS message handler reads the
  // current value without re-binding the socket every navigation.
  useEffect(() => {
    chatIdRef.current = chatId
  }, [chatId])

  async function loadChats() {
    try {
      const data = await api.listChats()
      setChats(data.chats)
    } catch {
      // non-fatal
    }
  }

  async function loadMessages(cid: number) {
    try {
      const data = await api.getMessages(cid)
      setMessages(data.messages)
    } catch (e) {
      if (e instanceof ApiError) alert(`${e.status}: ${e.message}`)
    }
  }

  // WebSocket — connect once on mount, never reconnect on navigation.
  useEffect(() => {
    const ws = chatWebSocket()
    wsRef.current = ws
    setWsStatus('connecting')
    ws.onopen = () => setWsStatus('open')
    ws.onerror = () => setWsStatus('closed')
    ws.onclose = (event) => {
      setWsStatus('closed')
      // 4401 is our custom auth-failure close code (set by the server when
      // the JWT is missing or invalid). Other close codes (1000 normal,
      // 1006 abnormal closure) are not auth failures — don't log out.
      if (event.code === 4401) {
        clearAuth()
        nav('/login')
      }
    }
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        if (data.type === 'message') {
          if (data.chat_id === chatIdRef.current) {
            setMessages((prev) => [
              data.message,
              ...prev.filter((m) => m.id !== data.message.id),
            ])
          }
          loadChats()
        }
      } catch {
        // ignore non-JSON frames
      }
    }
    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [])

  // Load chats on mount
  useEffect(() => {
    loadChats()
  }, [])

  // Load messages when active chat changes
  useEffect(() => {
    if (chatId !== null) {
      loadMessages(chatId)
    } else {
      setMessages([])
    }
  }, [chatId])

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, chatId])

  async function openChat(e: React.FormEvent) {
    e.preventDefault()
    const peer = Number(peerInput)
    if (!peer) return
    try {
      const data = await api.openChatWithPeer(peer)
      nav(`/chats/${data.chat_id}`)
      setPeerInput('')
      loadChats()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to open chat')
    }
  }

  function send(e: React.FormEvent) {
    e.preventDefault()
    if (!text.trim() || !chatId) return
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'send', chat_id: chatId, text }))
    setText('')
  }

  const activeChat = chats.find((c) => c.chat_id === chatId)
  const myUserId = getUserId()

  return (
    <div className="chats-page">
      <aside className="chat-list">
        <h2>Chats</h2>
        <form onSubmit={openChat} className="new-chat">
          <input
            type="number"
            placeholder="Open chat with user ID"
            value={peerInput}
            onChange={(e) => setPeerInput(e.target.value)}
            min={1}
          />
          <button type="submit">Open</button>
        </form>
        {chats.length === 0 ? (
          <p className="empty">
            No chats yet. Enter a user ID above and click Open.
          </p>
        ) : (
          chats.map((c) => (
            <button
              key={c.chat_id}
              type="button"
              className={`chat-list-item${chatId === c.chat_id ? ' active' : ''}`}
              onClick={() => nav(`/chats/${c.chat_id}`)}
            >
              <div className="chat-list-peer">{c.peer.display_name}</div>
              {c.last_message && (
                <div className="chat-list-preview">{c.last_message.text}</div>
              )}
            </button>
          ))
        )}
      </aside>
      <section className="chat-room">
        {!chatId ? (
          <div className="empty">Select or open a chat to start messaging.</div>
        ) : (
          <>
            <header className="chat-header">
              <strong>{activeChat?.peer.display_name ?? 'Chat'}</strong>
              <span className={`ws-status ws-${wsStatus}`}>{wsStatus}</span>
            </header>
            <div className="message-list">
              {messages.length === 0 ? (
                <div className="empty">No messages yet.</div>
              ) : (
                messages.map((m) => {
                  const mine = myUserId === m.sender_id
                  return (
                    <div
                      key={m.id}
                      className={`message${mine ? ' mine' : ''}`}
                    >
                      {!mine && activeChat && (
                        <div className="message-sender">
                          {activeChat.peer.display_name}
                        </div>
                      )}
                      <p>{m.text}</p>
                      <time>
                        {new Date(m.created_at).toLocaleTimeString()}
                      </time>
                    </div>
                  )
                })
              )}
              <div ref={messagesEndRef} />
            </div>
            <form onSubmit={send} className="composer">
              <input
                type="text"
                placeholder="Type a message…"
                value={text}
                onChange={(e) => setText(e.target.value)}
                disabled={wsStatus !== 'open'}
              />
              <button
                type="submit"
                disabled={!text.trim() || wsStatus !== 'open'}
              >
                Send
              </button>
            </form>
          </>
        )}
      </section>
    </div>
  )
}