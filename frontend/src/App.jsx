import { useEffect, useState } from 'react'
import axios from 'axios'
import './App.css'

const api = axios.create({
  baseURL: '/',
})

const CATEGORY_OPTIONS = [
  { id: 'primary', label: 'Primary' },
  { id: 'promotions', label: 'Promotions' },
  { id: 'social', label: 'Social' },
  { id: 'updates', label: 'Updates' },
]

const RESPONSE_LABELS = ['Answer', 'From', 'Date', 'Subject', 'Summary', 'Attachment']

function parseAssistantAnswer(text) {
  const normalized = (text || '').replace(/\r\n/g, '\n').trim()
  if (!normalized) {
    return null
  }

  const lines = normalized.split('\n')
  const sections = []
  let currentSection = null
  let currentField = null

  const pushSection = () => {
    if (!currentSection) {
      return
    }

    const cleanedFields = Object.fromEntries(
      Object.entries(currentSection.fields)
        .map(([key, value]) => [key, value.trim()])
        .filter(([, value]) => value),
    )

    if (currentSection.title || Object.keys(cleanedFields).length > 0) {
      sections.push({
        title: currentSection.title,
        fields: cleanedFields,
      })
    }
  }

  for (const rawLine of lines) {
    const line = rawLine.trim()

    if (!line) {
      if (currentField && currentSection) {
        currentSection.fields[currentField] += '\n'
      }
      continue
    }

    if (/^Email\s+\d+$/i.test(line)) {
      pushSection()
      currentSection = { title: line, fields: {} }
      currentField = null
      continue
    }

    const inlineLabelMatch = line.match(/^(Answer|From|Date|Subject|Summary|Attachment):\s*(.*)$/)
    if (inlineLabelMatch) {
      if (!currentSection) {
        currentSection = { title: '', fields: {} }
      }
      currentField = inlineLabelMatch[1]
      currentSection.fields[currentField] = inlineLabelMatch[2] || ''
      continue
    }

    if (!currentSection) {
      currentSection = { title: '', fields: { Answer: '' } }
      currentField = 'Answer'
    }

    if (!currentField) {
      currentField = 'Answer'
      currentSection.fields[currentField] = currentSection.fields[currentField] || ''
    }

    currentSection.fields[currentField] = currentSection.fields[currentField]
      ? `${currentSection.fields[currentField]}\n${line}`
      : line
  }

  pushSection()

  if (!sections.length) {
    return null
  }

  const [summarySection, ...detailSections] = sections
  const cleanedDetails = detailSections
    .map((section) => ({
      title: section.title,
      from: section.fields.From || '',
      date: section.fields.Date || '',
      subject: section.fields.Subject || '',
      summary: section.fields.Summary || '',
      attachment: section.fields.Attachment || '',
    }))
    .filter((detail) => detail.from || detail.date || detail.subject || detail.summary || detail.attachment)

  return {
    summary: summarySection.fields.Answer || '',
    introMeta: {
      from: summarySection.fields.From || '',
      date: summarySection.fields.Date || '',
      subject: summarySection.fields.Subject || '',
      attachment: summarySection.fields.Attachment || '',
      summary: summarySection.fields.Summary || '',
    },
    details: cleanedDetails,
  }
}

function splitParagraphs(text) {
  return (text || '')
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)
}

function AnswerContent({ text }) {
  const parsed = parseAssistantAnswer(text)

  if (!parsed) {
    return (
      <div className="message-copy">
        {splitParagraphs(text).map((paragraph, index) => (
          <p key={`paragraph-${index}`}>{paragraph}</p>
        ))}
      </div>
    )
  }

  return (
    <div className="assistant-answer">
      {parsed.summary ? (
        <div className="answer-summary">
          {splitParagraphs(parsed.summary).map((paragraph, index) => (
            <p key={`summary-${index}`}>{paragraph}</p>
          ))}
        </div>
      ) : null}

      {parsed.introMeta.from || parsed.introMeta.date || parsed.introMeta.subject || parsed.introMeta.summary || parsed.introMeta.attachment ? (
        <div className="answer-card">
          <div className="answer-card-header">
            <strong>Best Match</strong>
          </div>
          {parsed.introMeta.subject ? <h3>{parsed.introMeta.subject}</h3> : null}
          <div className="answer-meta">
            {parsed.introMeta.from ? <span>{parsed.introMeta.from}</span> : null}
            {parsed.introMeta.date ? <span>{parsed.introMeta.date}</span> : null}
          </div>
          {parsed.introMeta.summary ? <p>{parsed.introMeta.summary}</p> : null}
          {parsed.introMeta.attachment ? (
            <p className="answer-attachment">Attachment: {parsed.introMeta.attachment}</p>
          ) : null}
        </div>
      ) : null}

      {parsed.details.length ? (
        <div className="answer-detail-list">
          {parsed.details.map((detail, index) => (
            <article key={`${detail.title}-${index}`} className="answer-card">
              <div className="answer-card-header">
                <strong>{detail.title || `Email ${index + 1}`}</strong>
              </div>
              {detail.subject ? <h3>{detail.subject}</h3> : null}
              <div className="answer-meta">
                {detail.from ? <span>{detail.from}</span> : null}
                {detail.date ? <span>{detail.date}</span> : null}
              </div>
              {detail.summary ? <p>{detail.summary}</p> : null}
              {detail.attachment ? (
                <p className="answer-attachment">Attachment: {detail.attachment}</p>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function App() {
  const [health, setHealth] = useState(null)
  const [chatInput, setChatInput] = useState('')
  const [categoryFilters, setCategoryFilters] = useState([])
  const [senderFilter, setSenderFilter] = useState('')
  const [subjectFilter, setSubjectFilter] = useState('')
  const [dateFromFilter, setDateFromFilter] = useState('')
  const [dateToFilter, setDateToFilter] = useState('')
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
  const [syncStatusLoaded, setSyncStatusLoaded] = useState(false)

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
    api.get('/api/sync-status')
      .then((response) => setSyncStatus(response.data))
      .catch(() => {})
      .finally(() => setSyncStatusLoaded(true))
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
      setSyncStatusLoaded(true)
      await loadHealth()
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Sync failed.')
      api.get('/api/sync-status')
        .then((response) => setSyncStatus(response.data))
        .catch(() => {})
        .finally(() => setSyncStatusLoaded(true))
    } finally {
      api.get('/api/sync-status')
        .then((response) => setSyncStatus(response.data))
        .catch(() => {})
        .finally(() => setSyncStatusLoaded(true))
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
      const response = await api.post('/api/chat', {
        question,
        top_k: 4,
        category_filters: categoryFilters,
        search_filters: {
          sender: senderFilter,
          subject: subjectFilter,
          date_from: dateFromFilter || null,
          date_to: dateToFilter || null,
        },
      })
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

  const toggleCategoryFilter = (categoryId) => {
    setCategoryFilters((current) => (
      current.includes(categoryId)
        ? current.filter((value) => value !== categoryId)
        : [...current, categoryId]
    ))
  }

  const clearCategoryFilters = () => {
    setCategoryFilters([])
  }

  const clearStructuredFilters = () => {
    setSenderFilter('')
    setSubjectFilter('')
    setDateFromFilter('')
    setDateToFilter('')
  }

  const formatLastSyncedAt = (value) => {
    if (!syncStatusLoaded) {
      return 'Last sync: loading...'
    }

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

          <div className="chat-controls">
            <div className="filter-toolbar">
              <div className="filter-toolbar-copy">
                <p className="section-kicker">Mailbox Tabs</p>
                <p className="filter-toolbar-note">
                  {categoryFilters.length
                    ? `Searching ${categoryFilters.length} selected tab${categoryFilters.length > 1 ? 's' : ''}.`
                    : 'Searching across all Gmail tabs.'}
                </p>
              </div>
              <div className="filter-pill-row">
                {CATEGORY_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    className={`filter-pill ${categoryFilters.includes(option.id) ? 'active' : ''}`}
                    onClick={() => toggleCategoryFilter(option.id)}
                  >
                    {option.label}
                  </button>
                ))}
                <button
                  type="button"
                  className="filter-pill filter-pill-clear"
                  onClick={clearCategoryFilters}
                  disabled={!categoryFilters.length}
                >
                  All tabs
                </button>
              </div>
            </div>
            <div className="structured-filter-grid">
              <label className="structured-filter-field">
                <span>Sender</span>
                <input
                  type="text"
                  value={senderFilter}
                  onChange={(event) => setSenderFilter(event.target.value)}
                  placeholder="Seunghoon Baik or OpenAI"
                />
              </label>
              <label className="structured-filter-field">
                <span>Subject</span>
                <input
                  type="text"
                  value={subjectFilter}
                  onChange={(event) => setSubjectFilter(event.target.value)}
                  placeholder="Baltimore, invoice, interview"
                />
              </label>
              <label className="structured-filter-field">
                <span>Date From</span>
                <input
                  type="date"
                  value={dateFromFilter}
                  onChange={(event) => setDateFromFilter(event.target.value)}
                />
              </label>
              <label className="structured-filter-field">
                <span>Date To</span>
                <input
                  type="date"
                  value={dateToFilter}
                  onChange={(event) => setDateToFilter(event.target.value)}
                />
              </label>
            </div>
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
                  {message.role === 'assistant' ? (
                    <AnswerContent text={message.text} />
                  ) : (
                    <div className="message-copy">
                      {splitParagraphs(message.text).map((paragraph, paragraphIndex) => (
                        <p key={`user-paragraph-${paragraphIndex}`}>{paragraph}</p>
                      ))}
                    </div>
                  )}
                  {message.sources?.length ? (
                    <div className="source-list">
                      <p className="sources-label">Sources</p>
                      {message.sources.map((source) => (
                        <div
                          key={`${source.gmail_message_id}-${source.subject}`}
                          className="source-card"
                        >
                          <strong>{source.subject}</strong>
                          {source.gmail_category ? (
                            <span className="source-category">{source.gmail_category}</span>
                          ) : null}
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
                Use Sender, Subject, and Date filters for exact matches. Natural language now acts as the instruction layer.
              </p>
              <div className="composer-actions">
                <button type="button" className="secondary-button" onClick={clearStructuredFilters}>
                  Clear filters
                </button>
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
