import { Link } from 'react-router-dom'

/** The mark is a rounded square with three lines. The last line is shorter and ends in the seal dot. */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="9" fill="var(--ink)" />
      <g stroke="var(--bg-surface)" strokeWidth="2.2" strokeLinecap="round">
        <path d="M8 11h16M8 16h16M8 21h9" />
      </g>
      <circle cx="23" cy="21" r="2.2" fill="var(--seal)" />
    </svg>
  )
}

export function Logo({ to = '/' }: { to?: string }) {
  return (
    <Link to={to} className="inline-flex items-center gap-2.5 rounded-sm" aria-label="Governed Agent Platform home">
      <LogoMark />
      <span className="text-[15px] font-bold tracking-[-0.01em]">Governed Agent Platform</span>
    </Link>
  )
}
