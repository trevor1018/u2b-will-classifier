// Core data types — matches the JSON output from scripts/refresh.py

export type CaseStatus =
  | "solved"        // 已破案
  | "cold"          // 懸案
  | "partial"       // 部分破案
  | "exonerated"    // 平反
  | "ongoing"       // 審理中
  | "unknown";

export type CaseType =
  | "murder"        // 謀殺
  | "missing"       // 失蹤
  | "serial"        // 連環殺手
  | "cult"          // 邪教
  | "fraud"         // 詐欺
  | "robbery"       // 搶劫/竊盜
  | "disaster"      // 災難/事故
  | "mystery"       // 未解之謎
  | "kidnap"        // 綁架
  | "curio"         // 奇人異事
  | "other";

export interface CaseRecord {
  /** YouTube video id */
  id: string;
  /** Original video title */
  title: string;
  /** Cleaned-up case name (without brackets / hooks) */
  caseName: string;
  /** Video description (may be truncated) */
  description?: string;
  /** Thumbnail URL (yt default) */
  thumbnail: string;
  /** YouTube video URL */
  url: string;
  /** ISO date when video was published */
  publishedAt: string;
  /** Engagement stats */
  viewCount: number;
  likeCount: number;
  commentCount: number;
  /** Approx year the crime/event happened (best guess from title) */
  crimeYear?: number;
  /** End year — when the case was closed/verdict (if known) */
  resolveYear?: number;
  /** Country (zh-Hant) */
  country?: string;
  /** City / region */
  city?: string;
  /** Geo coordinates (lon/lat). Lat goes second to match leaflet [lat, lon] later. */
  lat?: number;
  lon?: number;
  /** Case classification */
  caseType: CaseType;
  status: CaseStatus;
  /** Member-only video? */
  memberOnly?: boolean;
  /** Free-form tags from title brackets (e.g. ["懸案", "DNA"]) */
  tags?: string[];
  /** Optional case milestones — for swimlane drilldown */
  milestones?: Array<{ date: string; event: string }>;
}

export interface CasesPayload {
  /** Generation metadata */
  generatedAt: string;
  source: "youtube-api" | "mock";
  channel: {
    id: string;
    handle: string;
    title: string;
  };
  cases: CaseRecord[];
}

// Display palettes (kept here so all views agree)
export const CASE_TYPE_LABEL: Record<CaseType, string> = {
  murder: "謀殺",
  missing: "失蹤",
  serial: "連環",
  cult: "邪教",
  fraud: "詐欺",
  robbery: "搶劫",
  disaster: "災難",
  mystery: "未解之謎",
  kidnap: "綁架",
  curio: "奇人異事",
  other: "其他",
};

export const CASE_TYPE_COLOR: Record<CaseType, string> = {
  murder: "#f87171",
  missing: "#fbbf24",
  serial: "#dc2626",
  cult: "#a855f7",
  fraud: "#f59e0b",
  robbery: "#84cc16",
  disaster: "#fb923c",
  mystery: "#60a5fa",
  kidnap: "#ec4899",
  curio: "#14b8a6",
  other: "#9ca3af",
};

export const STATUS_LABEL: Record<CaseStatus, string> = {
  solved: "已破案",
  cold: "懸案",
  partial: "部分破案",
  exonerated: "平反",
  ongoing: "審理中",
  unknown: "未知",
};

export const STATUS_COLOR: Record<CaseStatus, string> = {
  solved: "#a3e635",
  cold: "#f87171",
  partial: "#fbbf24",
  exonerated: "#22d3ee",
  ongoing: "#60a5fa",
  unknown: "#6b7280",
};
