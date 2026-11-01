import { useState } from 'react'
import { ChevronDown, ChevronRight, Clock, Wrench, Layers, Terminal } from 'lucide-react'

export default function TracePanel({ trace = {}, selectedTools = [], executionResults = [] }) {
  const [open, setOpen] = useState(false)
  const hasTrace = trace && Object.keys(trace).length > 0
  const hasTools = selectedTools && selectedTools.length > 0
  const hasResults = executionResults && executionResults.length > 0

  if (!hasTrace && !hasTools && !hasResults) return null

  return (
    <div className="border border-[#ebdccb] rounded-xl text-xs font-mono bg-[#ffffff] overflow-hidden shadow-soft">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3.5 py-2.5 text-[#5c493c] hover:text-espresso-950 hover:bg-caramel-50/70 transition-colors"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5 text-caramel-700" /> : <ChevronRight className="w-3.5 h-3.5 text-caramel-600" />}
        <span className="font-sans font-medium text-espresso-900">Technical Details</span>
        
        {hasTools && (
          <span className="text-[11px] text-caramel-800/80 font-sans">
            ({selectedTools.length} tool{selectedTools.length !== 1 ? 's' : ''})
          </span>
        )}

        {trace.total_latency_ms !== undefined && (
          <span className="ml-auto flex items-center gap-1.5 text-caramel-900 font-mono text-[11px] bg-caramel-50 px-2.5 py-0.5 rounded-md border border-caramel-200">
            <Clock className="w-3 h-3 text-caramel-700" />
            {Math.round(trace.total_latency_ms)}ms
          </span>
        )}
      </button>

      {open && (
        <div className="border-t border-[#ebdccb] p-4 space-y-4 text-espresso-900 bg-[#fdfbf9]">
          {/* Auto-Healing Reflection Banner */}
          {trace.auto_healed && (
            <div className="bg-emerald-50 border border-emerald-300 rounded-xl p-3 flex items-start gap-2.5 shadow-xs">
              <span className="text-base leading-none">✨</span>
              <div>
                <span className="font-sans font-bold text-emerald-950 text-xs block">
                  Self-Healing Reflection Loop Triggered
                </span>
                <span className="text-emerald-800 text-[11px] font-sans mt-0.5 block leading-relaxed">
                  Initial API invocation encountered a validation fault. NEXUS inspected the external error hint and automatically self-corrected the parameters without failing the user request.
                </span>
              </div>
            </div>
          )}

          {/* 1. Tools Used (Method & Endpoint) */}
          {hasTools && (
            <div>
              <div className="flex items-center gap-1.5 text-caramel-900 font-sans font-semibold text-[11px] uppercase tracking-wider mb-2">
                <Wrench className="w-3.5 h-3.5 text-caramel-700" />
                Tools Used ({selectedTools.length})
              </div>
              <div className="space-y-1.5">
                {selectedTools.map((t, i) => (
                  <div key={i} className="flex flex-wrap items-center justify-between bg-[#ffffff] border border-[#ebdccb] rounded-lg px-3 py-2 gap-2 shadow-xs">
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                        t.method === 'POST' ? 'bg-amber-100/80 text-amber-950 border border-amber-300' :
                        t.method === 'GET' ? 'bg-emerald-100/80 text-emerald-950 border border-emerald-300' :
                        'bg-orange-100/80 text-orange-950 border border-orange-300'
                      }`}>
                        {t.method || 'GET'}
                      </span>
                      <span className="text-espresso-950 font-medium font-sans text-xs">{t.name || t.tool_id}</span>
                      <code className="text-caramel-950 text-[11px] bg-[#f5ede2] px-1.5 py-0.5 rounded border border-[#e5d3c0]">{t.endpoint}</code>
                    </div>
                    {t.risk_level && (
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${
                        t.risk_level === 'HIGH' ? 'bg-amber-100 text-amber-950 border border-amber-300' : 'bg-stone-100 text-stone-700'
                      }`}>
                        {t.risk_level}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 2. Execution Trace with Timings */}
          {hasTrace && (
            <div>
              <div className="flex items-center gap-1.5 text-caramel-900 font-sans font-semibold text-[11px] uppercase tracking-wider mb-2">
                <Layers className="w-3.5 h-3.5 text-caramel-700" />
                Execution Trace & Latency Breakdown
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-[11px]">
                {trace.intent_latency_ms !== undefined && (
                  <div className="bg-[#ffffff] border border-[#ebdccb] rounded-xl p-2.5 shadow-xs">
                    <span className="text-[#7d6856] block text-[10px] uppercase font-semibold">Intent Routing</span>
                    <span className="text-caramel-800 font-medium text-xs">{Math.round(trace.intent_latency_ms)} ms</span>
                  </div>
                )}
                {trace.retrieval_latency_ms !== undefined && (
                  <div className="bg-[#ffffff] border border-[#ebdccb] rounded-xl p-2.5 shadow-xs">
                    <span className="text-[#7d6856] block text-[10px] uppercase font-semibold">Hybrid Retrieval</span>
                    <span className="text-caramel-800 font-medium text-xs">{Math.round(trace.retrieval_latency_ms)} ms</span>
                  </div>
                )}
                {trace.total_latency_ms !== undefined && (
                  <div className="bg-[#ffffff] border border-[#ebdccb] rounded-xl p-2.5 shadow-xs">
                    <span className="text-[#7d6856] block text-[10px] uppercase font-semibold">Total Pipeline</span>
                    <span className="text-caramel-900 font-bold text-xs">{Math.round(trace.total_latency_ms)} ms</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 3. Raw Response */}
          {hasResults && (
            <div>
              <div className="flex items-center gap-1.5 text-caramel-900 font-sans font-semibold text-[11px] uppercase tracking-wider mb-2">
                <Terminal className="w-3.5 h-3.5 text-caramel-700" />
                Raw API Response
              </div>
              <div className="space-y-2">
                {executionResults.map((r, i) => (
                  <details key={i} className="group border border-[#ebdccb] rounded-xl bg-[#ffffff] overflow-hidden shadow-xs">
                    <summary className="cursor-pointer px-3.5 py-2 flex items-center justify-between text-xs hover:bg-caramel-50/70 transition-colors">
                      <div className="flex items-center gap-2">
                        <span className="text-espresso-950 font-semibold">{r.tool_id}</span>
                        <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                          r.status === 'SUCCESS' ? 'text-emerald-900 bg-emerald-100 border border-emerald-300' : 'text-rose-900 bg-rose-100 border border-rose-300'
                        }`}>
                          {r.status}
                        </span>
                      </div>
                      {r.latency_ms !== undefined && (
                        <span className="text-caramel-800 text-[11px] font-medium">{Math.round(r.latency_ms)}ms</span>
                      )}
                    </summary>
                    <div className="p-3 bg-[#faf5ee] border-t border-[#ebdccb]">
                      <pre className="text-[11px] text-[#4d2d11] overflow-x-auto font-mono whitespace-pre max-h-48">
                        {JSON.stringify(r.response || r.message, null, 2)}
                      </pre>
                    </div>
                  </details>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
