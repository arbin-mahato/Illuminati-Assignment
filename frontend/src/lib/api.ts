export interface AgentTraceEvent {
  agent: string;
  action: string;
  detail: string;
}

export interface AnalysisResponse {
  question: string;
  intent: string;
  answer: string;
  insight: InsightContent | null;
  tool_result: Record<string, unknown> | null;
  investigation_result: Record<string, unknown> | null;
  trace: AgentTraceEvent[];
}

export interface InsightContent {
  headline: string;
  summary: string;
  key_findings: string[];
  recommended_actions: string[];
  caveat: string;
}

export interface ProgressEvent {
  agent: string;
  status: 'working' | 'complete';
  detail: string;
}

export interface ConversationContextTurn {
  role: 'user' | 'assistant';
  content: string;
  intent?: string;
}

export interface AnalysisRequestContext {
  sessionId: string;
  history: ConversationContextTurn[];
}

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export async function runAnalysis(question: string, context?: AnalysisRequestContext): Promise<AnalysisResponse> {
  const response = await fetch(`${apiBaseUrl}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, session_id: context?.sessionId, history: context?.history ?? [] }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : 'The analysis service is unavailable.');
  }
  return response.json() as Promise<AnalysisResponse>;
}

export async function streamAnalysis(
  question: string,
  onProgress: (event: ProgressEvent) => void,
  context?: AnalysisRequestContext,
): Promise<AnalysisResponse> {
  const response = await fetch(`${apiBaseUrl}/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ question, session_id: context?.sessionId, history: context?.history ?? [] }),
  });
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : 'The analysis service is unavailable.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalResponse: AnalysisResponse | null = null;
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const events = buffer.split('\n\n');
    buffer = events.pop() ?? '';
    for (const eventBlock of events) {
      const eventName = eventBlock.match(/^event: (.+)$/m)?.[1];
      const data = eventBlock.match(/^data: (.+)$/m)?.[1];
      if (!eventName || !data) continue;
      const payload: unknown = JSON.parse(data);
      if (eventName === 'progress') onProgress(payload as ProgressEvent);
      if (eventName === 'final') finalResponse = payload as AnalysisResponse;
      if (eventName === 'error') throw new Error((payload as { detail?: string }).detail ?? 'Analysis could not be completed.');
    }
    if (done) break;
  }
  if (!finalResponse) throw new Error('The analysis stream ended before returning a result.');
  return finalResponse;
}
