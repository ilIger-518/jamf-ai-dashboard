// ── Auth ──────────────────────────────────────────────────────────────────────
export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserResponse {
  id: string;
  username: string;
  email: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
}

// ── Jamf Server ───────────────────────────────────────────────────────────────
export interface JamfServer {
  id: string;
  name: string;
  url: string;
  is_active: boolean;
  last_sync: string | null;
  device_count: number;
}

// ── Devices ───────────────────────────────────────────────────────────────────
export type DeviceType = "computer" | "mobile";
export type DeviceStatus = "managed" | "unmanaged" | "pending";

export interface Device {
  id: string;
  jamf_id: number;
  server_id: string;
  name: string;
  serial_number: string;
  device_type: DeviceType;
  status: DeviceStatus;
  os_version: string | null;
  os_build: string | null;
  model: string | null;
  username: string | null;
  last_check_in: string | null;
  is_supervised: boolean;
  is_enrolled: boolean;
  updated_at: string;
}

export interface DeviceListResponse {
  items: Device[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// ── Policies ──────────────────────────────────────────────────────────────────
export interface Policy {
  id: string;
  jamf_id: number;
  server_id: string;
  name: string;
  enabled: boolean;
  trigger: string | null;
  scope_all: boolean;
  updated_at: string;
}

// ── Smart Groups ──────────────────────────────────────────────────────────────
export interface SmartGroup {
  id: string;
  jamf_id: number;
  server_id: string;
  name: string;
  group_type: "computer" | "mobile";
  is_smart: boolean;
  member_count: number;
  updated_at: string;
}

// ── Patch ─────────────────────────────────────────────────────────────────────
export interface PatchTitle {
  id: string;
  server_id: string;
  name: string;
  software_title_id: string;
  latest_version: string | null;
  updated_at: string;
}

// ── Compliance ────────────────────────────────────────────────────────────────
export type ComplianceStatus = "compliant" | "non_compliant" | "unknown";

export interface ComplianceResult {
  id: string;
  device_id: string;
  device_name: string;
  check_name: string;
  status: ComplianceStatus;
  details: string | null;
  checked_at: string;
}

// ── AI / Chat ─────────────────────────────────────────────────────────────────
export interface ChatSession {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export type MessageRole = "user" | "assistant" | "system";

export interface ChatMessage {
  id: string;
  session_id: string;
  role: MessageRole;
  content: string;
  sources: string[] | null;
  created_at: string;
}

export type PendingActionStatus = "pending" | "approved" | "rejected";

export interface PendingAction {
  id: string;
  session_id: string;
  tool_name: string;
  parameters: Record<string, unknown>;
  human_readable_summary: string;
  status: PendingActionStatus;
  created_at: string;
}

// ── Pagination ────────────────────────────────────────────────────────────────
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}
