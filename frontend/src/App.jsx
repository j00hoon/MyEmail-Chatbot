import { useEffect, useState } from 'react'
import axios from 'axios'
import './App.css'

const api = axios.create({
  baseURL: 'http://127.0.0.1:8000',
})

const buildStatusCards = (health) => [
  {
    label: 'Run Mode',
    value: health?.app_env || 'checking',
    description: 'Current app runtime profile for this local workspace.',
  },
  {
    label: 'AI Engine',
    value: health?.openai_configured ? 'OpenAI connected' : 'Local fallback',
    description: 'Shows whether GPT-powered generation is active or offline retrieval is used.',
  },
  {
    label: 'Gmail Access',
    value: health?.gmail_credentials_present ? 'OAuth ready' : 'Credentials missing',
    description: 'Confirms whether Gmail OAuth files are available for mailbox sync.',
  },
]

const quickPrompts = [
  'What recruiter emails arrived this week?',
  'Summarize interview follow-ups I should send.',
  'Which emails include attachments I need to review?',
]

const syncStages = [
  'Connecting to Gmail',
  'Pulling recent messages',
  'Normalizing email content',
  'Refreshing vector index',
  'Finalizing local cache',
]

function App() {
  const [health, setHealth] = useState(null)
  const [emails, setEmails] = useState([])
  const [count, setCount] = useState(10)
  const [chatInput, setChatInput] = useState('')
  const [chatHistory, setChatHistory] = useState([])
  const [syncing, setSyncing] = useState(false)
  const [chatting, setChatting] = useState(false)
  const [loadingEmails, setLoadingEmails] = useState(false)
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
  })

  const statusCards = buildStatusCards(health)
  const activeSyncStage = syncStatus.stage

  useEffect(() => {
    if (!syncing) {
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
  }, [syncing])

  const loadHealth = async () => {
    const response = await api.get('/api/health')
    setHealth(response.data)
  }

  const loadEmails = async () => {
    setLoadingEmails(true)
    try {
      const response = await api.get('/api/emails?limit=20')
      setEmails(Array.isArray(response.data) ? response.data : [])
    } finally {
      setLoadingEmails(false)
    }
  }

  useEffect(() => {
    loadHealth().catch(() => {})
    loadEmails().catch(() => {})
    api.get('/api/sync-status').then((response) => setSyncStatus(response.data)).catch(() => {})
  }, [])

  const handleSync = async () => {
    const normalizedCount = Math.min(50, Math.max(1, Number(count) || 10))
    setCount(normalizedCount)
    setSyncing(true)
    setError('')
    setStatus('')
    setSyncStatus({
      state: 'running',
      stage: 'Connecting to Gmail',
      progress: 5,
      detail: `Preparing to sync up to ${normalizedCount} recent emails.`,
      fetched_count: 0,
      saved_count: 0,
      indexed_count: 0,
    })

    try {
      const response = await api.post('/api/sync', { count: normalizedCount })
      setStatus(response.data.message)
      const syncStatusResponse = await api.get('/api/sync-status')
      setSyncStatus(syncStatusResponse.data)
      await loadHealth()
      await loadEmails()
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Sync failed.')
      api.get('/api/sync-status').then((response) => setSyncStatus(response.data)).catch(() => {})
    } finally {
      setSyncing(false)
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

  return (
    <main className="app-shell">
      <section className="hero-grid">
        <article className="hero-card hero-main">
          <div className="hero-topline">
            <span className="hero-badge">Private Gmail Workspace</span>
            <span className="hero-dot" />
            <span className="hero-mini">local RAG system</span>
          </div>
          <h1>Turn your inbox into a searchable purple command center.</h1>
          <p className="hero-copy">
            Sync recent Gmail threads, index them locally, and ask natural questions
            through a cleaner personal AI workspace built for demos and iteration.
          </p>
          <div className="hero-actions">
            <button type="button" onClick={handleSync} disabled={syncing}>
              {syncing ? 'Syncing and indexing...' : 'Sync latest emails'}
            </button>
            <div className="hero-chip">
              <span>Indexed emails</span>
              <strong>{emails.length}</strong>
            </div>
          </div>
        </article>

        <div className="status-bento">
          {statusCards.map((item) => (
            <article className="status-card" key={item.label}>
              <p className="card-label">{item.label}</p>
              <h2>{item.value}</h2>
              <p className="card-copy">{item.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="workspace-grid">
        <article className="panel panel-compact">
          <div className="panel-header">
            <div>
              <p className="section-kicker">Ingestion Agent</p>
              <h2>Sync Settings</h2>
            </div>
            <span className="panel-badge">step 01</span>
          </div>

          <div className="sync-metric">
            <span className="sync-metric-label">Next sync size</span>
            <strong>{count}</strong>
            <small>recent Gmail emails</small>
          </div>

          <label className="input-group" htmlFor="count">
            <span>Recent email count</span>
            <input
              id="count"
              type="number"
              min="1"
              max="50"
              value={count}
              onChange={(event) => setCount(event.target.value)}
            />
          </label>

          <div className="sync-options">
            <div className="mini-card">
              <span>Storage</span>
              <strong>SQLite + local vector index</strong>
            </div>
            <div className="mini-card">
              <span>Mode</span>
              <strong>{health?.openai_configured ? 'GPT-assisted RAG' : 'retrieval only'}</strong>
            </div>
          </div>

          <p className="panel-copy">
            Pull fresh Gmail messages, normalize content, then refresh the retrieval layer for chat.
          </p>

          {syncing ? (
            <div className="sync-live-card">
              <div className="sync-live-header">
                <div>
                  <p className="sync-live-kicker">Live Progress</p>
                  <strong>{activeSyncStage}</strong>
                </div>
                <span>{syncStatus.progress}% complete</span>
              </div>
              <div className="sync-progress-track" aria-hidden="true">
                <span
                  className="sync-progress-bar"
                  style={{ width: `${Math.max(syncStatus.progress, 10)}%` }}
                />
              </div>
              <p className="sync-live-detail">{syncStatus.detail}</p>
              <div className="sync-stats-row">
                <div className="sync-stat-pill">
                  <span>Fetched</span>
                  <strong>{syncStatus.fetched_count}</strong>
                </div>
                <div className="sync-stat-pill">
                  <span>Saved</span>
                  <strong>{syncStatus.saved_count}</strong>
                </div>
                <div className="sync-stat-pill">
                  <span>Indexed</span>
                  <strong>{syncStatus.indexed_count}</strong>
                </div>
              </div>
              <div className="sync-stage-list">
                {syncStages.map((stage, index) => {
                  const currentStageIndex = Math.max(syncStages.indexOf(syncStatus.stage), 0)
                  const state =
                    index < currentStageIndex
                      ? 'done'
                      : index === currentStageIndex
                        ? 'active'
                        : 'upcoming'

                  return (
                    <div key={stage} className={`sync-stage ${state}`}>
                      <span className="sync-stage-dot" />
                      <span>{stage}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          ) : null}

          {status ? <p className="status success">{status}</p> : null}
          {error ? <p className="status error">{error}</p> : null}
        </article>

        <article className="panel panel-chat">
          <div className="panel-header">
            <div>
              <p className="section-kicker">Chat Agent</p>
              <h2>Ask Your Inbox</h2>
            </div>
            <span className="panel-badge">step 02</span>
          </div>

          <div className="prompt-row">
            {quickPrompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                className="prompt-chip"
                onClick={() => setChatInput(prompt)}
              >
                {prompt}
              </button>
            ))}
          </div>

          <div className="chat-box">
            {chatHistory.length === 0 ? (
              <div className="empty-state">
                <p>Try prompts like:</p>
                <strong>Which recruiter emails need a reply this week?</strong>
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
                {chatting ? 'Thinking...' : 'Ask inbox'}
              </button>
            </div>
          </div>
        </article>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-kicker">Indexed Metadata</p>
            <h2>Stored Emails</h2>
          </div>
          <div className="stored-header-actions">
            <div className="hero-chip">
              <span>Visible</span>
              <strong>{emails.length}</strong>
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={loadEmails}
              disabled={loadingEmails}
            >
              {loadingEmails ? 'Refreshing...' : 'Refresh list'}
            </button>
          </div>
        </div>

        <div className="email-list">
          {emails.length === 0 ? (
            <div className="empty-state">
              <p>No emails indexed yet.</p>
              <strong>Run sync first to fill your local knowledge base.</strong>
            </div>
          ) : (
            emails.map((email) => (
              <article className="email-card" key={email.gmail_message_id}>
                <div className="email-header">
                  <div>
                    <p className="email-meta-label">Email record</p>
                    <h3>{email.subject || 'No Subject'}</h3>
                    <span>{email.sender || 'Unknown sender'}</span>
                  </div>
                  <span className="email-tag">
                    {email.attachment_names?.length || 0} attachments
                  </span>
                </div>
                <p>{email.snippet || email.body_text || 'No preview available.'}</p>
                {email.attachment_names?.length ? (
                  <p className="attachments">
                    Attachments: {email.attachment_names.join(', ')}
                  </p>
                ) : null}
                <div className="email-footer">
                  <span className="email-id">ID {email.gmail_message_id.slice(0, 12)}</span>
                  <span className="email-state">indexed locally</span>
                </div>
              </article>
            ))
          )}
        </div>
      </section>
    </main>
  )
}

export default App
