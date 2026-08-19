'use client';

import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { AnalysisResponse } from '@/lib/api';

type Row = Record<string, unknown>;
type Column = [string, string];
const colors = ['#003082', '#4f79c7', '#2f9b77', '#7c58bb'];
const isRow = (value: unknown): value is Row => typeof value === 'object' && value !== null && !Array.isArray(value);
const toRows = (value: unknown): Row[] => Array.isArray(value) ? value.filter(isRow) : [];
const money = (value: unknown, compact = false) => typeof value === 'number' ? new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', notation: compact ? 'compact' : 'standard', maximumFractionDigits: compact ? 1 : 2 }).format(value) : '—';
const count = (value: unknown) => typeof value === 'number' ? new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(value) : '—';

export function InsightPanels({ response }: { response: AnalysisResponse }) {
  const result = response.tool_result ?? response.investigation_result;
  if (!result) return null;
  if (response.intent === 'OVERALL_METRICS') return <Overall result={result} />;
  if (response.intent === 'STORE_RANKINGS') return <Rankings result={result} />;
  if (response.intent === 'CHANNEL_PERFORMANCE') return <Channels result={result} />;
  if (response.intent === 'SKU_PERFORMANCE') return <Skus result={result} />;
  if (response.intent === 'CITY_REVENUE_TRENDS') return <Cities result={result} />;
  if (response.intent === 'WEEKEND_VS_WEEKDAY') return <Segments title="Weekend versus weekday" rows={toRows(result.segments)} nameKey="day_type" />;
  if (response.intent === 'FESTIVE_VS_NORMAL') return <Segments title="Festive-period performance" rows={toRows(result.periods)} nameKey="period" />;
  if (response.intent === 'STORE_DECLINE_DIAGNOSIS') return <Declines result={result} />;
  return null;
}

function Overall({ result }: { result: Row }) {
  const monthly = toRows(result.monthly_breakdown);
  return <Dashboard><MetricGrid cards={[["3-month revenue", money(result.total_revenue), "Net revenue across the period"], ["Total orders", count(result.total_orders), "Unique billed transactions"], ["Average order value", money(result.average_order_value), "Net revenue per order"]]} /><BarPanel title="Monthly revenue trend" rows={monthly} dataKey="revenue" nameKey="month" /><DataTable title="Monthly breakdown" rows={monthly} columns={[["month", "Month"], ["revenue", "Revenue"], ["orders", "Orders"], ["average_order_value", "AOV"]]} /></Dashboard>;
}

function Rankings({ result }: { result: Row }) {
  const top = toRows(result.top_stores); const bottom = toRows(result.bottom_stores);
  return <Dashboard><BarPanel title="Top store revenue ranking" rows={top} dataKey="revenue" nameKey="store_name" horizontal /><div className="data-grid"><DataTable title="Top five stores by revenue" rows={top} columns={storeColumns} /><DataTable title="Bottom five stores by revenue" rows={bottom} columns={storeColumns} /></div></Dashboard>;
}

function Channels({ result }: { result: Row }) {
  const channels = toRows(result.channels); const leader = channels[0] ?? {};
  return <Dashboard><MetricGrid cards={[["Leading channel", String(leader.channel ?? '—'), `${money(leader.revenue)} revenue`], ["Leading channel AOV", money(leader.average_order_value), "Average order value"], ["Channels analysed", count(channels.length), "Sales channels"]]} /><BarPanel title="Channel revenue" rows={channels} dataKey="revenue" nameKey="channel" colors /><DataTable title="Channel performance" rows={channels} columns={[["channel", "Channel"], ["revenue", "Revenue"], ["orders", "Orders"], ["average_order_value", "AOV"], ["revenue_share_pct", "Revenue share"]]} /></Dashboard>;
}

function Skus({ result }: { result: Row }) {
  const revenue = toRows(result.top_by_revenue);
  return <Dashboard><BarPanel title="Top SKUs by revenue" rows={revenue} dataKey="revenue" nameKey="sku_name" horizontal /><div className="data-grid"><DataTable title="Top SKUs by quantity" rows={toRows(result.top_by_quantity)} columns={skuColumns} /><DataTable title="Top SKUs by revenue" rows={revenue} columns={skuColumns} /></div></Dashboard>;
}

function Cities({ result }: { result: Row }) {
  const trends = toRows(result.city_trends); const months = trends.length && isRow(trends[0].monthly_revenue) ? Object.keys(trends[0].monthly_revenue) : [];
  const chartRows = months.map((month) => Object.fromEntries([['month', month], ...trends.map((trend) => [String(trend.city), isRow(trend.monthly_revenue) ? Number(trend.monthly_revenue[month]) : 0])]));
  return <Dashboard><section className="evidence-panel chart-panel"><h3>City revenue trend</h3><ResponsiveContainer width="100%" height={280}><LineChart data={chartRows}><CartesianGrid stroke="#e1e5dc" /><XAxis dataKey="month" tickLine={false} axisLine={false} /><YAxis tickFormatter={(value) => money(value, true)} width={72} tickLine={false} axisLine={false} /><Tooltip formatter={(value) => money(value)} /><Legend />{trends.map((trend, index) => <Line key={String(trend.city)} type="monotone" dataKey={String(trend.city)} stroke={colors[index % colors.length]} strokeWidth={2.5} dot={{ r: 3 }} />)}</LineChart></ResponsiveContainer></section><DataTable title="Cities with May–July revenue decline" rows={toRows(result.declining_cities)} columns={[["city", "City"], ["pct_change", "May–July change"]]} /></Dashboard>;
}

function Segments({ title, rows, nameKey }: { title: string; rows: Row[]; nameKey: string }) { return <Dashboard><BarPanel title={title} rows={rows} dataKey="revenue" nameKey={nameKey} /><DataTable title="Verified comparison" rows={rows} columns={[[nameKey, "Segment"], ["revenue", "Revenue"], ["orders", "Orders"], ["average_order_value", "AOV"], ["average_daily_revenue", "Daily revenue"]]} /></Dashboard>; }

function Declines({ result }: { result: Row }) {
  const stores = toRows(result.stores); const investigations = toRows(result.investigations); const steepest = stores[0] ?? {};
  return <Dashboard><MetricGrid cards={[["Declining stores", count(result.declining_store_count), "Strict month-over-month decline"], ["Steepest decline", String(steepest.store_name ?? '—'), `${format('revenue_change_pct', steepest.revenue_change_pct)} May–July`], ["Evidence checked", count(investigations.length), "Store investigations completed"]]} /><DataTable title="Consistently declining stores" rows={stores} columns={[["store_name", "Store"], ["city", "City"], ["first_month_revenue", "May"], ["second_month_revenue", "June"], ["final_month_revenue", "July"], ["revenue_change_pct", "Change"]]} /><section className="driver-grid">{investigations.map((investigation, index) => <DriverCard key={`${String(investigation.observed_driver)}-${index}`} row={investigation} />)}</section></Dashboard>;
}

function DriverCard({ row }: { row: Row }) {
  const store = isRow(row.store) ? row.store : {};
  return <details className="driver-card"><summary><span><strong>{String(store.store_name ?? 'Store investigation')}</strong><small>{String(store.city ?? '')} · {format('revenue_change_pct', store.revenue_change_pct)} revenue change</small></span><span>View evidence</span></summary><p>{String(row.observed_driver ?? '')}</p><div className="driver-metrics"><span><small>Order change</small><strong>{format('order_change_pct', store.order_change_pct)}</strong></span><span><small>AOV change</small><strong>{format('average_order_value_change_pct', store.average_order_value_change_pct)}</strong></span></div><DataTable title="Leading channel changes" rows={toRows(row.channel_changes).slice(0, 3)} columns={[["channel", "Channel"], ["first_month_revenue", "May"], ["final_month_revenue", "July"], ["revenue_change_pct", "Change"]]} /></details>;
}

function Dashboard({ children }: { children: React.ReactNode }) { return <div className="insight-panels">{children}</div>; }
function MetricGrid({ cards }: { cards: string[][] }) { return <div className="metric-grid">{cards.map(([label, value, note]) => <article className="metric-card" key={label}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>)}</div>; }
function BarPanel({ title, rows, dataKey, nameKey, horizontal = false, colors: useColors = false }: { title: string; rows: Row[]; dataKey: string; nameKey: string; horizontal?: boolean; colors?: boolean }) { return <section className="evidence-panel chart-panel"><h3>{title}</h3><ResponsiveContainer width="100%" height={270}><BarChart data={rows} layout={horizontal ? 'vertical' : 'horizontal'} margin={horizontal ? { left: 34 } : undefined}><CartesianGrid vertical={horizontal} horizontal={!horizontal} stroke="#e1e5dc" />{horizontal ? <><XAxis type="number" tickFormatter={(value) => money(value, true)} tickLine={false} axisLine={false} /><YAxis type="category" dataKey={nameKey} width={128} tickLine={false} axisLine={false} /></> : <><XAxis dataKey={nameKey} tickLine={false} axisLine={false} /><YAxis tickFormatter={(value) => money(value, true)} tickLine={false} axisLine={false} width={72} /></>}<Tooltip formatter={(value) => money(value)} /><Bar dataKey={dataKey} fill={colors[0]} radius={horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0]}>{useColors && rows.map((row, index) => <Cell key={String(row[nameKey])} fill={colors[index % colors.length]} />)}</Bar></BarChart></ResponsiveContainer></section>; }
function DataTable({ title, rows, columns }: { title: string; rows: Row[]; columns: Column[] }) { return <section className="evidence-panel table-panel"><h3>{title}</h3><div className="table-wrap"><table><thead><tr>{columns.map(([key, title]) => <th className={numeric(key) ? 'numeric' : ''} key={title}>{title}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={`${String(row[columns[0][0]])}-${index}`}>{columns.map(([key]) => <td className={numeric(key) ? 'numeric' : ''} key={key}>{format(key, row[key])}</td>)}</tr>)}</tbody></table></div></section>; }
function format(key: string, value: unknown) { if (key.includes('revenue') || key === 'average_order_value') return money(value); if (key.includes('pct') || key.includes('share') || key === 'change') return typeof value === 'number' ? `${value.toFixed(2)}%` : '—'; if (key === 'orders' || key.includes('quantity')) return count(value); return String(value ?? '—'); }
function numeric(key: string) { return key.includes('revenue') || key.includes('pct') || key.includes('share') || key.includes('quantity') || key === 'orders' || key === 'average_order_value' || key === 'change'; }

const skuColumns: Column[] = [["sku_name", "SKU"], ["category", "Category"], ["quantity_sold", "Quantity"], ["revenue", "Revenue"]];
const storeColumns: Column[] = [["store_name", "Store"], ["city", "City"], ["revenue", "Revenue"], ["orders", "Orders"], ["average_order_value", "AOV"]];
