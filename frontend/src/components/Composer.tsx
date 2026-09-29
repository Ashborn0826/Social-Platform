import { useState } from 'react'
import { ApiError, api } from '../api'

export default function Composer({ onPosted }: { onPosted: () => void }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!text.trim()) return
    setBusy(true)
    setError(null)
    try {
      await api.createPost(text)
      setText('')
      onPosted()
    } catch (e) {
      setError(
        e instanceof ApiError ? `${e.status}: ${e.message}` : 'Failed to post'
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        placeholder="What's on your mind?"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        maxLength={2000}
      />
      <div className="composer-footer">
        <span className="char-count">{text.length} / 2000</span>
        <button type="submit" disabled={busy || !text.trim()}>
          {busy ? 'Posting…' : 'Post'}
        </button>
      </div>
      {error && <div className="error">{error}</div>}
    </form>
  )
}