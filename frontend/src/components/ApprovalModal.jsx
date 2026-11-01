import { CheckCircle, XCircle, AlertTriangle, Layers } from 'lucide-react'
import LoadingSpinner from './LoadingSpinner'

export default function ApprovalModal({ interrupt, onApprove, onReject, loading }) {
  if (!interrupt) return null
  const details = interrupt.details || {}
  const steps = details.steps || []
  const hasMultipleSteps = steps.length > 1

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
      <div className="bg-[#ffffff] border border-amber-300/80 rounded-2xl shadow-2xl max-w-lg w-full overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 bg-amber-50/90 border-b border-amber-200/80">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-700 shrink-0" />
            <div>
              <h2 className="font-bold text-espresso-950 text-base tracking-wide">Human Authorization Required</h2>
              <p className="text-xs text-amber-900/80 mt-0.5 font-medium">
                {hasMultipleSteps
                  ? `Review and approve ${steps.length} sequential operations before execution.`
                  : 'Review and approve this operation before live execution.'}
              </p>
            </div>
          </div>
          <span className="text-[11px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-amber-100 text-amber-900 border border-amber-300">
            {details.environment || 'Sandbox'}
          </span>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4 max-h-[75vh] overflow-y-auto">
          {/* Key Summary Box */}
          <div className="bg-[#faf7f2] border border-[#ebdccb] rounded-xl p-4 space-y-2.5 text-sm">
            {details.amount && (
              <Row label="Amount" value={<span className="text-emerald-700 font-bold text-base">{details.amount}</span>} />
            )}
            {details.recipient && (
              <Row label="Recipient" value={<span className="text-espresso-950 font-medium">{details.recipient}</span>} />
            )}
            {!hasMultipleSteps && (
              <>
                <Row label="Action" value={<span className="text-espresso-950 font-medium">{details.tool_name || details.tool_id}</span>} />
                <Row
                  label="Endpoint"
                  value={
                    <span className="font-mono text-xs text-caramel-950 bg-[#f5ede2] px-2 py-0.5 rounded border border-[#e5d3c0]">
                      {details.method} {details.endpoint}
                    </span>
                  }
                />
              </>
            )}
          </div>

          {/* Planned Steps (Multi-Step Plan View) */}
          {hasMultipleSteps && (
            <div>
              <p className="text-xs font-semibold text-[#6b584a] uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-caramel-700" />
                Planned Execution Steps ({steps.length})
              </p>
              <div className="space-y-2">
                {steps.map((st, idx) => (
                  <div key={idx} className="bg-[#ffffff] border border-[#ebdccb] rounded-lg p-3 text-xs space-y-1 shadow-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-espresso-950">
                        {idx + 1}. {st.name || st.tool_id}
                      </span>
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-bold ${
                        st.risk_level === 'HIGH' ? 'bg-amber-100 text-amber-900 border border-amber-300' : 'bg-stone-100 text-stone-700'
                      }`}>
                        {st.method} {st.risk_level}
                      </span>
                    </div>
                    <code className="text-[#6b584a] font-mono text-[11px] block">{st.endpoint}</code>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Collapsible Parameters */}
          {details.parameters && Object.keys(details.parameters).length > 0 && (
            <details className="text-xs border border-[#ebdccb] rounded-lg bg-[#faf7f2]">
              <summary className="cursor-pointer px-3 py-2 text-[#6b584a] hover:text-espresso-950 font-medium">
                View Raw Request Parameters
              </summary>
              <pre className="p-3 pt-0 text-[11px] text-[#4d2d11] overflow-x-auto font-mono">
                {JSON.stringify(details.parameters, null, 2)}
              </pre>
            </details>
          )}

          {/* Action Buttons */}
          <div className="flex gap-3 pt-2">
            <button
              onClick={onApprove}
              disabled={loading}
              className="flex-1 flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-xl transition-all text-sm shadow-sm"
            >
              {loading ? <LoadingSpinner size="sm" /> : <CheckCircle className="w-4 h-4" />}
              Approve &amp; Execute
            </button>
            <button
              onClick={onReject}
              disabled={loading}
              className="flex-1 flex items-center justify-center gap-2 bg-[#fdf4f4] hover:bg-rose-100 border border-rose-200 disabled:opacity-50 disabled:cursor-not-allowed text-rose-800 font-semibold py-2.5 rounded-xl transition-all text-sm"
            >
              <XCircle className="w-4 h-4" />
              Reject
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-[#7d6856] text-xs w-20 shrink-0 font-medium">{label}</span>
      <div className="flex-1 min-w-0">{value}</div>
    </div>
  )
}
