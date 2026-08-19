'use client';

import { useState } from 'react';
import { ArrowUpRight, Bot, ChevronRight, CircleHelp, Database, PanelLeftClose, PanelLeftOpen, Send, Sparkles } from 'lucide-react';
import { evaluationQuestions } from '@/lib/questions';

const capabilities = [
  'Revenue & orders',
  'Store performance',
  'Channel mix',
  'SKU demand',
  'City decline',
  'Weekend comparison',
  'Festive impact',
  'Root-cause analysis',
];

export function InsightWorkspace() {
  const [question, setQuestion] = useState('');
  const [selectedQuestion, setSelectedQuestion] = useState<number | null>(null);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  function chooseQuestion(index: number) {
    setSelectedQuestion(index);
    setQuestion(evaluationQuestions[index]);
  }

  return (
    <main className={`app-shell ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <aside className="sidebar">
        <a className="brand" href="#top" aria-label="QSR Insight Studio home">
          <span className="brand-mark">Q</span><span>QSR Insight<br /><strong>Studio</strong></span>
        </a>
        <button
          className="sidebar-toggle"
          type="button"
          onClick={() => setIsSidebarCollapsed((value) => !value)}
          aria-label={isSidebarCollapsed ? 'Expand navigation' : 'Collapse navigation'}
          title={isSidebarCollapsed ? 'Expand navigation' : 'Collapse navigation'}
        >
          {isSidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
        <div className="sidebar-label">Analysis library</div>
        <nav aria-label="Analysis questions">
          {evaluationQuestions.map((item, index) => (
            <button className={`question-link ${selectedQuestion === index ? 'selected' : ''}`} key={item} onClick={() => chooseQuestion(index)}>
              <span>0{index + 1}</span><p>{item}</p><ChevronRight size={15} />
            </button>
          ))}
        </nav>
        <div className="data-note"><Database size={17} /><span><strong>Verified dataset</strong><br />20,000 orders · 50 stores</span></div>
      </aside>

      <section className="workspace" id="top">
        <header className="topbar">
          <div><span className="eyebrow">Operations intelligence</span><h1>Ask the business data.</h1></div>
          <button className="help-button"><CircleHelp size={17} /> How it works</button>
        </header>

        <div className="content">
          <section className="hero-card">
            <div className="hero-copy"><span className="agent-badge"><Sparkles size={14} /> Agentic QSR analytics</span><h2>Clear decisions, grounded in your operational data.</h2><p>Ask in plain English. The analysis engine chooses a verified tool, queries the workbook, and explains the result with supporting evidence.</p></div>
            <div className="hero-orbit" aria-hidden="true"><Bot size={42} /><span>AI</span></div>
          </section>

          <section className="suggestions" aria-labelledby="quick-start-heading">
            <div className="section-heading"><div><span className="eyebrow">Start here</span><h2 id="quick-start-heading">Recommended analyses</h2></div><span className="muted">8 evaluation-ready questions</span></div>
            <div className="marquee" aria-label="Recommended analyses">
              <div className="marquee-track">
                {[0, 1].map((copy) => (
                  <div className="marquee-group" key={copy} aria-hidden={copy === 1}>
                    {capabilities.map((capability, index) => (
                      <button
                        key={`${copy}-${capability}`}
                        onClick={() => chooseQuestion(index)}
                        className="suggestion"
                        tabIndex={copy === 1 ? -1 : undefined}
                      >
                        <span>0{index + 1}</span><strong>{capability}</strong><ArrowUpRight size={18} />
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </section>
        </div>

        <form className="composer" onSubmit={(event) => event.preventDefault()}>
          <label htmlFor="question">What would you like to understand?</label>
          <div className="input-row"><input id="question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="e.g. Which cities are losing revenue?" /><button type="submit" disabled={!question.trim()} aria-label="Run analysis"><Send size={19} /></button></div>
          <p>Every answer will show the agent path and dataset evidence.</p>
        </form>
      </section>
    </main>
  );
}
