import { useState, useEffect } from 'react'
import { Database, Shield, Activity, Cpu, RefreshCw } from 'lucide-react'
import { getRegistryStats, getHealth, getLogs, getPayPalStatus } from '../api/client'
import LoadingSpinner from '../components/LoadingSpinner'

function StatCard({ icon: Icon, label, value, sub, color = 'text-caramel-700' }) {
  return (
    <div className="bg-[#ffffff] border border-[#ebdccb] rounded-2xl p-5 shadow-soft">
      <div className="flex items-start gap-4">
        <div className={`p-2.5 rounded-xl bg-caramel-50 border border-caramel-200 ${color}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div className="min-w-0">
          <p className="text-[#7d6856] text-xs font-semibold uppercase tracking-wider">{label}</p>
          <p className="text-2xl font-bold text-espresso-950 mt-1 truncate tracking-tight">{value ?? '—'}</p>
          {sub && <p className="text-xs text-caramel-800 mt-1 truncate font-medium">{sub}</p>}
        </div>
      </div>
    </div>
  )
}

function Bar({ label, value, max }) {
  const pct = max > 0 ? (value / max) * 100 : 0
  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="text-[#4a392b] w-36 truncate shrink-0 font-medium">{label}</span>
      <div className="flex-1 bg-[#f0e6d9] rounded-full h-2 overflow-hidden border border-[#ebdccb]/60">
        <div
          className="bg-gradient-to-r from-caramel-600 to-caramel-500 h-full rounded-full transition-all duration-500 shadow-xs"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-caramel-900 font-mono text-xs w-6 text-right shrink-0 font-bold">{value}</span>
    </div>
  )
}

export default function DashboardPage() {
  const [stats, setStats] = useState(null)
  const [health, setHealth] = useState(null)
  const [logs, setLogs] = useState([])
  const [paypal, setPaypal] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [sr, hr, lr, pr] = await Promise.allSettled([
        getRegistryStats(), getHealth(), getLogs(20), getPayPalStatus(),
      ])
      if (sr.status === 'fulfilled') setStats(sr.value)
      if (hr.status === 'fulfilled') setHealth(hr.value)
      if (lr.status === 'fulfilled') setLogs(lr.value.logs || [])
      if (pr.status === 'fulfilled') setPaypal(pr.value)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner size="lg" text="Loading dashboard…" />
      </div>
    )
  }

  const maxSvc = stats ? Math.max(...Object.values(stats.by_service || {}), 1) : 1
  const maxMeth = stats ? Math.max(...Object.values(stats.by_method || {}), 1) : 1

  const successLogs = logs.filter((l) => l.status === 'SUCCESS').length

  return (
    <div className="p-6 overflow-y-auto h-full space-y-6 bg-[#faf7f2]">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-espresso-950 tracking-tight">System Dashboard</h1>
          <p className="text-xs text-caramel-800 mt-0.5 font-medium">Platform runtime statistics, tool topology, and telemetry</p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 text-xs font-semibold text-caramel-900 hover:text-caramel-950 px-3 py-2 rounded-xl bg-white hover:bg-caramel-50 border border-[#ebdccb] transition-colors shadow-xs"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Database}
          label="Total Tools"
          value={stats?.total ?? 0}
          sub={`${stats?.active ?? 0} active · ${stats?.inactive ?? 0} inactive`}
          color="text-caramel-700"
        />
        <StatCard
          icon={Shield}
          label="High-Risk Tools"
          value={stats?.by_risk_level?.HIGH ?? 0}
          sub="require human authorization"
          color="text-amber-600"
        />
        <StatCard
          icon={Activity}
          label="Backend Uptime"
          value={health ? `${Math.round(health.uptime_seconds)}s` : '—'}
          sub={health?.services_initialized ? 'core services operational' : 'initializing…'}
          color="text-emerald-700"
        />
        <StatCard
          icon={Cpu}
          label="PayPal Integration"
          value={paypal?.configured ? 'Active' : 'Unset'}
          sub={paypal?.configured ? 'Sandbox OAuth live' : 'Configure in .env'}
          color={paypal?.configured ? 'text-emerald-700' : 'text-stone-400'}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* By service */}
        <div className="bg-[#ffffff] border border-[#ebdccb] rounded-2xl p-5 shadow-soft">
          <h3 className="font-semibold text-espresso-950 mb-4 text-sm tracking-wide">Tools by Service Domain</h3>
          {stats?.by_service && Object.keys(stats.by_service).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(stats.by_service)
                .sort(([, a], [, b]) => b - a)
                .map(([svc, cnt]) => (
                  <Bar key={svc} label={svc} value={cnt} max={maxSvc} />
                ))}
            </div>
          ) : (
            <p className="text-[#8c6f58] text-xs">No service data available.</p>
          )}
        </div>

        {/* By method */}
        <div className="bg-[#ffffff] border border-[#ebdccb] rounded-2xl p-5 shadow-soft">
          <h3 className="font-semibold text-espresso-950 mb-4 text-sm tracking-wide">Tools by HTTP Method</h3>
          {stats?.by_method && Object.keys(stats.by_method).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(stats.by_method)
                .sort(([, a], [, b]) => b - a)
                .map(([m, cnt]) => (
                  <Bar key={m} label={m} value={cnt} max={maxMeth} />
                ))}
            </div>
          ) : (
            <p className="text-[#8c6f58] text-xs">No method data available.</p>
          )}
        </div>
      </div>

      {/* Recent execution logs */}
      <div className="bg-[#ffffff] border border-[#ebdccb] rounded-2xl p-5 shadow-soft">
        <div className="flex items-center justify-between mb-4 pb-2 border-b border-[#ebdccb]">
          <h3 className="font-semibold text-espresso-950 text-sm tracking-wide">Recent Tool Executions</h3>
          {logs.length > 0 && (
            <span className="text-xs text-caramel-800 font-semibold">
              {successLogs}/{logs.length} successful
            </span>
          )}
        </div>
        {logs.length === 0 ? (
          <p className="text-[#8c6f58] text-xs py-4 text-center">No execution logs yet. Interact via the Chat interface to trigger executions.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-max">
              <thead>
                <tr className="text-[#7d6856] border-b border-[#ebdccb]">
                  {['Request ID', 'Tool', 'Status', 'Latency', 'Time'].map((h) => (
                    <th key={h} className="text-left pb-2.5 pr-6 font-semibold uppercase text-[10px] tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f2e7db]">
                {logs.map((log, i) => (
                  <tr key={i} className="hover:bg-caramel-50/50 transition-colors">
                    <td className="py-2.5 pr-6 font-mono text-[#7d6856]">{log.request_id?.slice(0, 8)}…</td>
                    <td className="py-2.5 pr-6 text-espresso-950 font-semibold">{log.tool_id}</td>
                    <td className="py-2.5 pr-6">
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
                    <td className="py-2.5 pr-6 text-caramel-900 font-mono font-medium">{Math.round(log.latency_ms)}ms</td>
                    <td className="py-2 text-[#7d6856] font-mono">
                      {new Date(log.timestamp * 1000).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
