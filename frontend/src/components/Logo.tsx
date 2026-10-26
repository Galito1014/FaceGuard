export default function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden>
      <defs>
        <linearGradient id="fg-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#45a6ff" />
          <stop offset="1" stopColor="#0b6fe0" />
        </linearGradient>
      </defs>
      <path d="M32 5 53 13v17c0 14-9 24-21 29C20 54 11 44 11 30V13Z" fill="rgba(31,139,255,.12)" stroke="url(#fg-g)" strokeWidth="3.5" />
      <circle cx="32" cy="27" r="7" fill="none" stroke="#7cc4ff" strokeWidth="3" />
      <path d="M21 44c2.5-5 6.5-7.5 11-7.5S40.5 39 43 44" fill="none" stroke="#7cc4ff" strokeWidth="3" strokeLinecap="round" />
      <path d="M17 19h6M41 19h6M17 19v5M47 19v5" stroke="#45a6ff" strokeWidth="2" strokeLinecap="round" opacity=".7" />
    </svg>
  );
}
