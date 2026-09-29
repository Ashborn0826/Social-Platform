import { useState } from 'react'
import { ApiError, api } from '../api'

export default function UploadPage() {
  const [status, setStatus] = useState<string>(
    'Pick a JPEG (or PNG/WebP). The frontend requests a presigned URL, PUTs bytes directly to storage, marks complete, then polls for the thumbnail.'
  )
  const [lastAttachmentId, setLastAttachmentId] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleFile(file: File) {
    setBusy(true)
    try {
      setStatus(`Step 1/4: requesting presigned upload URL for ${file.type} (${(file.size / 1024).toFixed(1)} KB)…`)
      const r1 = await api.requestUpload(file.type, file.size)
      const { upload_url, attachment_id } = r1
      setLastAttachmentId(attachment_id)

      setStatus('Step 2/4: PUT-ing bytes directly to storage…')
      const put = await fetch(upload_url, { method: 'PUT', body: file })
      if (!put.ok) throw new Error(`upload PUT failed: ${put.status}`)

      setStatus('Step 3/4: marking complete (queues thumbnail job)…')
      await api.completeUpload(attachment_id)

      setStatus(
        'Step 4/4: polling for thumbnail_key (worker is processing the image)…'
      )
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 500))
        const att = await api.getAttachment(attachment_id)
        if (att.thumbnail_key) {
          setStatus(
            `Done! thumbnail_key=${att.thumbnail_key} status=${att.status}`
          )
          return
        }
      }
      setStatus('Timeout: worker did not process within 10s. Check worker logs.')
    } catch (e) {
      setStatus(
        `Error: ${
          e instanceof ApiError ? `${e.status}: ${e.message}` : (e as Error).message
        }`
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="upload-page">
      <h2>Upload pipeline test</h2>
      <p className="muted">{status}</p>
      <input
        type="file"
        accept="image/jpeg,image/png,image/webp"
        disabled={busy}
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) handleFile(f)
        }}
      />
      {lastAttachmentId !== null && (
        <p className="muted">
          Last attachment ID: <code>{lastAttachmentId}</code>
        </p>
      )}
    </div>
  )
}