import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { MessageSquare, Database, BarChart3, FileText, Zap, Menu, X } from 'lucide-react'

const NAV = [
  { path: '/', icon: MessageSquare, label: 'Chat' },
  { path: '/registry', icon: Database, label: 'Tool Registry' },
  { path: '/dashboard', icon: BarChart3, label: 'Dashboard' },
  { path: '/logs', icon: FileText, label: 'System Logs' },
]

export default function Layout({ children }) {
  const location = useLocation()
  const [open, setOpen] = useState(true)

  return (
    <div className="flex h-screen bg-[#faf7f2] text-espresso-900 overflow-hidden font-sans">
      {/* Sidebar */}
      <aside
        className={`${open ? 'w-56' : 'w-16'} flex-shrink-0 transition-all duration-200 bg-[#ffffff] border-r border-[#ebdccb] flex flex-col shadow-soft z-20`}
      >
        {/* Logo */}
        <div className="flex items-center gap-2.5 px-3.5 py-4 border-b border-[#ebdccb]">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-caramel-100 to-caramel-200/80 border border-caramel-300 flex items-center justify-center flex-shrink-0 shadow-xs">
            <Zap className="w-4 h-4 text-caramel-700" />
          </div>
          {open && (
            <div className="flex flex-col">
              <span className="font-bold text-sm tracking-wider text-espresso-950">
                NEXUS
              </span>
              <span className="text-[10px] text-caramel-700 font-mono tracking-widest uppercase font-semibold">Orchestrator</span>
            </div>
          )}
        </div>

        {/* Nav links */}
        <nav className="flex-1 p-2 space-y-1.5">
          {NAV.map(({ path, icon: Icon, label }) => {
            const active = location.pathname === path
            return (
              <Link
                key={path}
                to={path}
                title={!open ? label : undefined}
                className={`flex items-center gap-3 px-3 py-2 rounded-xl transition-all duration-150 text-sm ${
                  active
                    ? 'bg-caramel-100/90 text-caramel-950 border border-caramel-300/80 shadow-xs font-semibold'
                    : 'text-[#6b584a] hover:bg-caramel-50/80 hover:text-espresso-950 hover:border hover:border-caramel-200/70'
                }`}
              >
                <Icon className={`w-4 h-4 flex-shrink-0 ${active ? 'text-caramel-700' : 'text-caramel-600/80'}`} />
                {open && <span className="truncate">{label}</span>}
              </Link>
            )
          })}
        </nav>

        {/* Collapse toggle */}
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center justify-center p-3 border-t border-[#ebdccb] text-[#8c6f58] hover:text-espresso-950 hover:bg-caramel-50/70 transition-colors"
        >
          {open ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
        </button>
      </aside>

      {/* Page content */}
      <main className="flex-1 overflow-hidden flex flex-col min-w-0 bg-[#faf7f2]">
        {children}
      </main>
    </div>
  )
}
