import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, api, getUserId, type Post } from '../api'
import PostCard from '../components/PostCard'

export default function ProfilePage() {
  const { userId: userIdParam } = useParams()
  const userId = userIdParam ? Number(userIdParam) : null
  const me = getUserId()

  const [posts, setPosts] = useState<Post[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [following, setFollowing] = useState(false)
  const [busy, setBusy] = useState(false)

  async function load() {
    if (!userId) return
    setLoading(true)
    setError(null)
    try {
      const data = await api.getUserPosts(userId)
      setPosts(data.posts)
    } catch (e) {
      setError(
        e instanceof ApiError ? `${e.status}: ${e.message}` : 'Failed to load'
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [userId])

  async function follow() {
    if (!userId) return
    setBusy(true)
    try {
      await api.follow(userId)
      setFollowing(true)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to follow')
    } finally {
      setBusy(false)
    }
  }

  async function unfollow() {
    if (!userId) return
    setBusy(true)
    try {
      await api.unfollow(userId)
      setFollowing(false)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to unfollow')
    } finally {
      setBusy(false)
    }
  }

  if (!userId) {
    return <div className="error">Invalid user ID</div>
  }
  if (me === userId) {
    return (
      <div className="profile-page">
        <h2>Your profile</h2>
        <p>
          That's you! Check your <Link to="/feed">home feed</Link>.
        </p>
      </div>
    )
  }

  return (
    <div className="profile-page">
      <header className="profile-header">
        <h2>User #{userId}</h2>
        <button
          onClick={following ? unfollow : follow}
          disabled={busy}
          className={following ? 'following' : ''}
        >
          {following ? 'Unfollow' : 'Follow'}
        </button>
      </header>
      {error && <div className="error">{error}</div>}
      {loading && posts.length === 0 ? (
        <div className="loading">Loading…</div>
      ) : posts.length === 0 ? (
        <div className="empty">No posts yet.</div>
      ) : (
        posts.map((p) => <PostCard key={p.id} post={p} />)
      )}
    </div>
  )
}