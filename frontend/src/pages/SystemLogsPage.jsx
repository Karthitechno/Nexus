import { useState, useEffect } from 'react'
import { RefreshCw, Search, X } from 'lucide-react'
import { getLogs, getLogById } from '../api/client'
import LoadingSpinner from '../components/LoadingSpinner'

export default function SystemLogsPage() {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [ridSearch, setRidSearch] = useState('')
  const [limit, setLimit] = useState(50)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getLogs(limit)
      setLogs(res.logs || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [limit])

  const searchById = async () => {
    const rid = ridSearch.trim()
    if (!rid) return
    setError(null)
    try {
      const log = await getLogById(rid)
      setSelected(log)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="flex h-full overflow-hidden p-6 gap-5 bg-[#faf7f2]">
      {/* ── Log table ── */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h1 className="text-xl font-bold text-espresso-950 tracking-tight">System Telemetry &amp; Logs</h1>
            <p className="text-xs text-caramel-800 mt-0.5 font-medium">Immutable audit trail of all tool executions, routing events, and approvals</p>
          </div>
          <div className="flex items-center gap-2.5">
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="bg-[#ffffff] border border-[#ebdccb] rounded-xl px-3 py-2 text-xs text-espresso-950 focus:outline-none focus:border-caramel-500 shadow-xs"
            >
              {[20, 50, 100, 200].map((n) => (
                <option key={n} value={n}>Last {n} records</option>
              ))}
            </select>
            <button
              onClick={load}
              className="p-2 text-[#7d6856] hover:text-espresso-950 hover:bg-caramel-50 rounded-xl border border-[#ebdccb] transition-colors shadow-xs"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Request ID search */}
        <div className="flex gap-2.5 mb-4">
          <input
            value={ridSearch}
            onChange={(e) => setRidSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && searchById()}
            placeholder="Filter by unique request_id (e.g. req_6b4a3c10)…"
            className="flex-1 bg-[#ffffff] border border-[#ebdccb] rounded-xl px-3.5 py-2 text-xs text-espresso-950 placeholder-[#a8927e] focus:outline-none focus:border-caramel-500 transition-colors shadow-xs"
          />
          <button
            onClick={searchById}
            className="flex items-center gap-1.5 bg-gradient-to-r from-caramel-600 to-caramel-700 hover:from-caramel-500 hover:to-caramel-600 text-white px-4 py-2 rounded-xl text-xs font-semibold transition-all shadow-sm"
          >
            <Search className="w-3.5 h-3.5" /> Lookup
          </button>
        </div>

        {error && (
          <div className="mb-3.5 bg-rose-50 border border-rose-300 text-rose-800 px-4 py-2.5 rounded-xl text-xs">
            {error}
          </div>
        )}

        {/* Table */}
        <div className="flex-1 overflow-auto rounded-xl border border-[#ebdccb] bg-[#ffffff] shadow-soft">
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <LoadingSpinner text="Loading logs…" />
            </div>
          ) : (
            <table className="w-full text-xs min-w-max">
              <thead className="bg-[#faf7f2] sticky top-0 z-10 border-b border-[#ebdccb]">
                <tr>
                  {['Request ID', 'Tool ID', 'Status', 'Latency', 'Timestamp', 'Error / Diagnostic'].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-[11px] font-semibold text-[#7d6856] uppercase tracking-wider whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f2e7db]">
                {logs.map((log, i) => (
                  <tr
                    key={i}
                    onClick={() => setSelected(log)}
                    className={`cursor-pointer transition-colors ${
                      selected === log
                        ? 'bg-caramel-100/70 border-l-2 border-caramel-600'
                        : 'hover:bg-caramel-50/60'
                    }`}
                  >
                    <td className="px-4 py-3 font-mono text-[#7d6856]">{log.request_id?.slice(0, 12)}…</td>
                    <td className="px-4 py-3 text-espresso-950 font-semibold">{log.tool_id}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-bold font-mono ${
                          log.status === 'SUCCESS'
                            ? 'bg-emerald-50 text-emerald-900 border border-emerald-300'
                            : log.status === 'NOT_CONFIGURED'
                            ? 'bg-amber-50 text-amber-950 border border-amber-300'
                            : 'bg-rose-50 text-rose-950 border border-rose-300'
                        }`}
                      >
                        {log.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-caramel-900 font-mono font-medium">{Math.round(log.latency_ms)}ms</td>
                    <td className="px-4 py-3 text-[#7d6856] whitespace-nowrap font-mono">
                      {new Date(log.timestamp * 1000).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-rose-700 max-w-xs truncate font-mono text-[11px]">{log.error || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!loading && logs.length === 0 && (
            <div className="text-center text-[#8c6f58] py-16 text-xs">
              No execution logs found. Send a chat request to generate logs.
            </div>
          )}
        </div>
      </div>

      {/* ── Detail panel ── */}
      {selected && (
        <div className="w-96 shrink-0 bg-[#ffffff] border border-[#ebdccb] rounded-2xl flex flex-col overflow-hidden shadow-soft">
          <div className="flex items-center justify-between px-4 py-3.5 border-b border-[#ebdccb] bg-[#faf7f2]">
            <h3 className="text-xs font-semibold text-espresso-950 uppercase tracking-wider">Log Detail Record</h3>
            <button
              onClick={() => setSelected(null)}
              className="text-[#8c6f58] hover:text-espresso-950 p-1 rounded-md hover:bg-caramel-100 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <pre className="text-[11px] text-[#4d2d11] bg-[#f7f0e6] p-3.5 rounded-xl overflow-x-auto whitespace-pre-wrap break-all font-mono border border-[#e5d3c0]">
              {JSON.stringify(selected, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}
