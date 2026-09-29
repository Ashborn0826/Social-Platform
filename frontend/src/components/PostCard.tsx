import { Link } from 'react-router-dom'
import type { Post } from '../api'

export default function PostCard({ post }: { post: Post }) {
  return (
    <article className="post-card">
      <header>
        <Link to={`/users/${post.author.id}`} className="post-author">
          {post.author.display_name}
        </Link>
        <time>{formatTime(post.created_at)}</time>
      </header>
      <p className="post-text">{post.text}</p>
      {post.attachments.length > 0 && (
        <div className="post-attachments">
          {post.attachments.map((a) => (
            <a
              key={a.id}
              href={a.url}
              target="_blank"
              rel="noopener noreferrer"
              className="attachment"
            >
              {a.content_type.startsWith('image/') ? (
                <img src={a.thumbnail_url ?? a.url} alt="" loading="lazy" />
              ) : (
                <div className="attachment-placeholder">📎 {a.content_type}</div>
              )}
            </a>
          ))}
        </div>
      )}
    </article>
  )
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diff = (now.getTime() - d.getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return d.toLocaleDateString()
}