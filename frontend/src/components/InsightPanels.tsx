import { AnalysisResponse } from '@/lib/api';

type RecordValue = Record<string, unknown>;

function isRecord(value: unknown): value is RecordValue {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function currency(value: unknown): string {
  return typeof value === 'number' ? new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(value) : '—';
}

function number(value: unknown): string {
  return typeof value === 'number' ? new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(value) : '—';
}

function labelFromIntent(intent: string): string {
  return intent.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function InsightPanels({ response }: { response: AnalysisResponse }) {
  const result = response.tool_result ?? response.investigation_result;
  if (!result) return null;
  const monthly = Array.isArray(result.monthly_breakdown) ? result.monthly_breakdown.filter(isRecord) : [];
  const cards = response.intent === 'OVERALL_METRICS'
    ? [
        ['3-month revenue', currency(result.total_revenue), 'Net revenue across the period'],
        ['Total orders', number(result.total_orders), 'Unique billed transactions'],
        ['Average order value', currency(result.average_order_value), 'Net revenue per order'],
      ]
    : response.intent === 'STORE_DECLINE_DIAGNOSIS'
      ? [['Declining stores', number(result.declining_store_count), 'Strict month-over-month decline']]
      : [];

  return (
    <div className="insight-panels">
      {cards.length > 0 && <div className="metric-grid">{cards.map(([label, value, note]) => <article className="metric-card" key={label}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>)}</div>}
      {monthly.length > 0 && <MonthlyTrend rows={monthly} />}
      <EvidenceTable intent={response.intent} result={result} />
    </div>
  );
}

function MonthlyTrend({ rows }: { rows: RecordValue[] }) {
  const maximum = Math.max(...rows.map((row) => Number(row.revenue) || 0));
  return <section className="evidence-panel"><h3>Monthly revenue trend</h3><div className="bar-chart">{rows.map((row) => <div className="bar-column" key={String(row.month)}><span>{currency(row.revenue)}</span><i style={{ height: `${Math.max(12, (Number(row.revenue) / maximum) * 100)}%` }} /><strong>{String(row.month)}</strong></div>)}</div><SimpleTable rows={rows} columns={[['month', 'Month'], ['revenue', 'Revenue'], ['orders', 'Orders'], ['average_order_value', 'AOV']]} /></section>;
}

function EvidenceTable({ intent, result }: { intent: string; result: RecordValue }) {
  let rows: RecordValue[] = [];
  let title = 'Verified evidence';
  let columns: [string, string][] = [];
  if (intent === 'CHANNEL_PERFORMANCE') { rows = arrayRecords(result.channels); title = 'Channel performance'; columns = [['channel', 'Channel'], ['revenue', 'Revenue'], ['orders', 'Orders'], ['average_order_value', 'AOV'], ['revenue_share_pct', 'Share %']]; }
  if (intent === 'STORE_RANKINGS') { rows = arrayRecords(result.top_stores); title = 'Top five stores by revenue'; columns = [['store_name', 'Store'], ['city', 'City'], ['revenue', 'Revenue'], ['orders', 'Orders'], ['average_order_value', 'AOV']]; }
  if (intent === 'SKU_PERFORMANCE') { rows = arrayRecords(result.top_by_revenue); title = 'Top SKUs by revenue'; columns = [['sku_name', 'SKU'], ['category', 'Category'], ['quantity_sold', 'Quantity'], ['revenue', 'Revenue']]; }
  if (intent === 'CITY_REVENUE_TRENDS') { rows = arrayRecords(result.declining_cities); title = 'Cities with declining revenue'; columns = [['city', 'City'], ['pct_change', 'May–Jul change %']]; }
  if (intent === 'WEEKEND_VS_WEEKDAY') { rows = arrayRecords(result.segments); title = 'Weekend versus weekday'; columns = [['day_type', 'Day type'], ['revenue', 'Revenue'], ['orders', 'Orders'], ['average_order_value', 'AOV'], ['average_daily_revenue', 'Daily revenue']]; }
  if (intent === 'FESTIVE_VS_NORMAL') { rows = arrayRecords(result.periods); title = 'Festive-period comparison'; columns = [['period', 'Period'], ['revenue', 'Revenue'], ['orders', 'Orders'], ['average_order_value', 'AOV'], ['average_daily_revenue', 'Daily revenue']]; }
  if (intent === 'STORE_DECLINE_DIAGNOSIS') { rows = arrayRecords(result.stores); title = 'Consistently declining stores'; columns = [['store_name', 'Store'], ['city', 'City'], ['first_month_revenue', 'May'], ['second_month_revenue', 'June'], ['final_month_revenue', 'July'], ['revenue_change_pct', 'Change %']]; }
  return rows.length > 0 ? <section className="evidence-panel"><h3>{title}</h3><SimpleTable rows={rows} columns={columns} /></section> : null;
}

function SimpleTable({ rows, columns }: { rows: RecordValue[]; columns: [string, string][] }) {
  return <div className="table-wrap"><table><thead><tr>{columns.map(([, title]) => <th key={title}>{title}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={`${String(row[columns[0][0]])}-${index}`}>{columns.map(([key]) => <td key={key}>{formatValue(key, row[key])}</td>)}</tr>)}</tbody></table></div>;
}

function formatValue(key: string, value: unknown): string {
  if (key.includes('revenue') || key === 'average_order_value' || key === 'aov') return currency(value);
  if (key.includes('pct') || key.includes('share')) return typeof value === 'number' ? `${value.toFixed(2)}%` : '—';
  if (key === 'orders' || key.includes('quantity')) return number(value);
  return String(value ?? '—');
}

function arrayRecords(value: unknown): RecordValue[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}
