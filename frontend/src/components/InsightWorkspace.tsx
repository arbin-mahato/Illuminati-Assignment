'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Bot, ChevronRight, CircleHelp, Database, LoaderCircle, PanelLeftClose, PanelLeftOpen, Send, Sparkles, UserRound } from 'lucide-react';
import { AnalysisResponse, ProgressEvent, streamAnalysis } from '@/lib/api';
import { InsightPanels } from '@/components/InsightPanels';
import { evaluationQuestions } from '@/lib/questions';

const capabilities = ['Revenue & orders', 'Store performance', 'Channel mix', 'SKU demand', 'City decline', 'Weekend comparison', 'Festive impact', 'Root-cause analysis'];

type ConversationItem = { id: string; role: 'user' | 'assistant'; content?: string; progress?: ProgressEvent[]; response?: AnalysisResponse; };

export function InsightWorkspace() {
  const [question, setQuestion] = useState('');
  const [selectedQuestion, setSelectedQuestion] = useState<number | null>(null);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [messages, setMessages] = useState<ConversationItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const contentEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => { contentEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, isLoading]);

  function chooseQuestion(index: number) { setSelectedQuestion(index); setQuestion(evaluationQuestions[index]); }

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submittedQuestion = question.trim();
    if (!submittedQuestion || isLoading) return;
    const assistantId = `assistant-${Date.now()}`;
    setError(null); setQuestion(''); setIsLoading(true);
    setMessages((current) => [...current, { id: `user-${Date.now()}`, role: 'user', content: submittedQuestion }, { id: assistantId, role: 'assistant', progress: [] }]);
    try {
      const response = await streamAnalysis(submittedQuestion, (progress) => {
        setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, progress: [...(message.progress ?? []), progress] } : message));
      });
      setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, response } : message));
    } catch (requestError) {
      setMessages((current) => current.filter((message) => message.id !== assistantId));
      setError(requestError instanceof Error ? requestError.message : 'Unable to complete analysis.');
    } finally { setIsLoading(false); }
  }

  const hasConversation = messages.length > 0;
  return <main className={`app-shell ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
    <aside className="sidebar">
      <a className="brand" href="#top" aria-label="QSR Insight Studio home"><span className="brand-mark">Q</span><span>QSR Insight<br /><strong>Studio</strong></span></a>
      <button className="sidebar-toggle" type="button" onClick={() => setIsSidebarCollapsed((value) => !value)} aria-label={isSidebarCollapsed ? 'Expand navigation' : 'Collapse navigation'}>{isSidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}</button>
      <div className="sidebar-label">Analysis library</div>
      <nav aria-label="Analysis questions">{evaluationQuestions.map((item, index) => <button className={`question-link ${selectedQuestion === index ? 'selected' : ''}`} key={item} onClick={() => chooseQuestion(index)}><span>0{index + 1}</span><p>{item}</p><ChevronRight size={15} /></button>)}</nav>
      <div className="data-note"><Database size={17} /><span><strong>Verified dataset</strong><br />20,000 orders · 50 stores</span></div>
    </aside>
    <section className="workspace" id="top">
      <header className="topbar"><div><span className="eyebrow">Operations intelligence</span><h1>{hasConversation ? 'Intelligence session' : 'Ask the business data.'}</h1></div><button className="help-button"><CircleHelp size={17} /> How it works</button></header>
      <div className={`content ${hasConversation ? 'conversation-content' : ''}`}>
        {!hasConversation ? <Landing onChoose={chooseQuestion} /> : <Conversation messages={messages} />}
        {error && <p className="error-message" role="alert">{error}</p>}<div ref={contentEndRef} />
      </div>
      <form className="composer" onSubmit={submitQuestion}>
        <label htmlFor="question">What would you like to understand?</label>
        <div className="input-row"><input id="question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask a question about stores, revenue, demand, or performance…" disabled={isLoading} /><button type="submit" disabled={!question.trim() || isLoading} aria-label="Run analysis">{isLoading ? <LoaderCircle className="spin" size={19} /> : <Send size={19} />}</button></div>
        <p>Agent progress, verified calculations, and supporting evidence appear in every response.</p>
      </form>
    </section>
  </main>;
}

function Landing({ onChoose }: { onChoose: (index: number) => void }) {
  return <><section className="hero-card"><div className="hero-copy"><span className="agent-badge"><Sparkles size={14} /> Agentic QSR analytics</span><h2>Clear decisions, grounded in your operational data.</h2><p>Groq interprets the business question and composes the insight. Verified DuckDB tools calculate every number from the workbook.</p></div><div className="hero-orbit" aria-hidden="true"><Bot size={42} /><span>AI</span></div></section><section className="suggestions" aria-labelledby="quick-start-heading"><div className="section-heading"><div><span className="eyebrow">Start here</span><h2 id="quick-start-heading">Recommended analyses</h2></div><span className="muted">8 evaluation-ready questions</span></div><div className="marquee" aria-label="Recommended analyses"><div className="marquee-track">{[0, 1].map((copy) => <div className="marquee-group" key={copy} aria-hidden={copy === 1}>{capabilities.map((capability, index) => <button key={`${copy}-${capability}`} onClick={() => onChoose(index)} className="suggestion" tabIndex={copy === 1 ? -1 : undefined}><span>0{index + 1}</span><strong>{capability}</strong><ArrowUpRight size={18} /></button>)}</div>)}</div></div></section></>;
}

function Conversation({ messages }: { messages: ConversationItem[] }) {
  return <section className="conversation" aria-live="polite">{messages.map((message) => message.role === 'user' ? <article className="message user-message" key={message.id}><div><span className="message-label">Your question</span><p>{message.content}</p></div><span className="message-avatar"><UserRound size={17} /></span></article> : <article className="message agent-message" key={message.id}><span className="message-avatar agent-avatar"><Bot size={18} /></span><div className="agent-response"><div className="message-label">QSR Insight Agent</div>{message.response ? <><div className="answer-card"><div className="result-label"><span>Verified insight</span><span>{message.response.intent.replaceAll('_', ' ')}</span></div><h2>{message.response.answer}</h2><Trace progress={message.progress ?? []} /></div><InsightPanels response={message.response} /></> : <Progress progress={message.progress ?? []} />}</div></article>)}</section>;
}

function Progress({ progress }: { progress: ProgressEvent[] }) { const latest = progress.at(-1); return <div className="progress-card"><LoaderCircle className="spin" size={20} /><div><strong>{latest?.detail ?? 'Starting the analysis…'}</strong><p>Streaming the agent workflow in real time.</p></div><Trace progress={progress} /></div>; }
function Trace({ progress }: { progress: ProgressEvent[] }) { return progress.length > 0 ? <div className="trace-list">{progress.map((event, index) => <span className={event.status} key={`${event.agent}-${event.status}-${index}`}><strong>{event.agent}</strong> · {event.detail}</span>)}</div> : null; }
