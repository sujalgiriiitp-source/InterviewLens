import { useEffect, useRef, useState } from 'react'
import {
  fetchRoles,
  createSession,
  submitAnswer,
  finishSession,
} from './api'

// The two roles defined by the API contract. Used only as a fallback so the
// role select still renders if GET /api/roles fails while the backend is
// down; the live list from the API always wins when it loads.
const FALLBACK_ROLES = [
  { id: 'ai_ml', label: 'AI/ML Engineer', books: [] },
  { id: 'data_science', label: 'Data Science / Applied ML Engineer', books: [] },
]

const ACCEPTED_TYPES = '.pdf,.txt'

function App() {
  // --- Roles (loaded from the API) ---
  const [roles, setRoles] = useState([])
  const [rolesError, setRolesError] = useState('')
  const [rolesLoading, setRolesLoading] = useState(true)

  // --- Upload step ---
  const [file, setFile] = useState(null)
  const [role, setRole] = useState('ai_ml')
  const [creating, setCreating] = useState(false)

  // --- Session / interview step ---
  const [session, setSession] = useState(null) // { session_id, parsed, topics, questions }
  const [questions, setQuestions] = useState([]) // queue, incl. any adaptive follow-ups
  const [currentIndex, setCurrentIndex] = useState(0)
  const [answer, setAnswer] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [qaRecord, setQaRecord] = useState([]) // [{ question, answer }]

  // --- Summary step ---
  const [summary, setSummary] = useState(null)
  const [finishing, setFinishing] = useState(false)

  const [error, setError] = useState('')
  const fileInputRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    fetchRoles()
      .then((data) => {
        if (cancelled) return
        const list = Array.isArray(data) ? data : []
        if (list.length > 0) {
          setRoles(list)
          setRole(list[0].id)
        } else {
          setRoles(FALLBACK_ROLES)
        }
      })
      .catch((err) => {
        if (cancelled) return
        setRolesError(
          `Could not load roles from the API (${err.message}). Showing the two roles from the spec — starting an interview still needs the backend on port 8000.`,
        )
        setRoles(FALLBACK_ROLES)
      })
      .finally(() => {
        if (!cancelled) setRolesLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const currentQuestion = questions[currentIndex] || null
  const totalQuestions = questions.length
  const selectedRole = roles.find((r) => r.id === role)

  function resetAll() {
    setFile(null)
    setRole(roles.length > 0 ? roles[0].id : 'ai_ml')
    setCreating(false)
    setSession(null)
    setQuestions([])
    setCurrentIndex(0)
    setAnswer('')
    setSubmitting(false)
    setQaRecord([])
    setSummary(null)
    setFinishing(false)
    setError('')
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  async function handleStart(e) {
    e.preventDefault()
    setError('')
    if (!file) {
      setError('Please choose a resume file (.pdf or .txt) first.')
      return
    }
    setCreating(true)
    try {
      const data = await createSession(file, role)
      if (!data.questions || data.questions.length === 0) {
        throw new Error('The API returned a session with no questions.')
      }
      setSession(data)
      setQuestions(data.questions)
      setCurrentIndex(0)
      setQaRecord([])
      setSummary(null)
    } catch (err) {
      setError(err.message || 'Failed to start the interview.')
    } finally {
      setCreating(false)
    }
  }

  async function handleSubmitAnswer(e) {
    e.preventDefault()
    setError('')
    if (!currentQuestion) return
    if (!answer.trim()) {
      setError('Please write an answer before submitting.')
      return
    }
    setSubmitting(true)
    try {
      const result = await submitAnswer(session.session_id, currentQuestion.id, answer.trim())
      const answered = { question: currentQuestion, answer: answer.trim() }
      setQaRecord((prev) => [...prev, answered])
      setAnswer('')

      const next = result && result.next_question ? result.next_question : null
      if (next) {
        // Adaptive follow-up from the backend (or the next queued question).
        setQuestions((prev) => {
          const updated = [...prev]
          const nextIdx = currentIndex + 1
          if (updated[nextIdx] && updated[nextIdx].id === next.id) return updated
          updated.splice(nextIdx, 0, next)
          return updated
        })
        setCurrentIndex((i) => i + 1)
      } else if (currentIndex + 1 < questions.length) {
        setCurrentIndex((i) => i + 1)
      } else {
        // Last question answered — finish the session and show the summary.
        await handleFinish()
      }
    } catch (err) {
      setError(err.message || 'Failed to submit your answer.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleFinish() {
    setFinishing(true)
    setError('')
    try {
      const data = await finishSession(session.session_id)
      setSummary(data.summary || data)
    } catch (err) {
      setError(err.message || 'Failed to generate the summary.')
    } finally {
      setFinishing(false)
    }
  }

  const parsed = session?.parsed || null
  // skills and technologies overlap (e.g. Python appears in both lists) —
  // de-duplicate so React keys stay unique and chips are not shown twice.
  const skillChips = [
    ...new Set([...(parsed?.skills || []), ...(parsed?.technologies || [])]),
  ]

  return (
    <div className="page">
      <header className="header">
        <h1>InterviewLens</h1>
        <p className="subtitle">
          AI-powered role-based candidate screening. Your resume is parsed,
          skills are extracted, and interview questions are generated with RAG
          over ML textbooks — every question traces back to its source.
        </p>
      </header>

      <main className="container">
        {error && (
          <div className="alert alert-error" role="alert">
            <strong>Something went wrong:</strong> {error}
          </div>
        )}

        {/* ============ STEP 1: UPLOAD ============ */}
        {!session && (
          <section className="card">
            <h2>Start your interview</h2>
            <p className="muted">
              Upload your resume and pick a role. We parse the resume, extract
              your skills, and generate five interview questions grounded in
              the textbooks for that role.
            </p>

            {rolesError && (
              <div className="alert alert-warning" role="alert">
                {rolesError}
              </div>
            )}

            <form onSubmit={handleStart}>
              <label className="field-label" htmlFor="resume">
                Resume (.pdf or .txt)
              </label>
              <input
                id="resume"
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_TYPES}
                disabled={creating}
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
              {file && (
                <p className="file-name">
                  Selected: <strong>{file.name}</strong> (
                  {(file.size / 1024).toFixed(1)} KB)
                </p>
              )}

              <label className="field-label" htmlFor="role">
                Role
              </label>
              <select
                id="role"
                value={role}
                disabled={creating || rolesLoading}
                onChange={(e) => setRole(e.target.value)}
              >
                {roles.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.label}
                  </option>
                ))}
              </select>
              {selectedRole?.books?.length > 0 && (
                <p className="muted small">
                  Knowledge base: {selectedRole.books.join(', ')}
                </p>
              )}

              <button
                type="submit"
                className="btn btn-primary"
                disabled={creating || rolesLoading}
              >
                {creating ? 'Generating your interview…' : 'Start interview'}
              </button>
            </form>

            {creating && (
              <div className="generating" role="status">
                <div className="spinner" aria-hidden="true" />
                <p>
                  <strong>Generating your interview…</strong>
                  <br />
                  <span className="muted">
                    Parsing your resume, retrieving relevant textbook passages,
                    and generating questions with the model. This can take a
                    minute or two — please don&apos;t close this page.
                  </span>
                </p>
              </div>
            )}
          </section>
        )}

        {/* ============ STEP 2: INTERVIEW ============ */}
        {session && !summary && currentQuestion && (
          <section className="card">
            <div className="progress-row">
              <span className="progress-text">
                Question {currentIndex + 1} of {totalQuestions}
              </span>
              <span className="muted small">
                {session.parsed?.name ? `Candidate: ${session.parsed.name} · ` : ''}
                Role: {selectedRole?.label || role}
              </span>
            </div>
            <div
              className="progress-bar"
              role="progressbar"
              aria-valuenow={currentIndex + 1}
              aria-valuemin={1}
              aria-valuemax={totalQuestions}
            >
              <div
                className="progress-fill"
                style={{ width: `${((currentIndex + 1) / totalQuestions) * 100}%` }}
              />
            </div>

            {skillChips.length > 0 && (
              <div className="chips" aria-label="Skills extracted from your resume">
                <span className="chips-label">Skills extracted:</span>
                {skillChips.map((s) => (
                  <span key={s} className="chip">
                    {s}
                  </span>
                ))}
              </div>
            )}

            <span className="topic-tag">{currentQuestion.topic}</span>
            <h2 className="question-text">{currentQuestion.text}</h2>
            {currentQuestion.source && (
              <p className="source-line">
                Grounded in: <em>{currentQuestion.source}</em>
              </p>
            )}

            <form onSubmit={handleSubmitAnswer}>
              <label className="field-label" htmlFor="answer">
                Your answer
              </label>
              <textarea
                id="answer"
                rows={7}
                value={answer}
                disabled={submitting || finishing}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder="Explain your reasoning — concepts, trade-offs, and examples help."
              />
              <button
                type="submit"
                className="btn btn-primary"
                disabled={submitting || finishing}
              >
                {submitting
                  ? 'Submitting…'
                  : currentIndex + 1 === totalQuestions
                    ? 'Submit answer & finish'
                    : 'Submit answer'}
              </button>
            </form>

            {finishing && (
              <div className="generating" role="status">
                <div className="spinner" aria-hidden="true" />
                <p>
                  <strong>Preparing your summary…</strong>
                </p>
              </div>
            )}

            {qaRecord.length > 0 && (
              <details className="answered-so-far">
                <summary>
                  Answered so far ({qaRecord.length})
                </summary>
                <ol>
                  {qaRecord.map((item, i) => (
                    <li key={i}>
                      <strong>{item.question.text}</strong>
                      <p>{item.answer}</p>
                    </li>
                  ))}
                </ol>
              </details>
            )}
          </section>
        )}

        {/* ============ STEP 3: SUMMARY ============ */}
        {session && summary && (
          <section className="card">
            <h2>Interview summary</h2>
            <p className="muted">
              {summary.questions_asked != null && (
                <>
                  {summary.answered} of {summary.questions_asked} questions
                  answered.{' '}
                </>
              )}
              Role: {selectedRole?.label || role}
            </p>

            <div className="summary-grid">
              <div>
                <h3>Topics covered</h3>
                {summary.topics_covered?.length > 0 ? (
                  <ul>
                    {summary.topics_covered.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No topics recorded.</p>
                )}
              </div>
              <div>
                <h3>Overall</h3>
                <p>{summary.overall || 'No overall summary returned.'}</p>
              </div>
            </div>

            <p className="heuristic-note">
              Note: strengths and gaps below are basic heuristics — derived
              only from simple recorded signals such as answer length and
              keyword overlap with the source material. They are not scores
              and not a hiring decision.
            </p>

            <div className="summary-grid">
              <div>
                <h3>Strengths</h3>
                {summary.strengths?.length > 0 ? (
                  <ul>
                    {summary.strengths.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No strengths recorded.</p>
                )}
              </div>
              <div>
                <h3>Gaps</h3>
                {summary.gaps?.length > 0 ? (
                  <ul>
                    {summary.gaps.map((g, i) => (
                      <li key={i}>{g}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No gaps recorded.</p>
                )}
              </div>
            </div>

            <h3>Full Q&amp;A record</h3>
            <ol className="qa-list">
              {qaRecord.map((item, i) => (
                <li key={i} className="qa-item">
                  <p className="qa-question">
                    <span className="topic-tag small">{item.question.topic}</span>{' '}
                    {item.question.text}
                  </p>
                  {item.question.source && (
                    <p className="source-line small">
                      Grounded in: <em>{item.question.source}</em>
                    </p>
                  )}
                  <p className="qa-answer">{item.answer}</p>
                </li>
              ))}
            </ol>

            <button type="button" className="btn btn-secondary" onClick={resetAll}>
              Start new interview
            </button>
          </section>
        )}

        {/* Finish failed after the last answer: let the user retry. */}
        {session && !summary && !currentQuestion && !finishing && (
          <section className="card">
            <h2>All questions answered</h2>
            <p className="muted">
              Your answers are saved. The summary could not be generated —
              try again, or start a new interview.
            </p>
            <button type="button" className="btn btn-primary" onClick={handleFinish}>
              Generate summary
            </button>{' '}
            <button type="button" className="btn btn-secondary" onClick={resetAll}>
              Start new interview
            </button>
          </section>
        )}
      </main>

      <footer className="footer">
        InterviewLens — questions are generated by a model with retrieval over
        ML textbooks. No scores are invented; strengths and gaps are basic
        heuristics only.
      </footer>
    </div>
  )
}

export default App
