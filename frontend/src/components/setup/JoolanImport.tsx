"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2 } from "lucide-react";
import { getJoolanOrders, importJoolanWorkbook, startJoolanSync, setJoolanForecastSource,
  getJoolanJobStatus, confirmJoolanOrderType, type JoolanOrder, type JoolanSummary } from "@/lib/api/joolan";
import { discoverJoolanSchema, inspectHistoricalCsv, buildCombinedHistory, getCombinedHistory, type CombinedHistory, type JoolanSchema, type HistoricalProfile } from "@/lib/api/joolan";

export default function JoolanImport() {
  const [summary, setSummary] = useState<JoolanSummary | null>(null);
  const [rows, setRows] = useState<JoolanOrder[]>([]);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [key, setKey] = useState("");
  const [enseigne, setEnseigne] = useState("legend73");
  const [documentType, setDocumentType] = useState("");
  const [schema, setSchema] = useState<JoolanSchema | null>(null);
  const [history, setHistory] = useState<HistoricalProfile | null>(null);
  const [schemaSearch, setSchemaSearch] = useState("");
  const [combined, setCombined] = useState<CombinedHistory | null>(null);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
  });
  const fileInput = useRef<HTMLInputElement>(null);
  const load = useCallback(async (start = 0) => {
    const result = await getJoolanOrders(start);
    setSummary(result.summary); setRows(result.rows);
  }, []);
  useEffect(() => {
    let active = true;
    inspectHistoricalCsv().then(result => {
      if (!active) return;
      setHistory(result);
      const next = new Date(`${result.lastOrderDate}T00:00:00Z`);
      next.setUTCDate(next.getUTCDate()+1);
      setStartDate(previous => previous || next.toISOString().slice(0,10));
    }).catch(() => { /* Manual inspection retains the visible error path. */ });
    getCombinedHistory().then(result => { if (active && result.storedRows) setCombined(result); }).catch(() => {});
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let alive = true;
    getJoolanOrders(offset).then(result => {
      if (alive) { setSummary(result.summary); setRows(result.rows); }
    }).catch(e => { if (alive) setError(e instanceof Error ? e.message : "Could not load Joolan data"); });
    return () => { alive = false; };
  }, [offset]);
  useEffect(() => {
    if (!job) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await getJoolanJobStatus(job!);
        if (!alive) return;
        if (result.status === "running") { timer = setTimeout(poll, 2000); return; }
        setJob(null); setBusy(false);
        if (result.status === "error") { setMessage(""); setError(result.errorMessage || "Sync failed; previous snapshot preserved"); }
        else { setMessage("Joolan snapshot updated. Review the rows, then select your forecast source."); setOffset(0); await load(0); }
      } catch (e) {
        if (alive) { setError(e instanceof Error ? e.message : "Could not check sync status"); timer = setTimeout(poll, 5000); }
      }
    }
    void poll();
    return () => { alive = false; clearTimeout(timer); };
  }, [job, load]);
  async function upload(file: File) {
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await importJoolanWorkbook(file); setSummary(result.snapshot);
      setOffset(0); await load(0); setMessage("Trade workbook imported. Re-importing replaces this snapshot without adding quantities again.");
    } catch (e) { setError(e instanceof Error ? e.message : "Import failed"); }
    finally { setBusy(false); if (fileInput.current) fileInput.current.value = ""; }
  }
  async function sync() {
    setBusy(true); setError(""); setMessage(`Downloading or resuming orders from ${startDate} through ${endDate}. Completed pages are kept if Joolan reaches its query limit.`);
    try { const result = await startJoolanSync(key, enseigne.trim(), documentType.trim(), startDate, endDate); setKey(""); setJob(result.jobId); }
    catch (e) { setError(e instanceof Error ? e.message : "Sync failed"); setBusy(false); }
  }
  async function choose(source: "legacy" | "joolan" | "combined") {
    setBusy(true); setError("");
    try {
      if(source==="joolan" || source==="combined")await confirmJoolanOrderType(documentType || summary?.customerOrderType || "");
      setSummary(await setJoolanForecastSource(source)); setMessage("Forecast source changed. Click Refresh forecasts below to rebuild the dashboard.");
    }
    catch (e) { setError(e instanceof Error ? e.message : "Could not change source"); }
    finally { setBusy(false); }
  }
  async function buildHistory() {
    setBusy(true); setError(""); setMessage("Building the persistent CSV + Joolan history database…");
    try {
      if (summary?.usableRows && (documentType || summary.customerOrderType)) {
        await confirmJoolanOrderType(documentType || summary.customerOrderType);
      }
      const result = await buildCombinedHistory(); setCombined(result);
      setMessage(result.needsOrderType ? 'CSV and newer Joolan source rows saved. Confirm the document type to prepare the forecast view.' : 'Combined history saved. Select Use combined history, then refresh forecasts.');
    } catch (e) { setMessage(""); setError(e instanceof Error ? e.message : "Could not build history"); }
    finally { setBusy(false); }
  }
  async function inspectHistory() {
    setBusy(true); setError(""); setMessage("Inspecting the historical CSV…");
    try { setHistory(await inspectHistoricalCsv()); setMessage("Historical CSV inspected. No forecast or source selection was changed."); }
    catch (e) { setError(e instanceof Error ? e.message : "History inspection failed"); setMessage(""); }
    finally { setBusy(false); }
  }
  async function discover() {
    setBusy(true); setError(""); setSchema(null); setMessage("Reading Joolan table and column names…");
    try { setSchema(await discoverJoolanSchema(key, enseigne.trim())); setMessage("Schema discovered. Download the dictionary to map inventory and supplier orders."); }
    catch (e) { setError(e instanceof Error ? e.message : "Schema discovery failed"); setMessage(""); }
    finally { setBusy(false); }
  }
  function downloadDictionary() {
    if (!schema) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(schema, null, 2)], { type: "application/json" }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'joolan-data-dictionary.json';
    document.body.appendChild(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <Card>
    <CardHeader>
      <CardTitle>Joolan trade documents</CardTitle>
      <CardDescription>Import individual order lines with customer, date, ordered quantity and delivered quantity.</CardDescription>
    </CardHeader>
    <CardContent className="space-y-5">
      <div className="rounded-lg border p-4 space-y-3">
        <p className="font-medium">Continue from existing history</p>
        <Button type="button" variant="outline" disabled={busy} onClick={() => void inspectHistory()}>Inspect historical CSV</Button>
        <Button type="button" variant="outline" className="ml-2" disabled={busy} onClick={() => void buildHistory()}>Build CSV + Joolan database</Button>
        {history && <div className="text-sm space-y-2">
          <p>{history.fileName}: {history.rows.toLocaleString()} rows, {history.firstOrderDate} through {history.lastOrderDate}.</p>
          <p>{history.invalidDateRows.toLocaleString()} rows have missing or invalid dates. {history.months.length} months contain recorded orders; this does not establish complete source coverage.</p>
          <p>{history.notice}</p>
        </div>}
        {combined && <div className="text-sm space-y-2">
          <p>{combined.legacyRows.toLocaleString()} CSV rows + {combined.rawJoolanRows.toLocaleString()} newer Joolan source rows = {combined.storedRows.toLocaleString()} stored source rows.</p>
          <p>{combined.joolanRows.toLocaleString()} newer Joolan customer-order lines selected for forecasting. {combined.rawQuarantinedRows.toLocaleString()} newer source rows require review.</p>
          {combined.legacyQuarantinedRows > 0 && <p>{combined.legacyQuarantinedRows.toLocaleString()} CSV rows have invalid quantities and are excluded from training. They remain in the source database for review.</p>}
          <p>History: {combined.firstDate} through {combined.lastDate}. CSV cutoff: {combined.csvCutoff}.</p>
          <p>{combined.notice}</p>
          {combined.gaps.length > 0 && <p role="alert">Import missing periods: {combined.gaps.map(gap => `${gap.start} to ${gap.end}`).join(', ')}.</p>}
          <Button type="button" disabled={busy || combined.needsOrderType || combined.gaps.length > 0} onClick={() => void choose('combined')}>Use combined history</Button>
        </div>}
        <p className="text-sm text-slate-500">The CSV covers dates through its cutoff. Combined history adds only later Joolan orders and preserves repeated lines; re-imported date ranges replace their prior Joolan rows.</p>
      </div>
      <div className="flex flex-wrap gap-3 items-center">
        <Input ref={fileInput} type="file" accept=".xlsx" className="hidden" aria-label="Joolan trade workbook"
          onChange={e => { const file = e.target.files?.[0]; if (file) void upload(file); }} />
        <Button type="button" disabled={busy} onClick={() => fileInput.current?.click()}>Import trade workbook</Button>
        <span className="text-sm text-slate-500">Select Joolan Trade Documents.xlsx. Each import replaces the previous Joolan snapshot.</span>
      </div>
      <details className="rounded-lg border p-4">
        <summary className="cursor-pointer font-medium">Connect directly to Joolan</summary>
        <div className="grid gap-3 mt-4 sm:grid-cols-2">
          <label className="text-sm">Enseigne<Input value={enseigne} onChange={e => setEnseigne(e.target.value)} disabled={busy} /></label>
          <label className="text-sm">API key<Input type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)} disabled={busy} /></label>
          <label className="text-sm sm:col-span-2">Document type (optional)<Input value={documentType} placeholder="Enter the verified customer-order type" onChange={e => setDocumentType(e.target.value)} disabled={busy} /></label>
          <label className="text-sm">From order date<Input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} disabled={busy} /></label>
          <label className="text-sm">Through order date<Input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} disabled={busy} /></label>
        </div>
        <p className="text-sm text-slate-500 my-3">Requires Queries permission. The key stays in memory. With no type filter, all trade document types are included.</p>
        <p className="text-sm text-slate-500 mb-3">Entering a type filters both source tables before download. Confirm the customer-order type in Joolan first. Direct sync can retrieve a complete source when a workbook export was interrupted.</p>
        <p className="text-xs text-slate-500 mb-3">If Joolan reaches its hourly limit, wait for the quota to reset, re-enter your key and sync again. Downloads with an accessible primary key resume from saved pages.</p>
        <Button type="button" disabled={busy || !key.trim() || !enseigne.trim() || !startDate || !endDate || endDate < startDate} onClick={() => void sync()}>Sync selected dates</Button>
        <Button type="button" variant="outline" className="ml-2" disabled={busy || !key.trim() || !enseigne.trim()} onClick={() => void discover()}>Discover tables and columns</Button>
        <p className="text-xs text-slate-500 mt-2">Verify the enseigne belongs to Daytona 73. Discovery reads schema metadata only and does not import orders, stock or train forecasts.</p>
        {schema && <div className="space-y-3 mt-4">
          <p className="text-sm">{schema.tables.length} tables discovered for {schema.enseigne}. {schema.notice}</p>
          <Button type="button" variant="outline" onClick={downloadDictionary}>Download data dictionary</Button>
          <Input aria-label="Search schema tables and columns" placeholder="Search tables or columns" value={schemaSearch} onChange={e => setSchemaSearch(e.target.value)} />
          <div className="max-h-80 overflow-auto space-y-2">
            {schema.tables.filter(table => `${table.name} ${table.columns.map(c => c.name).join(' ')}`.toLowerCase().includes(schemaSearch.toLowerCase())).map(table => <details key={table.name} className="border rounded p-2">
              <summary className="cursor-pointer text-sm font-medium">{table.name} ({table.columns.length} columns)</summary>
              <ul className="mt-2 text-xs space-y-1">{table.columns.map(column => <li key={column.name}>{column.name} · {column.dataType}{column.key ? ` · ${column.key}` : ''}{column.nullable ? ' · nullable' : ''}</li>)}</ul>
            </details>)}
          </div>
        </div>}
      </details>
      {busy && <p className="flex items-center gap-2 text-sm" role="status"><Loader2 className="h-4 w-4 animate-spin" />Working…</p>}
      {message && <p className="text-sm" role="status">{message}</p>}
      {error && <p className="text-sm text-red-600 break-words" role="alert">{error}</p>}
      {summary && <>
        <div className="flex flex-wrap gap-5 text-sm">
          <span><strong>{summary.totalRows.toLocaleString()}</strong> imported rows</span>
          <span><strong>{summary.usableRows.toLocaleString()}</strong> usable order lines</span>
          <span><strong>{summary.quarantinedRows.toLocaleString()}</strong> need review</span>
          <span>Forecast source: <strong>{summary.forecastSource === "combined" ? "CSV + Joolan" : summary.forecastSource === "joolan" ? "Joolan" : "Legacy CSV"}</strong></span>
        </div>
        {summary.importedAt && <p className="text-xs text-slate-500">Last import: {new Date(summary.importedAt).toLocaleString()}</p>}
        {summary.documentTypes.length > 0 && <p className="text-sm">Document types (line/report rows): {summary.documentTypes.map(t => `${t.type}: ${t.rows.toLocaleString()}`).join(" · ")}</p>}
        <p className="text-sm text-amber-700 dark:text-amber-400">{summary.notice} Confirm the document types represent the customer orders you want to forecast.</p>
        <div className="flex flex-wrap gap-3">
          <label className="text-sm">Confirmed customer-order type
            <select className="ml-2 rounded border p-2 bg-background" value={documentType || summary.customerOrderType} onChange={e=>setDocumentType(e.target.value)} disabled={busy}>
              <option value="">Select the type used for customer orders</option>
              {summary.documentTypes.filter(t=>t.type!=="(blank)").map(t=><option key={t.type} value={t.type}>{t.type}</option>)}
            </select>
          </label>
          <Button type="button" disabled={busy || !summary.usableRows || !(documentType || summary.customerOrderType)} onClick={() => void choose("combined")}>Use CSV + confirmed Joolan orders</Button>
          <Button type="button" variant="outline" disabled={busy || !summary.usableRows || !(documentType || summary.customerOrderType)} onClick={() => void choose("joolan")}>Use Joolan snapshot only</Button>
          <Button type="button" variant="outline" disabled={busy || summary.forecastSource === "legacy"} onClick={() => void choose("legacy")}>Use legacy CSV</Button>
        </div>
        <p className="text-xs text-slate-500">Joolan forecasts use ordered units on valid lines. Invalid rows stay in the preview but are excluded. Build the combined database to keep CSV history and add newer Joolan orders.</p>
      </>}
      {rows.length > 0 && <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm text-left">
          <thead><tr className="bg-slate-100 dark:bg-slate-900">{["Order", "Customer", "Date", "Product", "Colour / Size", "Ordered", "Delivered", "Status"].map(label => <th key={label} className="p-2 whitespace-nowrap">{label}</th>)}</tr></thead>
          <tbody>{rows.map((row, i) => <tr key={`${offset}-${i}`} className="border-t">
            <td className="p-2">{row.Order_Number || "—"}</td><td className="p-2">{row.Customer || "—"}</td>
            <td className="p-2 whitespace-nowrap">{row.Order_Date || "—"}</td><td className="p-2">{row.Product || "—"}</td>
            <td className="p-2">{row.Colour || "—"} / {row.Size || "—"}</td>
            <td className="p-2">{row.Ordered_Quantity ?? "—"}</td><td className="p-2">{row.Delivered_Quantity ?? "—"}</td>
            <td className="p-2 min-w-40">{row.Usable ? "Ready" : row.Issues.join("; ")}</td>
          </tr>)}</tbody>
        </table>
      </div>}
      {summary && summary.totalRows > 25 && <div className="flex items-center gap-3 text-sm">
        <Button type="button" variant="outline" disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous</Button>
        <span>{offset + 1}–{Math.min(offset + 25, summary.totalRows)} of {summary.totalRows.toLocaleString()}</span>
        <Button type="button" variant="outline" disabled={busy || offset + 25 >= summary.totalRows} onClick={() => setOffset(offset + 25)}>Next</Button>
      </div>}
    </CardContent>
  </Card>;
}
