import { useState } from "react";
import { askFinanceQuestion } from "../api/client";

export default function FinanceQAPage({ sourceBatch }) {
  const [question, setQuestion] = useState("Why did cash decrease this week?");
  const [answer, setAnswer] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault(); setLoading(true); setError("");
    try { setAnswer(await askFinanceQuestion(question, sourceBatch)); }
    catch (requestError) { setError(requestError.message); }
    finally { setLoading(false); }
  }
  return <div className="page-stack qa-page">
    <header className="page-header"><div><p className="eyebrow">FINANCE Q&amp;A</p><h1>Ask the ledger, not a chatbot</h1><p>Answers are grounded in current database and reconciliation evidence.</p></div></header>
    <form className="surface qa-form" onSubmit={submit}>
      <label htmlFor="finance-question">Question</label>
      <div><input id="finance-question" value={question} onChange={(event) => setQuestion(event.target.value)} minLength="3" maxLength="500" required />
      <button className="button button--primary" disabled={loading}>{loading ? "Analyzing…" : "Ask finance"}</button></div>
    </form>
    {error && <div className="alert alert--error">{error}</div>}
    {answer && <section className="surface qa-answer">
      <div className="section-heading"><div><p className="eyebrow">EVIDENCE-BACKED ANSWER</p><h2>{answer.generated_by === "llm" ? "AI synthesis" : "Database summary"}</h2></div><span>{new Date(answer.as_of).toLocaleString()}</span></div>
      <p className="qa-answer__copy">{answer.answer}</p>
      <div className="evidence-grid">{answer.evidence.map((item) => <article key={item.label}><span>{item.label}</span><strong>{item.value}</strong><small>{item.source}</small></article>)}</div>
    </section>}
  </div>;
}
