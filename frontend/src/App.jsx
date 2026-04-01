import { useEffect, useState } from 'react'
import axios from 'axios'
import './App.css'

const api = axios.create({
  baseURL: '/',
})

function App() {
  const [health, setHealth] = useState(null)
  const [chatInput, setChatInput] = useState('')
  const [chatHistory, setChatHistory] = useState([])
  const [syncing, setSyncing] = useState(false)
  const [chatting, setChatting] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [syncStatus, setSyncStatus] = useState({
    state: 'idle',
    stage: 'Ready',
    progress: 0,
    detail: 'No sync in progress.',
    fetched_count: 0,
    saved_count: 0,
    indexed_count: 0,
    last_completed_at: null,
  })

  const isSyncRunning = syncing || syncStatus.state === 'running'
  const recentQuestions = chatHistory
    .filter((message) => message.role === 'user')
    .slice(-3)
    .reverse()

  useEffect(() => {
    if (!isSyncRunning) {
      return
    }

    const pollSyncStatus = async () => {
      try {
        const response = await api.get('/api/sync-status')
        setSyncStatus(response.data)
      } catch {
        return
      }
    }

    pollSyncStatus()
    const timer = window.setInterval(pollSyncStatus, 1000)

    return () => window.clearInterval(timer)
  }, [isSyncRunning])

  const loadHealth = async () => {
    const response = await api.get('/api/health')
    setHealth(response.data)
  }

  useEffect(() => {
    loadHealth().catch(() => {})
    api.get('/api/sync-status').then((response) => setSyncStatus(response.data)).catch(() => {})
  }, [])

  const handleSync = async () => {
    if (isSyncRunning) {
      return
    }

    setSyncing(true)
    setError('')
    setStatus('')
    setSyncStatus({
      state: 'running',
      stage: 'Connecting to Gmail',
      progress: 5,
      detail: 'Preparing mailbox sync.',
      fetched_count: 0,
      saved_count: 0,
      indexed_count: 0,
      last_completed_at: syncStatus.last_completed_at,
    })

    try {
      const response = await api.post('/api/sync', { count: 10 })
      setStatus(response.data.message)
      const syncStatusResponse = await api.get('/api/sync-status')
      setSyncStatus(syncStatusResponse.data)
      await loadHealth()
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Sync failed.')
      api.get('/api/sync-status').then((response) => setSyncStatus(response.data)).catch(() => {})
    } finally {
      api.get('/api/sync-status')
        .then((response) => setSyncStatus(response.data))
        .catch(() => {})
        .finally(() => setSyncing(false))
    }
  }

  const handleAsk = async () => {
    if (!chatInput.trim()) {
      return
    }

    const question = chatInput.trim()
    setChatHistory((current) => [...current, { role: 'user', text: question }])
    setChatInput('')
    setChatting(true)
    setError('')

    try {
      const response = await api.post('/api/chat', { question, top_k: 4 })
      setChatHistory((current) => [
        ...current,
        {
          role: 'assistant',
          text: response.data.answer,
          sources: response.data.sources || [],
        },
      ])
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Chat request failed.'
      setChatHistory((current) => [...current, { role: 'assistant', text: message }])
      setError(message)
    } finally {
      setChatting(false)
    }
  }

  const formatLastSyncedAt = (value) => {
    if (!value) {
      return 'Last sync: not yet run'
    }

    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) {
      return 'Last sync: unavailable'
    }

    return `Last sync: ${parsed.toLocaleString()}`
  }

  return (
    <main className="app-shell">
      <header className="simple-header">
        <div>
          <p className="section-kicker">Chat Agent</p>
          <h1 className="app-title">Ask Your Inbox</h1>
        </div>
        <div className="header-pills">
          <div className="hero-chip">
            <span>AI</span>
            <strong>{health?.openai_configured ? 'On' : 'Off'}</strong>
          </div>
          <div className="hero-chip">
            <span>Gmail</span>
            <strong>{health?.gmail_credentials_present ? 'Ready' : 'Missing'}</strong>
          </div>
        </div>
      </header>

      <section className="chat-layout">
        <article className="panel panel-chat panel-chat-main">
          <div className="panel-header">
            <div>
              <p className="section-kicker">Main Workspace</p>
              <h2>Chat With Your Email</h2>
            </div>
            <span className="panel-badge">chat</span>
          </div>

          <div className="chat-box">
            {chatHistory.length === 0 ? (
              <div className="empty-state">
                <strong>Ask about recent emails, recruiters, interviews, receipts, or certifications.</strong>
              </div>
            ) : (
              chatHistory.map((message, index) => (
                <article
                  key={`${message.role}-${index}`}
                  className={`message-bubble ${message.role}`}
                >
                  <p className="message-role">{message.role}</p>
                  <p>{message.text}</p>
                  {message.sources?.length ? (
                    <div className="source-list">
                      <p className="sources-label">Sources</p>
                      {message.sources.map((source) => (
                        <div
                          key={`${source.gmail_message_id}-${source.subject}`}
                          className="source-card"
                        >
                          <strong>{source.subject}</strong>
                          <span>{source.sender || 'Unknown sender'}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </article>
              ))
            )}
            {chatting ? (
              <article className="message-bubble assistant thinking-bubble" aria-live="polite">
                <p className="message-role">assistant</p>
                <div className="thinking-row">
                  <div className="thinking-dots" aria-hidden="true">
                    <span className="thinking-dot" />
                    <span className="thinking-dot" />
                    <span className="thinking-dot" />
                  </div>
                  <p>Searching your inbox and drafting an answer...</p>
                </div>
              </article>
            ) : null}
          </div>

          <div className="chat-controls">
            <textarea
              rows="4"
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              placeholder="Summarize recruiter emails, interview follow-ups, or attachments I should review"
            />
            <div className="composer-row">
              <p className="composer-hint">
                Answers are grounded in indexed Gmail messages, not generic chat memory.
              </p>
              <button type="button" onClick={handleAsk} disabled={chatting}>
                {chatting ? (
                  <>
                    <span className="button-spinner" aria-hidden="true" />
                    Thinking
                  </>
                ) : 'Ask inbox'}
              </button>
            </div>
          </div>
        </article>

        <aside className="panel panel-sync-side">
          <div className="panel-header">
            <div>
              <p className="section-kicker">Mailbox</p>
              <button type="button" onClick={handleSync} disabled={isSyncRunning}>
                {isSyncRunning ? 'Syncing...' : 'Sync emails'}
              </button>
              <p className="sync-timestamp">{formatLastSyncedAt(syncStatus.last_completed_at)}</p>
            </div>
            <span className={`status-pill ${syncStatus.state}`}>{syncStatus.state}</span>
          </div>

          <p className="panel-copy">
            Sync once to load your mailbox, then sync again anytime to pull changes.
          </p>

          {isSyncRunning ? (
            <div className="sync-live-card compact">
              <div className="sync-live-header simple">
                <strong>{syncStatus.stage}</strong>
                <span>{syncStatus.progress}%</span>
              </div>
              <div className="sync-progress-track" aria-hidden="true">
                <span
                  className="sync-progress-bar"
                  style={{ width: `${Math.max(syncStatus.progress, 10)}%` }}
                />
              </div>
              <p className="sync-live-detail">{syncStatus.detail}</p>
            </div>
          ) : (
            <p className="sync-idle-note">
              {syncStatus.state === 'completed'
                ? 'Mailbox is up to date.'
                : syncStatus.state === 'failed'
                  ? syncStatus.detail
                  : 'No sync in progress.'}
            </p>
          )}

          {status ? <p className="status success">{status}</p> : null}
          {error ? <p className="status error">{error}</p> : null}

          <section className="question-history">
            <div className="question-history-header">
              <p className="section-kicker">Question History</p>
              <span>{recentQuestions.length}/3</span>
            </div>

            {recentQuestions.length > 0 ? (
              <div className="question-history-list">
                {recentQuestions.map((message, index) => (
                  <article
                    key={`recent-question-${index}-${message.text}`}
                    className="question-history-item"
                  >
                    <p>{message.text}</p>
                  </article>
                ))}
              </div>
            ) : (
              <p className="question-history-empty">
                Your last 3 questions will appear here.
              </p>
            )}
          </section>
        </aside>
      </section>

    </main>
  )
}

export default App
