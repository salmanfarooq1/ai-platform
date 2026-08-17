import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import styles from './AnswerBlock.module.css'

export default function AnswerBlock({ answer, isStreaming = false }) {
  if (!answer) return null
  return (
    <div className={styles.wrapper}>
      <div className={`${styles.answer} ${isStreaming ? styles.streaming : ''}`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
        {isStreaming && <span className="cursor" aria-hidden="true" />}
      </div>
    </div>
  )
}
