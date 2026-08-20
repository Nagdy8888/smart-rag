/**
 * CSP-safe local SVG icons. No Material Symbols CDN and no inline scripts.
 */

import type { ReactElement, SVGProps } from "react";

export type IconName =
  | "chat"
  | "documents"
  | "graph"
  | "tables"
  | "team"
  | "tools"
  | "curation"
  | "usage"
  | "profile"
  | "search"
  | "send"
  | "eye"
  | "eyeOff"
  | "mail"
  | "lock"
  | "menu"
  | "close"
  | "upload"
  | "plus"
  | "spark"
  | "bell"
  | "help"
  | "google";

export type IconProps = SVGProps<SVGSVGElement> & {
  /** Stable icon id from the typed set. */
  name: IconName;
  /** Accessible name. Decorative icons should pass `aria-hidden`. */
  title?: string;
};

const VIEW = "0 0 24 24";

/**
 * Render one stroked SVG icon from the local set.
 *
 * @param props - Icon name plus native SVG attributes.
 * @returns Inline SVG. No network side effects.
 */
export function Icon({ name, title, className, ...rest }: IconProps) {
  const combined = className ? `ui-icon ${className}` : "ui-icon";
  return (
    <svg
      viewBox={VIEW}
      width={20}
      height={20}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      className={combined}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      {iconPath(name)}
    </svg>
  );
}

/**
 * Return the path nodes for a named icon.
 *
 * @param name - Typed icon id.
 * @returns SVG children.
 */
function iconPath(name: IconName): ReactElement {
  switch (name) {
    case "chat":
      return (
        <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v8A2.5 2.5 0 0 1 17.5 17H9l-4 3v-3.5A2.5 2.5 0 0 1 4 14.5z" />
      );
    case "documents":
      return (
        <>
          <path d="M7 4h7l4 4v12H7z" />
          <path d="M14 4v4h4" />
        </>
      );
    case "graph":
      return (
        <>
          <circle cx="6" cy="17" r="2" />
          <circle cx="12" cy="7" r="2" />
          <circle cx="18" cy="14" r="2" />
          <path d="M8 16l3.2-7.2M13.7 8.7 16.5 13" />
        </>
      );
    case "tables":
      return (
        <>
          <rect x="4" y="5" width="16" height="14" rx="1.5" />
          <path d="M4 10h16M10 5v14" />
        </>
      );
    case "team":
      return (
        <>
          <circle cx="9" cy="8" r="2.2" />
          <circle cx="16" cy="9" r="1.8" />
          <path d="M4.5 18c.4-2.6 2.4-4 4.5-4s4.1 1.4 4.5 4" />
          <path d="M14 18c.2-1.8 1.4-3 3-3 1.5 0 2.6 1 2.8 2.6" />
        </>
      );
    case "tools":
      return (
        <path d="M14.7 6.3a4 4 0 0 0-5.6 5.6L4 17l3 3 5.1-5.1a4 4 0 0 0 5.6-5.6L15 12l-3-3z" />
      );
    case "curation":
      return (
        <>
          <path d="M5 7h14M5 12h10M5 17h7" />
          <path d="m15 15 2 2 3-3" />
        </>
      );
    case "usage":
      return (
        <>
          <path d="M4 19V5" />
          <path d="M4 19h16" />
          <path d="M8 15v-4M12 15V8M16 15v-6" />
        </>
      );
    case "profile":
      return (
        <>
          <circle cx="12" cy="8" r="3" />
          <path d="M5 19c1.2-3.2 3.4-5 7-5s5.8 1.8 7 5" />
        </>
      );
    case "search":
      return (
        <>
          <circle cx="11" cy="11" r="6" />
          <path d="m20 20-3.5-3.5" />
        </>
      );
    case "send":
      return <path d="M4 12 20 4l-7 16-2-7z" />;
    case "eye":
      return (
        <>
          <path d="M2.5 12S6 6.5 12 6.5 21.5 12 21.5 12 18 17.5 12 17.5 2.5 12 2.5 12z" />
          <circle cx="12" cy="12" r="2.5" />
        </>
      );
    case "eyeOff":
      return (
        <>
          <path d="M3 3l18 18" />
          <path d="M10.6 10.6A2.5 2.5 0 0 0 12 14.5" />
          <path d="M6.1 6.7C4 8.3 2.5 12 2.5 12S6 17.5 12 17.5c1.6 0 3-.3 4.2-.8M9.2 5.2C10.1 5 11 4.9 12 4.9 18 4.9 21.5 10.4 21.5 10.4s-.8 1.3-2.2 2.8" />
        </>
      );
    case "mail":
      return (
        <>
          <rect x="3.5" y="5.5" width="17" height="13" rx="2" />
          <path d="m4 7 8 6 8-6" />
        </>
      );
    case "lock":
      return (
        <>
          <rect x="5" y="11" width="14" height="9" rx="2" />
          <path d="M8 11V8a4 4 0 0 1 8 0v3" />
        </>
      );
    case "menu":
      return (
        <>
          <path d="M4 7h16M4 12h16M4 17h16" />
        </>
      );
    case "close":
      return <path d="M6 6l12 12M18 6 6 18" />;
    case "upload":
      return (
        <>
          <path d="M12 16V5" />
          <path d="m8 9 4-4 4 4" />
          <path d="M5 19h14" />
        </>
      );
    case "plus":
      return <path d="M12 5v14M5 12h14" />;
    case "spark":
      return <path d="M12 3v4M12 17v4M4.9 6.5l2.8 2.8M16.3 14.7l2.8 2.8M3 12h4M17 12h4M4.9 17.5l2.8-2.8M16.3 9.3l2.8-2.8" />;
    case "bell":
      return (
        <>
          <path d="M6 16h12l-1-3V10a5 5 0 0 0-10 0v3z" />
          <path d="M10 16v1a2 2 0 0 0 4 0v-1" />
        </>
      );
    case "help":
      return (
        <>
          <circle cx="12" cy="12" r="8.5" />
          <path d="M9.6 9.4a2.4 2.4 0 1 1 3.3 3.2c-.7.5-1.1 1-.1 1.6" />
          <path d="M12 16.8h.01" />
        </>
      );
    case "google":
      return (
        <>
          <path d="M21 12.2a8.8 8.8 0 1 1-3-6.7" />
          <path d="M21 12h-9" />
        </>
      );
    default:
      return <circle cx="12" cy="12" r="8" />;
  }
}
