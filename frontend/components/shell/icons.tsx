// Minimal 1.5px-stroke icon set for the app shell (16–18px, inherits currentColor).
const p = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

export const DashboardIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <rect x="3" y="3" width="8" height="8" rx="2" />
    <rect x="13" y="3" width="8" height="5" rx="2" />
    <rect x="13" y="10" width="8" height="11" rx="2" />
    <rect x="3" y="13" width="8" height="8" rx="2" />
  </svg>
);

export const CaptionsIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <rect x="3" y="5" width="18" height="14" rx="3" />
    <path d="M7 12h4m-4 3h7m3-3h3m-3 3h3" />
  </svg>
);

export const TranslateIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <path d="M4 5h9M8.5 3v2c0 4-2.5 7-5 8m1.5-5c1.5 3 4 5.5 7 6.5M13 21l4.5-10L22 21m-7.6-3.5h6.2" />
  </svg>
);

export const CommunityIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <circle cx="9" cy="8" r="3.2" />
    <path d="M3.5 20c.6-3.2 2.8-5 5.5-5s4.9 1.8 5.5 5M16 5.5a3.2 3.2 0 0 1 0 5.8M17.8 15.2c1.6.7 2.6 2.3 3 4.8" />
  </svg>
);

export const HistoryIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <path d="M4 12a8 8 0 1 1 2.3 5.6M4 12l-1.5-2M4 12l2.2-1.2M12 8v4l3 2" />
  </svg>
);

export const PremiumIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <path d="m12 3 2.7 5.6 6.3.8-4.6 4.3 1.2 6.1L12 16.9l-5.6 2.9 1.2-6.1L3 9.4l6.3-.8Z" />
  </svg>
);

export const SavedIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1Z" />
  </svg>
);

export const SharedIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <circle cx="6" cy="12" r="2.5" />
    <circle cx="17.5" cy="5.5" r="2.5" />
    <circle cx="17.5" cy="18.5" r="2.5" />
    <path d="m8.3 10.8 7-4M8.3 13.2l7 4" />
  </svg>
);

export const LogoutIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <path d="M14 4H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h8M10 12h11m0 0-3.5-3.5M21 12l-3.5 3.5" />
  </svg>
);

export const SearchIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </svg>
);

export const BellIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <path d="M18 9a6 6 0 1 0-12 0c0 6-2.5 7-2.5 7h17S18 15 18 9M10.3 20a2 2 0 0 0 3.4 0" />
  </svg>
);

export const UserIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4.5 20.5c1-3.8 4-6 7.5-6s6.5 2.2 7.5 6" />
  </svg>
);

export const MenuIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </svg>
);

export const CloseIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <path d="m6 6 12 12M18 6 6 18" />
  </svg>
);

export const MicIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
);

export const SendIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <path d="m22 2-7 20-4-9-9-4Z" />
  </svg>
);

/** Holds a live session without ending it. Paired with `MicIcon` on resume. */
export const PauseIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <path d="M9 5v14M15 5v14" />
  </svg>
);

export const PlayIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor" stroke="none">
    <path d="M7 4.5v15l13-7.5Z" />
  </svg>
);
