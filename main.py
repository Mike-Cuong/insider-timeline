import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Check,
  CircleHelp,
  Clock3,
  Database,
  ExternalLink,
  FileText,
  Landmark,
  LoaderCircle,
  Search,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import {
  getGetInsiderActivityQueryKey,
  getSearchCompaniesQueryKey,
  useGetInsiderActivity,
  useSearchCompanies,
} from '@workspace/api-client-react';
import type { InsiderTransaction } from '@workspace/api-client-react';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';

const queryClient = new QueryClient();
const QUICK_SEARCHES = ['NVDA', 'MSFT', 'AAPL'];
const PERIODS = [30, 90, 180, 365];
type ActivityFilter = 'all' | 'purchase' | 'sale' | 'award';

function money(value: number | null | undefined, compact = false) {
  if (value == null) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: compact && Math.abs(value) >= 1000000 ? 'compact' : 'standard',
    maximumFractionDigits: Math.abs(value) >= 1000 ? 0 : 2,
  }).format(value);
}

function number(value: number | null | undefined) {
  if (value == null) return '—';
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value);
}

function shortDate(value: string | null | undefined) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).format(date);
}

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase();
}

function readInitialReport() {
  const params = new URLSearchParams(window.location.search);
  const rawSymbol = params.get('symbol')?.trim().toUpperCase() ?? '';
  const symbol = /^[A-Z][A-Z0-9.-]{0,11}$/.test(rawSymbol) ? rawSymbol : '';
  const requestedDays = Number(params.get('days'));
  return {
    symbol,
    days: PERIODS.includes(requestedDays) ? requestedDays : 90,
  };
}

function TimelineChart({ transactions, days }: { transactions: InsiderTransaction[]; days: number }) {
  const buckets = useMemo(() => {
    const bucketCount = Math.min(12, Math.ceil(days / 30) + 1);
    const result = Array.from({ length: bucketCount }, () => ({ label: '', purchase: 0, sale: 0 }));
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth() - bucketCount + 1, 1);
    transactions.forEach((transaction) => {
      if (transaction.transactionType !== 'purchase' && transaction.transactionType !== 'sale') return;
      const date = new Date(transaction.transactionDate || transaction.filingDate);
      if (Number.isNaN(date.getTime())) return;
      const offset = (date.getFullYear() - start.getFullYear()) * 12 + date.getMonth() - start.getMonth();
      if (offset < 0 || offset >= bucketCount) return;
      const bucket = result[offset];
      const isSale = transaction.transactionType === 'sale';
      const amount = Math.abs(transaction.shares);
      if (isSale) bucket.sale += amount;
      else bucket.purchase += amount;
    });
    result.forEach((bucket, index) => {
      bucket.label = new Date(start.getFullYear(), start.getMonth() + index, 1).toLocaleDateString('en-US', { month: 'short' });
    });
    return result;
  }, [transactions, days]);
  const ceiling = Math.max(...buckets.map((item) => Math.max(item.purchase, item.sale)), 1);
  const baseY = 132;
  const chartHeight = 104;
  return (
    <div className="chart-wrap" data-testid="chart-insider-timeline">
      <svg className="chart-svg" viewBox="0 0 680 158" role="img" aria-label="Monthly insider purchases and sales">
        {[25, 60, 95, 132].map((y) => <line key={y} x1="30" x2="668" y1={y} y2={y} className={y === 132 ? 'chart-base' : 'chart-grid-line'} />)}
        {buckets.map((item, index) => {
          const spacing = 638 / buckets.length;
          const groupX = 30 + index * spacing + (spacing - 30) / 2;
          const buyHeight = (item.purchase / ceiling) * chartHeight;
          const saleHeight = (item.sale / ceiling) * chartHeight;
          return (
            <g key={`${item.label}-${index}`}>
              <rect x={groupX} y={baseY - buyHeight} width="12" height={Math.max(buyHeight, item.purchase ? 2 : 0)} rx="2" className="chart-bar-buy" />
              <rect x={groupX + 16} y={baseY - saleHeight} width="12" height={Math.max(saleHeight, item.sale ? 2 : 0)} rx="2" className="chart-bar-sale" />
              <text x={groupX + 14} y="151" textAnchor="middle" className="chart-label">{item.label}</text>
            </g>
          );
        })}
      </svg>
      <div className="chart-tooltip-note">Monthly market volume · shares</div>
    </div>
  );
}

function Metric({ label, value, caption, tone, icon }: { label: string; value: string; caption?: string; tone?: string; icon: ReactNode }) {
  return (
    <div className="metric" data-testid={`metric-${label.toLowerCase().replaceAll(' ', '-')}`}>
      <div className="metric-label">{icon}{label}</div>
      <div className={`metric-value ${tone ?? ''}`} data-testid={`value-${label.toLowerCase().replaceAll(' ', '-')}`}>{value}</div>
      {caption && <div className="metric-caption">{caption}</div>}
    </div>
  );
}

function InsiderActivityApp() {
  const [initialReport] = useState(readInitialReport);
  const [query, setQuery] = useState(initialReport.symbol);
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [selected, setSelected] = useState<{ symbol: string; name: string; cik: string } | null>(
    initialReport.symbol
      ? { symbol: initialReport.symbol, name: initialReport.symbol, cik: '' }
      : null,
  );
  const [days, setDays] = useState(initialReport.days);
  const [filter, setFilter] = useState<ActivityFilter>('all');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 260);
    return () => window.clearTimeout(timer);
  }, [query]);

  const searchParams = { query: debouncedQuery || ' ' };
  const search = useSearchCompanies(searchParams, {
    query: {
      enabled: debouncedQuery.length >= 1 && showSuggestions,
      queryKey: getSearchCompaniesQueryKey(searchParams),
    },
  });
  const activityParams = { symbol: selected?.symbol ?? '', days, limit: 100 };
  const activity = useGetInsiderActivity(activityParams, {
    query: {
      enabled: Boolean(selected?.symbol),
      queryKey: getGetInsiderActivityQueryKey(activityParams),
    },
  });
  const report = activity.data;
  const suggestions = search.data ?? [];
  const transactions = report?.transactions ?? [];
  const shownTransactions = useMemo(
    () => transactions.filter((transaction) => filter === 'all' || transaction.transactionType === filter),
    [transactions, filter],
  );
  const insiders = useMemo(() => {
    const group = new Map<string, { name: string; role: string; count: number }>();
    transactions.forEach((transaction) => {
      const existing = group.get(transaction.insiderName) ?? {
        name: transaction.insiderName,
        role: transaction.title || transaction.role,
        count: 0,
      };
      existing.count += 1;
      group.set(transaction.insiderName, existing);
    });
    return [...group.values()].sort((a, b) => b.count - a.count).slice(0, 5);
  }, [transactions]);

  function chooseCompany(company: { symbol: string; name: string; cik: string }) {
    setSelected(company);
    setQuery(company.symbol);
    setShowSuggestions(false);
    setFilter('all');
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = query.trim().toUpperCase();
    const match = suggestions.find((company) => company.symbol === normalized);
    if (match) chooseCompany(match);
    else if (/^[A-Z][A-Z0-9.-]{0,11}$/.test(normalized)) {
      chooseCompany({ symbol: normalized, name: normalized, cik: '' });
    }
    else if (suggestions.length) chooseCompany(suggestions[0]);
    else setShowSuggestions(true);
  }

  async function copyReportLink() {
    try {
      const url = new URL(window.location.href);
      if (selected?.symbol) url.searchParams.set('symbol', selected.symbol);
      url.searchParams.set('days', String(days));
      await navigator.clipboard.writeText(url.toString());
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  function exportCsv() {
    if (!shownTransactions.length) return;
    const columns = ['Filing date', 'Transaction date', 'Insider', 'Title', 'Type', 'Code', 'Shares', 'Price per share', 'Value', 'Shares owned after'];
    const rows = shownTransactions.map((t) => [t.filingDate, t.transactionDate, t.insiderName, t.title || t.role, t.transactionType, t.code, t.shares, t.pricePerShare ?? '', t.value ?? '', t.sharesOwnedFollowing ?? '']);
    const csv = [columns, ...rows].map((row) => row.map((item) => `"${String(item).replaceAll('"', '""')}"`).join(',')).join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${selected?.symbol ?? 'insider'}-activity.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand" data-testid="text-brand">
          <span className="brand-mark"><BarChart3 /></span>
          <span>Insider Ledger</span>
        </div>
        <div className="topbar-right"><span className="live-dot" /><span>SEC filing intelligence</span><span aria-hidden="true">·</span><span>U.S. equities</span></div>
      </header>

      <main className="page-wrap">
        <section className="intro">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> Form 4 activity monitor</div>
            <h1>Read between the filings.</h1>
            <p>A clearer view of the people moving with a company.</p>
          </div>
          <div className="date-note"><ShieldCheck size={14} /> Sourced from SEC disclosures</div>
        </section>

        <section className="search-card" aria-label="Company search">
          <label className="search-label" htmlFor="company-search">Company or ticker</label>
          <form className="search-row" onSubmit={submitSearch}>
            <div className="search-field">
              <Search size={17} />
              <input
                id="company-search"
                data-testid="input-company-search"
                value={query}
                onChange={(event) => { setQuery(event.target.value); setShowSuggestions(true); }}
                onFocus={() => setShowSuggestions(true)}
                onBlur={() => window.setTimeout(() => setShowSuggestions(false), 140)}
                placeholder="Search a public company, e.g. NVIDIA or NVDA"
                autoComplete="off"
                aria-label="Search companies by name or ticker"
              />
              {search.isFetching && <LoaderCircle size={15} className="animate-spin" />}
            </div>
            <button className="search-submit" type="submit" data-testid="button-search-company" disabled={!query.trim()}>
              <Search size={15} /><span>Analyze activity</span>
            </button>
            {showSuggestions && debouncedQuery.length > 0 && (
              <div className="suggestions" role="listbox" data-testid="list-company-suggestions">
                {search.isLoading && <div className="suggestion" aria-live="polite">Searching company records…</div>}
                {search.isError && <div className="suggestion" role="status">Company search is temporarily unavailable.</div>}
                {!search.isLoading && !search.isError && suggestions.map((company) => (
                  <button type="button" className="suggestion" key={company.cik} onMouseDown={(event) => event.preventDefault()} onClick={() => chooseCompany(company)} data-testid={`option-company-${company.symbol}`}>
                    <span className="suggestion-name">{company.name}</span><span className="suggestion-ticker">{company.symbol}</span>
                  </button>
                ))}
                {!search.isLoading && !search.isError && suggestions.length === 0 && !search.isFetching && (
                  <div className="suggestion" role="status">No matching public companies found.</div>
                )}
              </div>
            )}
          </form>
          <div className="search-foot">
            <div className="quick-picks"><span>Try</span>{QUICK_SEARCHES.map((symbol) => (
              <button type="button" key={symbol} onClick={() => { setQuery(symbol); setShowSuggestions(true); }} data-testid={`button-quick-search-${symbol}`}>{symbol}</button>
            ))}</div>
            {selected && <div className="period-control" aria-label="Activity period">
              {PERIODS.map((period) => <button type="button" key={period} className={days === period ? 'active' : ''} aria-pressed={days === period} onClick={() => setDays(period)} data-testid={`button-period-${period}`}>{period === 365 ? '1Y' : `${period}D`}</button>)}
            </div>}
          </div>
        </section>

        {!selected && (
          <section className="panel status-card fade-in" data-testid="empty-search-state">
            <div>
              <div className="status-icon"><Landmark size={18} /></div>
              <div className="status-title">Start with a company</div>
              <p className="status-description">Search a ticker or company name to trace reported purchases, sales, and awards across its insider group.</p>
            </div>
          </section>
        )}

        {selected && activity.isLoading && (
          <section className="results-area" aria-label="Loading activity" data-testid="loading-activity-state">
            <div className="metric-grid">{Array.from({ length: 5 }, (_, index) => <div className="metric" key={index}><div className="skeleton" style={{ height: 10, width: 80 }} /><div className="skeleton" style={{ height: 24, width: 106, marginTop: 13 }} /></div>)}</div>
            <div className="dashboard-grid"><div className="panel" style={{ height: 248 }} /><div className="panel" style={{ height: 248 }} /></div>
            <div className="panel" style={{ height: 280, marginTop: 14 }} />
          </section>
        )}

        {selected && activity.isError && (
          <section className="panel status-card fade-in" role="alert" data-testid="error-activity-state">
            <div><div className="status-icon"><CircleHelp size={18} /></div><div className="status-title">Activity could not be loaded</div>
              <p className="status-description">The filing feed did not respond. Check your connection and try this company again.</p>
              <button className="quiet-button" style={{ margin: '15px auto 0' }} onClick={() => void activity.refetch()} data-testid="button-retry-activity">Retry analysis</button>
            </div>
          </section>
        )}

        {selected && report && (
          <section className="results-area fade-in" data-testid="section-insider-results">
            <div className="result-head">
              <div className="company-id">
                <div className="ticker-block" data-testid="text-company-symbol">{report.company.symbol}</div>
                <div><div className="company-name" data-testid="text-company-name">{report.company.name}</div><div className="company-meta">CIK {report.company.cik} <span aria-hidden="true">·</span> Form 4 activity, past {days} days</div></div>
              </div>
              <div className="report-actions">
                <button type="button" className="quiet-button" onClick={copyReportLink} data-testid="button-copy-report-link">{copied ? <Check size={13} /> : <ExternalLink size={13} />}<span>{copied ? 'Link copied' : 'Copy report link'}</span></button>
                <button type="button" className="quiet-button" onClick={exportCsv} disabled={!shownTransactions.length} data-testid="button-export-csv"><FileText size={13} /><span>Export CSV</span></button>
              </div>
            </div>

            <div className="metric-grid" data-testid="summary-metrics">
              <Metric label="Transactions" value={number(report.summary.totalTransactions)} caption={`${report.summary.uniqueInsiders} reporting insiders`} icon={<FileText size={11} />} />
              <Metric label="Purchases" value={number(report.summary.purchases)} caption="Open-market & other buys" tone="positive" icon={<ArrowDownRight size={12} />} />
              <Metric label="Sales" value={number(report.summary.sales)} caption="Reported dispositions" tone="negative" icon={<ArrowUpRight size={12} />} />
              <Metric label="Net shares" value={`${report.summary.netShares > 0 ? '+' : ''}${number(report.summary.netShares)}`} caption="Purchases less sales" tone={report.summary.netShares >= 0 ? 'positive' : 'negative'} icon={report.summary.netShares >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />} />
              <Metric label="Net value" value={money(report.summary.netValue, true)} caption={`Latest filing ${shortDate(report.summary.latestFilingDate)}`} tone={(report.summary.netValue ?? 0) >= 0 ? 'positive' : 'negative'} icon={<Database size={11} />} />
            </div>

            <div className="dashboard-grid">
              <section className="panel" aria-label="Insider activity timeline">
                <div className="panel-heading">
                  <div><div className="panel-title">Activity over time</div><div className="panel-subtitle">Monthly share volume · past {days} days</div></div>
                  <div className="chart-legend"><span className="legend-key"><span className="legend-dot" />Buys</span><span className="legend-key"><span className="legend-dot sale" />Sells</span></div>
                </div>
                <TimelineChart transactions={transactions} days={days} />
              </section>
              <section className="panel" aria-label="Most active insiders">
                <div className="panel-heading"><div><div className="panel-title">Most active insiders</div><div className="panel-subtitle">Ranked by reported transactions</div></div></div>
                {insiders.length ? <div className="insider-list" data-testid="list-active-insiders">{insiders.map((insider) => (
                  <div className="insider-row" key={insider.name} data-testid={`row-insider-${initials(insider.name)}`}>
                    <div className="insider-avatar">{initials(insider.name)}</div>
                    <div className="insider-info"><div className="insider-name">{insider.name}</div><div className="insider-role">{insider.role || 'Reporting insider'}</div></div>
                    <div className="insider-count">{insider.count} filing{insider.count === 1 ? '' : 's'}</div>
                  </div>
                ))}</div> : <div className="status-card" style={{ minHeight: 135 }}>No insider activity in this period.</div>}
              </section>
            </div>

            <section className="panel table-panel" aria-label="Insider transactions">
              <div className="table-head">
                <div><div className="panel-title">Reported transactions</div><div className="panel-subtitle">Individual Form 4 transactions · filing date and transaction details</div></div>
                <div className="table-controls" aria-label="Filter transactions">
                  {(['all', 'purchase', 'sale', 'award'] as ActivityFilter[]).map((kind) => <button type="button" className={filter === kind ? 'active' : ''} key={kind} onClick={() => setFilter(kind)} aria-pressed={filter === kind} data-testid={`button-filter-${kind}`}>{kind === 'all' ? 'All activity' : `${kind[0].toUpperCase()}${kind.slice(1)}s`}</button>)}
                </div>
              </div>
              <div className="table-scroll">
                <table className="activity-table">
                  <thead><tr><th>Filing date</th><th>Transaction date</th><th>Insider</th><th>Transaction</th><th>Code</th><th style={{ textAlign: 'right' }}>Shares</th><th style={{ textAlign: 'right' }}>Price / share</th><th style={{ textAlign: 'right' }}>Value</th><th style={{ textAlign: 'right' }}>Shares after</th><th>Ownership</th><th>Filing</th></tr></thead>
                  <tbody data-testid="list-transactions">
                    {shownTransactions.length ? shownTransactions.map((transaction) => (
                      <tr key={transaction.id} data-testid={`row-transaction-${transaction.id}`}>
                        <td className="date-cell">{shortDate(transaction.filingDate)}</td>
                        <td className="date-cell">{shortDate(transaction.transactionDate)}</td>
                        <td><div className="person-cell"><div className="person-initials">{initials(transaction.insiderName)}</div><div><div className="person-name">{transaction.insiderName}</div><div className="person-title">{transaction.title || transaction.role || 'Insider'}</div></div></div></td>
                        <td><span className={`type-badge type-${transaction.transactionType === 'purchase' ? 'purchase' : transaction.transactionType === 'sale' ? 'sale' : transaction.transactionType === 'award' ? 'award' : 'other'}`}>{transaction.transactionType}</span></td>
                        <td className="mono">{transaction.code || '—'}</td>
                        <td className="number-cell">{number(transaction.shares)}</td>
                        <td className="number-cell">{money(transaction.pricePerShare)}</td>
                        <td className="number-cell">{money(transaction.value)}</td>
                        <td className="number-cell">{number(transaction.sharesOwnedFollowing)}</td>
                        <td>{transaction.directOrIndirect || '—'}</td>
                        <td><a className="filing-link" href={transaction.filingUrl} target="_blank" rel="noreferrer" aria-label={`Open SEC filing for ${transaction.insiderName}`} data-testid={`link-filing-${transaction.id}`}><ExternalLink size={13} /></a></td>
                      </tr>
                    )) : <tr><td className="table-empty" colSpan={11} data-testid="empty-transaction-filter">No transactions match this filter in the selected period.</td></tr>}
                  </tbody>
                </table>
              </div>
              <div className="table-footer"><span>{shownTransactions.length} transaction{shownTransactions.length === 1 ? '' : 's'} shown</span><span>Sorted by filing date, newest first</span></div>
            </section>
            <div className="source-note" data-testid="text-data-source">
              <span><ShieldCheck size={12} /> Source: {report.source || 'SEC EDGAR'} · Reported by company insiders</span>
              <span><Clock3 size={12} /> Updated {shortDate(report.generatedAt)}</span>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <ErrorBoundary>
          <InsiderActivityApp />
        </ErrorBoundary>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
