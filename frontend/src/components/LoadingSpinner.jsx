export default function LoadingSpinner({ size = 'md', text = '' }) {
  const sz = { sm: 'w-4 h-4 border', md: 'w-6 h-6 border-2', lg: 'w-10 h-10 border-2' }
  return (
    <div className="flex items-center gap-2.5">
      <div className={`${sz[size]} border-caramel-600 border-t-transparent rounded-full animate-spin`} />
      {text && <span className="text-caramel-950 text-xs font-semibold">{text}</span>}
    </div>
  )
}
