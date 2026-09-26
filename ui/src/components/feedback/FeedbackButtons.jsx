import { useState } from 'react'
import { ThumbsUp, ThumbsDown } from 'lucide-react'
import { submitFeedback } from '../../api/feedback'
import styles from './FeedbackButtons.module.css'

export default function FeedbackButtons({ requestId, endpoint }) {
  const [sent, setSent]   = useState(null)  // null | 'up' | 'down'
  const [error, setError] = useState(false)

  if (!requestId) return null  // no ID = no feedback

  async function handleRate(rating) {
    if (sent) return
    try {
      await submitFeedback({ requestId, endpoint, rating })
      setSent(rating)
    } catch { setError(true) }
  }

  return (
    <div className={styles.row} role="group" aria-label="Rate this answer">
      <button className={`${styles.btn} ${sent === 'up' ? styles.active : ''}`}
        onClick={() => handleRate('up')} disabled={!!sent} aria-pressed={sent === 'up'} aria-label="Helpful" title="Helpful">
        <ThumbsUp size={16} strokeWidth={1.75} />
      </button>
      <button className={`${styles.btn} ${sent === 'down' ? styles.active : ''}`}
        onClick={() => handleRate('down')} disabled={!!sent} aria-pressed={sent === 'down'} aria-label="Not helpful" title="Not helpful">
        <ThumbsDown size={16} strokeWidth={1.75} />
      </button>
      {sent && <span className={styles.thanks}>Thanks for the feedback</span>}
      {error && <span className={styles.err}>Couldn't submit — try again</span>}
    </div>
  )
}
