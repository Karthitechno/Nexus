import { useState, useRef, useEffect } from 'react'
import { Send, RefreshCw, Zap, Sparkles } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { sendChat, approveChat } from '../api/client'
import ApprovalModal from '../components/ApprovalModal'
import TracePanel from '../components/TracePanel'
import LoadingSpinner from '../components/LoadingSpinner'

const EXAMPLES = [
  'Send an invoice for $50 to bob@example.com',
  'List all pending invoices',
  'What was my total sales volume last month?',
  'Is there a dispute open from user_123?',
  'Create a new invoice for $200',
  'Show all available tools in the registry',
  'What does the documentation say about refunds?',
  'Search for payment tools',
  'Get transaction history for last month',
  'Check if there are any open disputes',
]

function Bubble({ msg }) {
  const isUser = msg.role === 'user'

  // Strip any raw HTML tags (e.g. legacy <small> or <color>) so user never sees unparsed HTML
  const cleanedContent = (msg.content || '')
    .replace(/<small[^>]*>(.*?)<\/small>/gis, '$1')
    .replace(/<\/?[a-z][a-z0-9]*[^<>]*>/gis, '')
    .trim()

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-5`}>
      <div className={`max-w-3xl w-full ${isUser ? 'pl-12' : 'pr-12'}`}>
        {/* Text bubble */}
        <div
          className={`px-4 py-3.5 rounded-2xl transition-all ${
            isUser
              ? 'bg-gradient-to-r from-caramel-600 to-caramel-700 text-white rounded-br-none ml-auto w-fit max-w-full shadow-md shadow-caramel-800/15 border border-caramel-500/30'
              : 'bg-[#ffffff] border border-[#ebdccb] text-espresso-900 rounded-bl-none shadow-soft'
          }`}
        >
          {isUser ? (
            <p className="text-sm leading-relaxed font-medium">{msg.content}</p>
          ) : (
            <div className="prose-dark text-sm">
              <ReactMarkdown>{cleanedContent || ''}</ReactMarkdown>
            </div>
          )}
        </div>

        {/* Technical Details Expander (Tools, Execution Trace, Raw Response) */}
        {!isUser && (
          <div className="mt-2.5">
            <TracePanel
              trace={msg.trace}
              selectedTools={msg.selectedTools}
              executionResults={msg.executionResults}
            />
          </div>
        )}
      </div>
    </div>
  )
}

export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [threadId, setThreadId] = useState(null)
  const [pendingApproval, setPendingApproval] = useState(null)
  const [approvalLoading, setApprovalLoading] = useState(false)
  const [thoughtStage, setThoughtStage] = useState('Analyzing user intent and domain…')
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  useEffect(() => {
    if (!loading) return
    const stages = [
      'Analyzing user intent and domain…',
      'Executing BM25 & ChromaDB hybrid retrieval…',
      'Cross-Encoder reranking top-k candidates…',
      'Validating schema slots & DAG dependencies…',
      'Executing sandbox operations…',
    ]
    let idx = 0
    setThoughtStage(stages[0])
    const iv = setInterval(() => {
      idx = (idx + 1) % stages.length
      setThoughtStage(stages[idx])
    }, 850)
    return () => clearInterval(iv)
  }, [loading])

  const doSend = async (query) => {
    query = (query || input).trim()
    if (!query || loading) return
    setInput('')
    setError(null)
    setMessages((m) => [...m, { role: 'user', content: query }])
    setLoading(true)
    try {
      const res = await sendChat(query, threadId, [])
      setThreadId(res.thread_id)
      if (res.status === 'PENDING_APPROVAL') {
        setPendingApproval({ interrupt: res.interrupt, threadId: res.thread_id })
        setMessages((m) => [
          ...m,
          {
            role: 'assistant',
            content:
              '⏳ **Approval required.** This operation mutates live data in the Sandbox. Please review and authorize below.',
            intent: res.intent,
          },
        ])
      } else {
        setMessages((m) => [
          ...m,
          {
            role: 'assistant',
            content: res.response || '*No response.*',
            intent: res.intent,
            selectedTools: res.selected_tools || [],
            trace: res.trace || {},
            executionResults: res.execution_results || [],
            approvalStatus: res.approval_status,
          },
        ])
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const doApproval = async (approved) => {
    if (!pendingApproval) return
    setApprovalLoading(true)
    try {
      const res = await approveChat(pendingApproval.threadId, approved)
      setPendingApproval(null)
      setMessages((m) => {
        const copy = [...m]
        copy[copy.length - 1] = {
          role: 'assistant',
          content: res.response || (approved ? 'Approved and executed.' : 'Operation rejected.'),
          requestId: res.request_id,
          executionResults: res.execution_results || [],
          trace: res.trace || {},
          approvalStatus: res.approval_status,
        }
        return copy
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setApprovalLoading(false)
    }
  }

  const newThread = () => {
    setThreadId(null)
    setMessages([])
    setError(null)
    setPendingApproval(null)
  }

  return (
    <div className="flex h-full overflow-hidden bg-[#faf7f2]">
      {/* ── Chat Main View ── */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3.5 border-b border-[#ebdccb] bg-[#ffffff]/90 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <h1 className="font-bold text-espresso-950 text-base">NEXUS Chat</h1>
            <span className="text-[10px] font-semibold tracking-wider uppercase px-2 py-0.5 rounded-full bg-caramel-100 text-caramel-900 border border-caramel-300/80">
              Agentic Mode
            </span>
            {threadId && (
              <p className="text-xs text-caramel-700 font-mono">session: {threadId.slice(0, 8)}</p>
            )}
          </div>
          <button
            onClick={newThread}
            className="flex items-center gap-1.5 text-xs font-semibold text-caramel-900 hover:text-caramel-950 px-3 py-1.5 rounded-xl bg-white hover:bg-caramel-50 border border-[#ebdccb] transition-all shadow-xs"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            New Thread
          </button>
        </div>

        {/* Messages list */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-2">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full gap-5 text-center max-w-lg mx-auto py-12">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-caramel-100 to-caramel-200 border border-caramel-300 flex items-center justify-center shadow-caramel-sm">
                <Sparkles className="w-8 h-8 text-caramel-700" />
              </div>
              <div className="space-y-2">
                <h2 className="text-2xl font-bold text-espresso-950">
                  NEXUS Tool Orchestration
                </h2>
                <p className="text-[#6b584a] text-sm leading-relaxed">
                  Execute PayPal APIs, inspect customer disputes, review balances, and explore tools.
                  Tools are retrieved dynamically on-demand — the LLM never sees the full catalog.
                </p>
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <Bubble key={i} msg={msg} />
          ))}

          {loading && (
            <div className="flex justify-start mb-5">
              <div className="bg-[#ffffff] border border-[#ebdccb] rounded-2xl rounded-bl-none px-4 py-3 shadow-soft flex items-center gap-3">
                <LoadingSpinner size="sm" />
                <span className="text-xs text-caramel-900 font-sans font-medium animate-pulse">{thoughtStage}</span>
              </div>
            </div>
          )}

          {error && (
            <div className="bg-rose-50 border border-rose-300 text-rose-800 px-4 py-3 rounded-xl text-sm mb-4">
              {error}
            </div>
          )}

          <div ref={endRef} />
        </div>

        {/* Input area */}
        <div className="px-6 pb-5 pt-3 border-t border-[#ebdccb] bg-[#ffffff]/90 backdrop-blur-md">
          <div className="flex gap-3">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  doSend()
                }
              }}
              placeholder="Ask me anything… e.g. 'Create an invoice for $50 to bob@example.com'"
              disabled={loading}
              className="flex-1 bg-[#faf7f2] border border-[#dec7af] rounded-xl px-4 py-3 text-sm text-espresso-950 placeholder-[#a8927e] focus:outline-none focus:bg-white focus:border-caramel-500 focus:ring-1 focus:ring-caramel-500/30 transition-all disabled:opacity-50"
            />
            <button
              onClick={() => doSend()}
              disabled={loading || !input.trim()}
              className="bg-gradient-to-r from-caramel-600 to-caramel-700 hover:from-caramel-500 hover:to-caramel-600 disabled:opacity-40 disabled:cursor-not-allowed text-white font-bold px-4 py-3 rounded-xl transition-all shadow-md shadow-caramel-800/15 flex items-center justify-center shrink-0"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* ── Example queries sidebar ── */}
      <div className="w-64 border-l border-[#ebdccb] bg-[#fcfaf7] flex flex-col shrink-0">
        <div className="px-4 py-3.5 border-b border-[#ebdccb]">
          <p className="text-[11px] font-semibold text-caramel-800 uppercase tracking-widest">Suggested Scenarios</p>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {EXAMPLES.map((q, i) => (
            <button
              key={i}
              onClick={() => doSend(q)}
              disabled={loading}
              className="w-full text-left text-xs text-[#5a483a] hover:text-espresso-950 bg-[#ffffff] hover:bg-caramel-50/80 border border-[#ebdccb] hover:border-caramel-400 rounded-xl px-3 py-2.5 transition-all disabled:opacity-40 leading-relaxed shadow-xs"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {/* Approval modal */}
      {pendingApproval && (
        <ApprovalModal
          interrupt={pendingApproval.interrupt}
          onApprove={() => doApproval(true)}
          onReject={() => doApproval(false)}
          loading={approvalLoading}
        />
      )}
    </div>
  )
}
