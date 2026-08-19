export interface AgentTraceEvent {
  agent: string;
  action: string;
  detail: string;
}

export interface AnalysisResponse {
  question: string;
  intent: string;
  answer: string;
  tool_result: Record<string, unknown> | null;
  investigation_result: Record<string, unknown> | null;
  trace: AgentTraceEvent[];
}

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export async function runAnalysis(question: string): Promise<AnalysisResponse> {
  const response = await fetch(`${apiBaseUrl}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : 'The analysis service is unavailable.');
  }
  return response.json() as Promise<AnalysisResponse>;
}
