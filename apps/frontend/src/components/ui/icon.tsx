/**
 * Lucide-backed console icons. Direct named imports only; Google stays local.
 *
 * @remarks
 * Decorative icons set `aria-hidden`. Icon-only actions must pass `title` or
 * an adjacent visually hidden label. No CDN, no inline scripts.
 */

import type { LucideIcon } from "lucide-react";
import {
  CircleCheck,
  CircleDashed,
  Clock3,
  FilePenLine,
  TriangleAlert,
  Archive,
  ArrowUp,
  BarChart3,
  Bell,
  CircleHelp,
  Command,
  ChevronDown,
  Eye,
  EyeOff,
  FileText,
  ListChecks,
  Lock,
  LogOut,
  Mail,
  Menu,
  MessageSquare,
  PanelLeft,
  PanelLeftClose,
  MoreHorizontal,
  Plus,
  Search,
  Send,
  Share2,
  Table2,
  Trash2,
  Upload,
  User,
  Users,
  Wrench,
  X,
} from "lucide-react";
import type { ReactElement, SVGProps } from "react";

export type IconName =
  | "checkCircle"
  | "partial"
  | "clock"
  | "fileEdit"
  | "alert"
  | "archive"
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
  | "bell"
  | "help"
  | "google"
  | "chevron"
  | "more"
  | "logout"
  | "command"
  | "panelExpand"
  | "panelCollapse"
  | "arrowUp"
  | "trash";

export type IconProps = SVGProps<SVGSVGElement> & {
  /** Stable icon id from the typed set. */
  name: IconName;
  /** Accessible name. Decorative icons should pass `aria-hidden`. */
  title?: string;
};

const LUCIDE_BY_NAME: Record<Exclude<IconName, "google">, LucideIcon> = {
  checkCircle: CircleCheck,
  partial: CircleDashed,
  clock: Clock3,
  fileEdit: FilePenLine,
  alert: TriangleAlert,
  archive: Archive,
  chat: MessageSquare,
  documents: FileText,
  graph: Share2,
  tables: Table2,
  team: Users,
  tools: Wrench,
  curation: ListChecks,
  usage: BarChart3,
  profile: User,
  search: Search,
  send: Send,
  eye: Eye,
  eyeOff: EyeOff,
  mail: Mail,
  lock: Lock,
  menu: Menu,
  close: X,
  upload: Upload,
  plus: Plus,
  bell: Bell,
  help: CircleHelp,
  chevron: ChevronDown,
  more: MoreHorizontal,
  logout: LogOut,
  command: Command,
  panelExpand: PanelLeft,
  panelCollapse: PanelLeftClose,
  arrowUp: ArrowUp,
  trash: Trash2,
};

/**
 * Render one 18px stroked icon from the Lucide set, or the local Google mark.
 *
 * @param props - Icon name plus native SVG attributes.
 * @returns Inline SVG. No network side effects.
 */
export function Icon({ name, title, className, ...rest }: IconProps): ReactElement {
  const combined = className ? `ui-icon ${className}` : "ui-icon";
  const hidden = title ? undefined : true;
  if (name === "google") {
    return (
      <svg
        viewBox="0 0 24 24"
        width={18}
        height={18}
        fill="none"
        aria-hidden={hidden}
        className={combined}
        {...rest}
      >
        {title ? <title>{title}</title> : null}
        <path
          fill="currentColor"
          d="M21.6 12.23c0-.74-.07-1.45-.19-2.13H12v4.03h5.38a4.6 4.6 0 0 1-2 3.02v2.5h3.23c1.89-1.74 2.99-4.31 2.99-7.42Z"
        />
        <path
          fill="currentColor"
          d="M12 22c2.7 0 4.96-.9 6.61-2.35l-3.23-2.5c-.9.6-2.04.96-3.38.96-2.6 0-4.8-1.76-5.59-4.12H3.09v2.58A10 10 0 0 0 12 22Z"
        />
        <path
          fill="currentColor"
          d="M6.41 13.99A6.01 6.01 0 0 1 6.1 12c0-.69.12-1.36.31-1.99V7.43H3.09A10 10 0 0 0 2 12c0 1.61.39 3.14 1.09 4.57l3.32-2.58Z"
        />
        <path
          fill="currentColor"
          d="M12 5.96c1.47 0 2.79.5 3.82 1.5l2.87-2.87C16.95 2.99 14.7 2 12 2 7.94 2 4.43 4.34 3.09 7.43l3.32 2.58C7.2 7.72 9.4 5.96 12 5.96Z"
        />
      </svg>
    );
  }
  const Lucide = LUCIDE_BY_NAME[name];
  return (
    <Lucide
      size={18}
      strokeWidth={1.75}
      aria-hidden={hidden}
      className={combined}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
    </Lucide>
  );
}
