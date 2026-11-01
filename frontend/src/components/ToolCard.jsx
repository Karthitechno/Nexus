import { useState } from 'react'
import { ChevronDown, ChevronRight, ShieldAlert, Zap } from 'lucide-react'

const METHOD_STYLE = {
  GET:    'bg-emerald-50 text-emerald-900 border-emerald-300',
  POST:   'bg-amber-50 text-amber-950 border-amber-300',
  PUT:    'bg-orange-50 text-orange-950 border-orange-300',
  DELETE: 'bg-rose-50 text-rose-950 border-rose-300',
  PATCH:  'bg-purple-50 text-purple-950 border-purple-300',
}

export default function ToolCard({ tool, score, reason, compact = false }) {
  const [expanded, setExpanded] = useState(!compact)
  const mStyle = METHOD_STYLE[tool.method] || 'bg-stone-100 text-stone-800 border-stone-300'
  const isHigh = tool.risk_level === 'HIGH'
  const props = tool.parameters?.properties || {}
  const required = tool.parameters?.required || []

  return (
    <div
      className={`border rounded-xl overflow-hidden text-sm transition-all shadow-soft ${
        isHigh
          ? 'border-amber-300/90 bg-amber-50/20'
          : 'border-[#ebdccb] bg-[#ffffff] hover:border-caramel-400'
      }`}
    >
      {/* Header row */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left hover:bg-caramel-50/60 transition-colors"
      >
        <span className={`shrink-0 text-[11px] font-mono font-bold px-2 py-0.5 rounded border ${mStyle}`}>
          {tool.method}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-espresso-950 font-semibold truncate text-xs sm:text-sm">{tool.name}</span>
            {isHigh && (
              <ShieldAlert className="w-3.5 h-3.5 text-amber-600 shrink-0" title="High-risk – requires approval" />
            )}
          </div>
          <span className="text-[11px] text-[#7d6856] truncate block font-mono">{tool.service} › {tool.category}</span>
        </div>
        {score !== undefined && (
          <span className="text-xs font-mono text-caramel-800 shrink-0 font-bold">{Number(score).toFixed(3)}</span>
        )}
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-caramel-700 shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-caramel-700 shrink-0" />
        )}
      </button>

      {/* Body */}
      {expanded && (
        <div className="px-3.5 pb-3.5 pt-2 space-y-2.5 border-t border-[#ebdccb]">
          <code className="block text-xs font-mono text-caramel-950 bg-[#f5ede2] px-2.5 py-1.5 rounded-lg border border-[#e5d3c0]">
            {tool.endpoint}
          </code>

          {tool.description && (
            <p className="text-xs text-[#4a392b] leading-relaxed">{tool.description}</p>
          )}

          {reason && (
            <div className="text-xs text-caramel-950 bg-caramel-50/90 border border-caramel-200 rounded-lg px-2.5 py-1.5">
              <span className="font-semibold text-caramel-900">Selection reason:</span> {reason}
            </div>
          )}

          {Object.keys(props).length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-[#7d6856] uppercase tracking-wider mb-1.5">Parameters</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.keys(props).map((k) => (
                  <span
                    key={k}
                    className={`text-xs font-mono px-2 py-0.5 rounded ${
                      required.includes(k)
                        ? 'bg-rose-50 text-rose-800 border border-rose-200'
                        : 'bg-[#f5ede2] text-espresso-950 border border-[#ebdccb]'
                    }`}
                  >
                    {k}{required.includes(k) ? '*' : ''}
                  </span>
                ))}
              </div>
              <p className="text-[10px] text-[#8f7560] mt-1">* required</p>
            </div>
          )}

          {tool.example_queries?.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-[#7d6856] uppercase tracking-wider mb-1">Example queries</p>
              <ul className="space-y-1">
                {tool.example_queries.slice(0, 3).map((q, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-xs text-[#5c493c]">
                    <Zap className="w-3 h-3 text-caramel-700 mt-0.5 shrink-0" />
                    {q}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
