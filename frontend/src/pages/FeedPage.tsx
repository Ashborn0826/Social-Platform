import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Post } from '../api'
import Composer from '../components/Composer'
import PostCard from '../components/PostCard'

export default function FeedPage() {
  const [posts, setPosts] = useState<Post[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nextCursor, setNextCursor] = useState<number | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)

  async function refresh() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getFeed(20)
      setPosts(data.posts)
      setNextCursor(data.next_cursor)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load feed')
    } finally {
      setLoading(false)
    }
  }

  async function loadMore() {
    if (!nextCursor || loadingMore) return
    setLoadingMore(true)
    try {
      const data = await api.getFeed(20, nextCursor)
      setPosts((prev) => [...prev, ...data.posts])
      setNextCursor(data.next_cursor)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load more')
    } finally {
      setLoadingMore(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  return (
    <div className="feed-page">
      <h2>Home</h2>
      <Composer onPosted={refresh} />
      {error && <div className="error">{error}</div>}
      {loading && posts.length === 0 ? (
        <div className="loading">Loading feed…</div>
      ) : posts.length === 0 ? (
        <div className="empty">
          Your feed is empty.
          <br />
          Follow someone to see their posts. To find user IDs, sign up
          another account in an incognito window — the user ID is
          returned in the signup response.
        </div>
      ) : (
        <>
          {posts.map((p) => (
            <PostCard key={p.id} post={p} />
          ))}
          {nextCursor && (
            <button
              className="load-more"
              onClick={loadMore}
              disabled={loadingMore}
            >
              {loadingMore ? 'Loading…' : 'Load older posts'}
            </button>
          )}
        </>
      )}
      <p className="refresh-hint">
        <Link to="/upload">Upload an image</Link> ·{' '}
        <Link to="/chats">Open chats</Link>
      </p>
    </div>
  )
}