import { useState } from 'react'
import axios from 'axios'
import './App.css'

function App() {
  const [emails, setEmails] = useState([])
  const [loading, setLoading] = useState(false)
  const [count, setCount] = useState(10)
  const [error, setError] = useState('')

  const handleFetchEmails = async () => {
    const normalizedCount = Math.min(50, Math.max(1, Number(count) || 10))

    setCount(normalizedCount)
    setLoading(true)
    setError('')

    try {
      const response = await axios.get(
        `http://127.0.0.1:5000/api/emails?count=${normalizedCount}`,
      )
      setEmails(Array.isArray(response.data) ? response.data : [])
    } catch (err) {
      const message =
        err.response?.data?.error ||
        err.message ||
        'An error occurred while fetching emails.'
      setEmails([])
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  const handleResetEmails = () => {
    setEmails([])
    setError('')
    setLoading(false)
  }

  return (
    <main className="app-shell">
      <section className="panel">
        <div className="hero">
          <p className="eyebrow">Gmail Inbox Viewer</p>
          <h1>Choose how many emails to load</h1>
          <p className="hero-copy">
            Connect to the Flask backend API and load your latest emails.
          </p>
        </div>

        <div className="controls">
          <label className="input-group" htmlFor="count">
            <span>Email Count</span>
            <input
              id="count"
              type="number"
              min="1"
              max="50"
              value={count}
              onChange={(event) => setCount(event.target.value)}
            />
          </label>

          <button type="button" onClick={handleFetchEmails} disabled={loading}>
            {loading ? 'Loading...' : 'Fetch Emails'}
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={handleResetEmails}
            disabled={loading && emails.length === 0}
          >
            Reset
          </button>
        </div>

        {error ? <p className="status error">{error}</p> : null}
        {!error && loading ? (
          <p className="status">Loading your email list...</p>
        ) : null}
        {!loading && !error && emails.length === 0 ? (
          <p className="status">No emails have been loaded yet.</p>
        ) : null}

        <div className="email-list">
          {emails.map((email) => (
            <article className="email-card" key={email.id}>
              <div className="email-header">
                <h2>{email.subject || 'No Subject'}</h2>
                <span className="email-badge">
                  Attachments {email.attachments?.length ?? 0}
                </span>
              </div>
              <p>{email.snippet || 'No preview available.'}</p>
              {email.attachments?.length ? (
                <p className="attachments">
                  Attachments: {email.attachments.join(', ')}
                </p>
              ) : null}
            </article>
          ))}
        </div>
      </section>
    </main>
  )
}

export default App
