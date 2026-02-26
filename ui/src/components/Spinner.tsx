export function Spinner({ size = 24 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className="animate-spin"
      style={{ filter: "drop-shadow(0 0 6px #00e5ff)" }}
    >
      <circle cx="12" cy="12" r="10" stroke="#1e293b" strokeWidth="3" />
      <path
        d="M12 2a10 10 0 0 1 10 10"
        stroke="#00e5ff"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}
