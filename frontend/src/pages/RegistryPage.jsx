import { useState, useEffect, useCallback } from 'react'
import { Upload, Plus, Trash2, Eye, ToggleLeft, ToggleRight, Search, RefreshCw, X } from 'lucide-react'
import {
  getTools, getRegistryStats, deleteTool, enableTool, disableTool,
  importCollection, registerTool,
} from '../api/client'
import LoadingSpinner from '../components/LoadingSpinner'

const METHOD_BADGE = {
  GET:    'bg-emerald-50 text-emerald-900 border border-emerald-300',
  POST:   'bg-amber-50 text-amber-950 border border-amber-300',
  PUT:    'bg-orange-50 text-orange-950 border border-orange-300',
  DELETE: 'bg-rose-50 text-rose-950 border border-rose-300',
  PATCH:  'bg-purple-50 text-purple-950 border border-purple-300',
}

/* ── Schema side-panel ── */
function SchemaPanel({ tool, onClose }) {
  if (!tool) return null
  return (
    <div className="w-88 shrink-0 border-l border-[#ebdccb] bg-[#ffffff] flex flex-col overflow-hidden shadow-soft">
      <div className="flex items-center justify-between px-4 py-3.5 border-b border-[#ebdccb] bg-[#faf7f2]">
        <h3 className="font-semibold text-espresso-950 text-sm truncate">{tool.name}</h3>
        <button onClick={onClose} className="text-[#8c6f58] hover:text-espresso-950 p-1 rounded-md hover:bg-caramel-100 transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
        <div className="grid grid-cols-2 gap-x-4 gap-y-2.5 bg-[#faf7f2] p-3 rounded-xl border border-[#ebdccb]">
          {[
            ['tool_id', tool.tool_id],
            ['service', tool.service],
            ['category', tool.category],
            ['method', tool.method],
            ['risk', tool.risk_level],
            ['active', String(tool.is_active)],
          ].map(([k, v]) => (
            <div key={k}>
              <p className="text-[#8c6f58] font-semibold uppercase text-[10px] tracking-wider">{k}</p>
              <p className="text-espresso-950 font-mono break-all text-[11px] mt-0.5 font-medium">{v}</p>
            </div>
          ))}
        </div>
        <div>
          <p className="text-[#7d6856] font-semibold mb-1 uppercase text-[10px] tracking-wider">endpoint</p>
          <code className="text-caramel-950 bg-[#f5ede2] px-2.5 py-1.5 rounded-lg border border-[#e5d3c0] block break-all font-mono text-[11px]">{tool.endpoint}</code>
        </div>
        {tool.description && (
          <div>
            <p className="text-[#7d6856] font-semibold mb-1 uppercase text-[10px] tracking-wider">description</p>
            <p className="text-[#4a392b] leading-relaxed bg-[#faf7f2] p-2.5 rounded-lg border border-[#ebdccb] text-xs">{tool.description}</p>
          </div>
        )}
        {tool.example_queries?.length > 0 && (
          <div>
            <p className="text-[#7d6856] font-semibold mb-1 uppercase text-[10px] tracking-wider">example queries</p>
            <ul className="space-y-1 bg-[#faf7f2] p-2.5 rounded-lg border border-[#ebdccb]">
              {tool.example_queries.map((q, i) => (
                <li key={i} className="text-[#4a392b] text-xs">• {q}</li>
              ))}
            </ul>
          </div>
        )}
        <div>
          <p className="text-[#7d6856] font-semibold mb-1 uppercase text-[10px] tracking-wider">parameters (JSON Schema)</p>
          <pre className="bg-[#f7f0e6] p-3 rounded-xl text-[#4d2d11] overflow-x-auto whitespace-pre-wrap font-mono text-[11px] border border-[#e5d3c0]">
            {JSON.stringify(tool.parameters, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  )
}

/* ── Register Tool Modal ── */
const BLANK = { tool_id: '', name: '', service: '', category: '', description: '', method: 'GET', endpoint: '', risk_level: 'LOW' }

function RegisterModal({ onClose, onSuccess }) {
  const [data, setData] = useState(BLANK)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)

  const set = (k) => (e) => setData((d) => ({ ...d, [k]: e.target.value }))

  const submit = async () => {
    setLoading(true)
    setErr(null)
    try {
      await registerTool(data)
      onSuccess()
      onClose()
    } catch (e) {
      setErr(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
      <div className="bg-[#ffffff] border border-[#ebdccb] rounded-2xl p-6 max-w-md w-full mx-4 overflow-y-auto max-h-[90vh] shadow-2xl">
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-[#ebdccb]">
          <h3 className="font-bold text-espresso-950 text-base">Register Tool</h3>
          <button onClick={onClose} className="text-[#8c6f58] hover:text-espresso-950"><X className="w-4 h-4" /></button>
        </div>
        <div className="space-y-3.5">
          {[
            ['tool_id', 'Tool ID (unique)'],
            ['name', 'Display Name'],
            ['service', 'Service (e.g. invoicing)'],
            ['category', 'Category'],
            ['description', 'Description'],
            ['endpoint', 'Endpoint (e.g. /v2/invoicing/invoices)'],
          ].map(([k, label]) => (
            <div key={k}>
              <label className="text-xs text-[#7d6856] block mb-1 font-medium">{label}</label>
              <input
                value={data[k]}
                onChange={set(k)}
                className="w-full bg-[#faf7f2] border border-[#dec7af] rounded-xl px-3 py-2 text-sm text-espresso-950 placeholder-[#a8927e] focus:bg-white focus:outline-none focus:border-caramel-500 transition-colors"
              />
            </div>
          ))}
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-xs text-[#7d6856] block mb-1 font-medium">Method</label>
              <select value={data.method} onChange={set('method')}
                className="w-full bg-[#faf7f2] border border-[#dec7af] rounded-xl px-3 py-2 text-sm text-espresso-950 focus:outline-none focus:border-caramel-500">
                {['GET', 'POST', 'PUT', 'DELETE', 'PATCH'].map((m) => <option key={m}>{m}</option>)}
              </select>
            </div>
            <div className="flex-1">
              <label className="text-xs text-[#7d6856] block mb-1 font-medium">Risk</label>
              <select value={data.risk_level} onChange={set('risk_level')}
                className="w-full bg-[#faf7f2] border border-[#dec7af] rounded-xl px-3 py-2 text-sm text-espresso-950 focus:outline-none focus:border-caramel-500">
                <option>LOW</option><option>HIGH</option>
              </select>
            </div>
          </div>
        </div>
        {err && <p className="text-rose-700 text-xs mt-3 bg-rose-50 p-2 rounded-lg border border-rose-200">{err}</p>}
        <div className="flex gap-3 mt-5">
          <button onClick={submit} disabled={loading}
            className="flex-1 bg-gradient-to-r from-caramel-600 to-caramel-700 hover:from-caramel-500 hover:to-caramel-600 shadow-sm disabled:opacity-50 text-white py-2.5 rounded-xl text-sm font-semibold transition-all">
            {loading ? 'Registering…' : 'Register'}
          </button>
          <button onClick={onClose}
            className="flex-1 bg-stone-100 hover:bg-stone-200 border border-stone-300 text-stone-700 py-2.5 rounded-xl text-sm font-medium transition-colors">
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

/* ── Main Page ── */
export default function RegistryPage() {
  const [tools, setTools] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [search, setSearch] = useState('')
  const [svcFilter, setSvcFilter] = useState('')
  const [methodFilter, setMethodFilter] = useState('')
  const [importResult, setImportResult] = useState(null)
  const [importLoading, setImportLoading] = useState(false)
  const [showRegister, setShowRegister] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = {}
      if (svcFilter) params.service = svcFilter
      if (methodFilter) params.method = methodFilter
      if (search) params.search = search
      const [tr, sr] = await Promise.all([getTools(params), getRegistryStats()])
      setTools(tr.tools || [])
      setStats(sr)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [search, svcFilter, methodFilter])

  useEffect(() => { load() }, [load])

  const services = stats ? Object.keys(stats.by_service || {}) : []

  const handleImport = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setImportLoading(true)
    setImportResult(null)
    try {
      const res = await importCollection(file)
      setImportResult(res)
      load()
    } catch (err) {
      setImportResult({ error: err.message })
    } finally {
      setImportLoading(false)
      e.target.value = ''
    }
  }

  const confirmDelete = async () => {
    try {
      await deleteTool(deleteTarget)
      if (selected?.tool_id === deleteTarget) setSelected(null)
      setDeleteTarget(null)
      load()
    } catch (e) {
      setError(e.message)
    }
  }

  const toggle = async (tool) => {
    try {
      tool.is_active ? await disableTool(tool.tool_id) : await enableTool(tool.tool_id)
      load()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="flex h-full overflow-hidden bg-[#faf7f2]">
      {/* ── Table area ── */}
      <div className="flex-1 flex flex-col overflow-hidden p-6 min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h1 className="text-xl font-bold text-espresso-950 tracking-tight">Tool Registry</h1>
            {stats && (
              <p className="text-xs text-caramel-800 mt-0.5 font-semibold">{stats.total} total tools · {stats.active} active</p>
            )}
          </div>
          <div className="flex items-center gap-2.5">
            <label className="flex items-center gap-1.5 bg-[#ffffff] hover:bg-caramel-50 border border-[#ebdccb] text-[#5c493c] text-xs font-semibold px-3 py-2 rounded-xl cursor-pointer transition-colors shadow-xs">
              {importLoading ? <LoadingSpinner size="sm" /> : <Upload className="w-3.5 h-3.5 text-caramel-700" />}
              Import OpenAPI / Postman
              <input type="file" accept=".json,.yaml,.yml" className="hidden" onChange={handleImport} />
            </label>
            <button
              onClick={() => setShowRegister(true)}
              className="flex items-center gap-1.5 bg-gradient-to-r from-caramel-600 to-caramel-700 hover:from-caramel-500 hover:to-caramel-600 text-white text-xs font-semibold px-3.5 py-2 rounded-xl transition-all shadow-sm"
            >
              <Plus className="w-3.5 h-3.5" /> Register Tool
            </button>
            <button onClick={load} className="p-2 text-[#7d6856] hover:text-espresso-950 hover:bg-caramel-50 rounded-xl border border-[#ebdccb] transition-colors shadow-xs">
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Import result banner */}
        {importResult && (
          <div
            className={`mb-3.5 px-4 py-2.5 rounded-xl text-xs flex items-center justify-between ${
              importResult.error
                ? 'bg-rose-50 border border-rose-300 text-rose-800'
                : 'bg-emerald-50 border border-emerald-300 text-emerald-800'
            }`}
          >
            <span>
              {importResult.error
                ? importResult.error
                : `✓ Imported ${importResult.imported} · skipped ${importResult.skipped} · errors ${importResult.errors}`}
            </span>
            <button onClick={() => setImportResult(null)} className="ml-3 opacity-60 hover:opacity-100">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Filters */}
        <div className="flex gap-2.5 mb-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#8c6f58]" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search tools by name, endpoint or description…"
              className="w-full bg-[#ffffff] border border-[#ebdccb] rounded-xl pl-9 pr-3.5 py-2 text-xs text-espresso-950 placeholder-[#a8927e] focus:outline-none focus:border-caramel-500 transition-colors shadow-xs"
            />
          </div>
          <select value={svcFilter} onChange={(e) => setSvcFilter(e.target.value)}
            className="bg-[#ffffff] border border-[#ebdccb] rounded-xl px-3 py-2 text-xs text-espresso-950 focus:outline-none focus:border-caramel-500 shadow-xs">
            <option value="">All Services</option>
            {services.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={methodFilter} onChange={(e) => setMethodFilter(e.target.value)}
            className="bg-[#ffffff] border border-[#ebdccb] rounded-xl px-3 py-2 text-xs text-espresso-950 focus:outline-none focus:border-caramel-500 shadow-xs">
            <option value="">All Methods</option>
            {['GET', 'POST', 'PUT', 'DELETE', 'PATCH'].map((m) => <option key={m}>{m}</option>)}
          </select>
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
              <LoadingSpinner text="Loading tools…" />
            </div>
          ) : (
            <table className="w-full text-xs min-w-max">
              <thead className="bg-[#faf7f2] sticky top-0 z-10 border-b border-[#ebdccb]">
                <tr>
                  {['Method', 'Name', 'Service', 'Category', 'Risk', 'Status', 'Actions'].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-[11px] font-semibold text-[#7d6856] uppercase tracking-wider whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f2e7db]">
                {tools.map((tool) => (
                  <tr
                    key={tool.tool_id}
                    onClick={() => setSelected(selected?.tool_id === tool.tool_id ? null : tool)}
                    className={`cursor-pointer transition-colors ${
                      selected?.tool_id === tool.tool_id
                        ? 'bg-caramel-100/70 border-l-2 border-caramel-600'
                        : 'hover:bg-caramel-50/60'
                    }`}
                  >
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className={`text-[11px] font-mono font-bold px-2 py-0.5 rounded ${METHOD_BADGE[tool.method] || 'bg-stone-100 text-stone-800'}`}>
                        {tool.method}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-semibold text-espresso-950">{tool.name}</p>
                      <p className="text-[11px] text-[#8c6f58] font-mono mt-0.5">{tool.tool_id}</p>
                    </td>
                    <td className="px-4 py-3 text-stone-700 whitespace-nowrap">{tool.service}</td>
                    <td className="px-4 py-3 text-[#7d6856] whitespace-nowrap">{tool.category}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className={`text-[11px] px-2 py-0.5 rounded font-mono font-semibold ${tool.risk_level === 'HIGH' ? 'bg-amber-100 text-amber-900 border border-amber-300' : 'bg-stone-100 text-stone-700'}`}>
                        {tool.risk_level}
                      </span>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className={`text-xs font-medium ${tool.is_active ? 'text-emerald-700 font-semibold' : 'text-stone-400'}`}>
                        {tool.is_active ? '● Active' : '○ Inactive'}
                      </span>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                        <button onClick={() => setSelected(tool)} title="View schema"
                          className="p-1.5 text-[#7d6856] hover:text-caramel-900 hover:bg-caramel-100 rounded-lg transition-colors">
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={() => toggle(tool)} title={tool.is_active ? 'Disable' : 'Enable'}
                          className="p-1.5 text-[#7d6856] hover:text-caramel-900 hover:bg-caramel-100 rounded-lg transition-colors">
                          {tool.is_active
                            ? <ToggleRight className="w-4 h-4 text-emerald-600" />
                            : <ToggleLeft className="w-4 h-4 text-stone-400" />}
                        </button>
                        <button onClick={() => setDeleteTarget(tool.tool_id)} title="Delete"
                          className="p-1.5 text-[#7d6856] hover:text-rose-700 hover:bg-rose-50 rounded-lg transition-colors">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!loading && tools.length === 0 && (
            <div className="text-center text-[#8c6f58] py-16 text-xs">
              No tools found. Import a Postman collection or register tools manually.
            </div>
          )}
        </div>
      </div>

      {/* ── Schema panel ── */}
      <SchemaPanel tool={selected} onClose={() => setSelected(null)} />

      {/* ── Delete confirm ── */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-[#ffffff] border border-rose-300 rounded-2xl p-6 max-w-sm w-full mx-4 shadow-2xl">
            <h3 className="text-espresso-950 font-bold mb-2 text-base">Delete tool?</h3>
            <p className="text-[#6b584a] text-xs mb-4">
              Permanently remove <code className="text-rose-800 bg-rose-50 px-1.5 py-0.5 rounded border border-rose-200">{deleteTarget}</code> from the registry.
            </p>
            <div className="flex gap-3">
              <button onClick={confirmDelete}
                className="flex-1 bg-rose-600 hover:bg-rose-700 text-white py-2 rounded-xl text-xs font-semibold transition-colors">
                Delete
              </button>
              <button onClick={() => setDeleteTarget(null)}
                className="flex-1 bg-stone-100 hover:bg-stone-200 text-stone-700 py-2 rounded-xl text-xs font-medium transition-colors">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Register modal ── */}
      {showRegister && (
        <RegisterModal onClose={() => setShowRegister(false)} onSuccess={load} />
      )}
    </div>
  )
}
