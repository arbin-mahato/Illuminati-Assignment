'use client';

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { AnalysisResponse } from '@/lib/api';

type RecordValue = Record<string, unknown>;
const COLORS = ['#003082', '#4f79c7', '#2f9b77', '#7c58bb'];

const isRecord = (value: unknown): value is RecordValue => typeof value === 'object' && value !== null && !Array.isArray(value);
const rows = (value: unknown): RecordValue[] => Array.isArray(value) ? value.filter(isRecord) : [];
const currency = (value: unknown, compact = false) => typeof value === 'number' ? new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', notation: compact ? 'compact' : 'standard', maximumFractionDigits: compact ? 1 : 2 }).format(value) : '—';
const number = (value: unknown) => typeof value === 'number' ? new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(value) : '—';

export function InsightPanels({ response }: { response: AnalysisResponse }) {
  const result = response.tool_result ?? response.investigation_result;
  if (!result) return null;
  switch (response.intent) {
    case 'OVERALL_METRICS': return <Overall result={result} />;
    case 'SKU_PERFORMANCE': return <Skus result={result} />;
    case 'CHANNEL_PERFORMANCE': return <Channels result={result} />;
    case 'STORE_RANKINGS': return <div className="data-grid"><DataTable title="Top five stores by revenue" data={rows(result.top_stores)} columns={storeColumns} /><DataTable title="Bottom five stores by revenue" data={rows(result.bottom_stores)} columns={storeColumns} /></div>;
    case 'CITY_REVENUE_TRENDS': return <DataTable title="Cities with May–July revenue decline" data={rows(result.declining_cities)} columns={[["city", "City"], ["pct_change", "May–July change"]]} />;
    case 'WEEKEND_VS_WEEKDAY': return <Segments title="Weekend versus weekday" data={rows(result.segments)} nameKey="day_type" />;
    case 'FESTIVE_VS_NORMAL': return <Segments title="Festive-period performance" data={rows(result.periods)} nameKey="period" />;
    case 'STORE_DECLINE_DIAGNOSIS': return <><MetricGrid cards={[["Declining stores", number(result.declining_store_count), "Strict month-over-month revenue decline"]]} /><DataTable title="Consistently declining stores" data={rows(result.stores)} columns={[["store_name", "Store"], ["city", "City"], ["first_month_revenue", "May"], ["second_month_revenue", "June"], ["final_month_revenue", "July"], ["revenue_change_pct", "Change"]]} /></>;
    default: return null;
  }
}

function Overall({ result }: { result: RecordValue }) {
  const data = rows(result.monthly_breakdown);
  return <><MetricGrid cards={[["3-month revenue", currency(result.total_revenue), "Net revenue across the period"], ["Total orders", number(result.total_orders), "Unique billed transactions"], ["Average order value", currency(result.average_order_value), "Net revenue per order"]]} /><Chart title="Monthly revenue trend" data={data} dataKey="revenue" nameKey="month" /><DataTable title="Monthly breakdown" data={data} columns={[["month", "Month"], ["revenue", "Revenue"], ["orders", "Orders"], ["average_order_value", "AOV"]]} /></>;
}

function Skus({ result }: { result: RecordValue }) {
  const revenue = rows(result.top_by_revenue);
  return <><Chart title="Top SKUs by revenue" data={revenue} dataKey="revenue" nameKey="sku_name" horizontal /><div className="data-grid"><DataTable title="Top SKUs by quantity" data={rows(result.top_by_quantity)} columns={skuColumns} /><DataTable title="Top SKUs by revenue" data={revenue} columns={skuColumns} /></div></>;
}

function Channels({ result }: { result: RecordValue }) {
  const data = rows(result.channels);
  return <><Chart title="Channel revenue" data={data} dataKey="revenue" nameKey="channel" colors /><DataTable title="Channel performance" data={data} columns={[["channel", "Channel"], ["revenue", "Revenue"], ["orders", "Orders"], ["average_order_value", "AOV"], ["revenue_share_pct", "Revenue share"]]} /></>;
}

function Segments({ title, data, nameKey }: { title: string; data: RecordValue[]; nameKey: string }) { return <><Chart title={title} data={data} dataKey="revenue" nameKey={nameKey} /><DataTable title="Verified comparison" data={data} columns={[[nameKey, "Segment"], ["revenue", "Revenue"], ["orders", "Orders"], ["average_order_value", "AOV"], ["average_daily_revenue", "Daily revenue"]]} /></>; }

function Chart({ title, data, dataKey, nameKey, horizontal = false, colors = false }: { title: string; data: RecordValue[]; dataKey: string; nameKey: string; horizontal?: boolean; colors?: boolean }) {
  return <section className="evidence-panel chart-panel"><h3>{title}</h3><ResponsiveContainer width="100%" height={270}><BarChart data={data} layout={horizontal ? 'vertical' : 'horizontal'} margin={horizontal ? { left: 30 } : undefined}><CartesianGrid vertical={horizontal} horizontal={!horizontal} stroke="#e1e5dc" />{horizontal ? <><XAxis type="number" tickFormatter={(value) => currency(value, true)} tickLine={false} axisLine={false} /><YAxis type="category" dataKey={nameKey} width={125} tickLine={false} axisLine={false} /></> : <><XAxis dataKey={nameKey} tickLine={false} axisLine={false} /><YAxis tickFormatter={(value) => currency(value, true)} tickLine={false} axisLine={false} width={72} /></>}<Tooltip formatter={(value) => currency(value)} /><Bar dataKey={dataKey} fill={COLORS[0]} radius={horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0]}>{colors && data.map((row, index) => <Cell key={String(row[nameKey])} fill={COLORS[index % COLORS.length]} />)}</Bar></BarChart></ResponsiveContainer></section>;
}

function MetricGrid({ cards }: { cards: string[][] }) { return <div className="metric-grid">{cards.map(([label, value, note]) => <article className="metric-card" key={label}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>)}</div>; }
function DataTable({ title, data, columns }: { title: string; data: RecordValue[]; columns: [string, string][] }) { return <section className="evidence-panel table-panel"><h3>{title}</h3><div className="table-wrap"><table><thead><tr>{columns.map(([key, header]) => <th className={isNumeric(key) ? 'numeric' : ''} key={header}>{header}</th>)}</tr></thead><tbody>{data.map((row, index) => <tr key={`${String(row[columns[0][0]])}-${index}`}>{columns.map(([key]) => <td className={isNumeric(key) ? 'numeric' : ''} key={key}>{format(key, row[key])}</td>)}</tr>)}</tbody></table></div></section>; }
function format(key: string, value: unknown) { if (key.includes('revenue') || key === 'average_order_value') return currency(value); if (key.includes('pct') || key.includes('share') || key === 'change') return typeof value === 'number' ? `${value.toFixed(2)}%` : '—'; if (key === 'orders' || key.includes('quantity')) return number(value); return String(value ?? '—'); }
function isNumeric(key: string) { return key.includes('revenue') || key.includes('pct') || key.includes('share') || key.includes('quantity') || key === 'orders' || key === 'average_order_value' || key === 'change'; }

const skuColumns: [string, string][] = [["sku_name", "SKU"], ["category", "Category"], ["quantity_sold", "Quantity"], ["revenue", "Revenue"]];
const storeColumns: [string, string][] = [["store_name", "Store"], ["city", "City"], ["revenue", "Revenue"], ["orders", "Orders"], ["average_order_value", "AOV"]];
