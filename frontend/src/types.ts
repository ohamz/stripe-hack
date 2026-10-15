export type Category = "included" | "goodwill" | "billable" | "needs_review" | "no_work_logged";

export interface KeyState { ok: boolean; state: string; message: string }

export interface Status {
  llm: KeyState;
  stripe: KeyState & { account: { ok: boolean; id?: string; error?: string } | null; webhooks: boolean };
  clock: { now: string; demo_now: string | null; period: string; display_period: string; display_period_label: string };
  busy: string | null;
  seeded: boolean;
  unprocessed_items: number;
  escalated_disputes: number;
}

export interface ClientCard {
  slug: string;
  name: string;
  contact_name: string;
  period: string;
  tab_total_pence: number;
  favours_used: number;
  favours_free_kind: number;
  favour_allowance: number | null;
  needs_review: number;
  health_badge: string | null;
  beyond_scope_share_pct: number;
  decisions: number;
}

export interface Overview {
  period: string;
  period_label: string;
  stats: {
    recovered_pence: number;
    goodwill_count: number;
    goodwill_value_pence: number;
    needs_review: number;
    invoices_raised: number;
    invoices_paid: number;
    invoices_failed: number;
  };
  clients: ClientCard[];
  unassigned_items: number;
}

export interface AgentEvent {
  id: number;
  ts: string;
  level: "info" | "warn" | "error";
  type: string;
  message: string;
  payload: Record<string, unknown>;
}

export interface EvidenceItem { type: "source_item" | "time_entry" | "clause" | "rule"; id: number | string; label: string }

export interface Decision {
  id: number;
  category: Category;
  clause_refs: string[];
  rule_refs: string[];
  minutes_logged: number;
  minutes_billed: number;
  amount_pence: number;
  value_pence: number;
  explanation: string;
  evidence: EvidenceItem[];
  cognee_query: string;
  cognee_context: string;
  confidence: number;
  counts_towards_allowance: boolean;
  period: string;
  created_at: string;
  remembered_at: string | null;
}

export interface TimeEntry {
  id: number;
  started_at: string;
  started_local: string;
  minutes: number;
  project: string;
  description: string;
  request_id: number | null;
  match_confidence: number | null;
  match_reason: string | null;
  source_item_id: number;
}

export interface RequestRow {
  id: number;
  requested_at: string;
  requested_local: string;
  summary: string;
  quote: string;
  kind: string;
  page_or_asset: string | null;
  revision_round: number | null;
  is_future_work: boolean;
  period: string;
  source: { id: number; source: string; author: string; channel: string; simulated: boolean };
  time_entries: TimeEntry[];
  meeting_minutes: number | null;
  decision: Decision | null;
}

export interface SourceItem {
  id: number;
  source: string;
  simulated: boolean;
  external_id: string;
  occurred_at: string;
  occurred_local: string;
  author: string;
  title: string | null;
  channel: string;
  text: string;
  raw: Record<string, unknown>;
  period: string;
  client_id: number | null;
  cognee_dataset: string | null;
  cognee_node_set: string[];
  remembered_at: string | null;
  processed_at: string | null;
  time_entry?: TimeEntry | null;
}

export interface Term { key: string; clause_ref: string; value: unknown; source_text: string; confidence: number }

export interface Invoice {
  id: number;
  client_id: number;
  client: { slug: string; name: string } | null;
  period: string;
  stripe_invoice_id: string | null;
  stripe_customer_id: string | null;
  status: "draft" | "open" | "paid" | "void" | "failed";
  total_pence: number;
  goodwill_value_pence: number;
  hosted_invoice_url: string | null;
  proof_token: string;
  created_at: string;
  error: string | null;
  notes: string[];
  remembered_at: string | null;
}

export interface ClientDetail {
  client: { id: number; slug: string; name: string; contact_name: string; contact_email: string; cognee_dataset: string; stripe_customer_id: string | null };
  card: ClientCard;
  terms: Term[];
  periods: { period: string; label: string; history: boolean }[];
  period: string;
  period_label: string;
  is_history: boolean;
  requests: RequestRow[];
  pending_items: SourceItem[];
  not_requests: SourceItem[];
  history_items: SourceItem[];
  unmatched_time: TimeEntry[];
  invoices: Invoice[];
  llm_ok: boolean;
}

export interface HealthNumbers {
  minutes_total: number;
  minutes_in_scope: number;
  minutes_beyond_scope: number;
  hours_total: number;
  hours_in_scope: number;
  hours_beyond_scope: number;
  beyond_scope_share_pct: number;
  favours_used: number;
  favours_free_kind: number;
  favours_value_pence: number;
  amount_billed_pence: number;
  needs_review: number;
  badge: string;
}

export interface Health {
  period: string;
  period_label: string;
  numbers: HealthNumbers;
  has_decisions: boolean;
  narrative: { paragraph: string | null; withheld_reason: string | null; cognee_query: string; cognee_context: string; generated_at: string } | null;
  llm_ok: boolean;
}

export interface RecallAnswer {
  query: string;
  query_type: string;
  datasets: string[];
  node_name: string[] | null;
  answer: string;
  evidence_block: string;
  references: Record<string, unknown>[];
  context: string;
}

export interface Dispute {
  id: number;
  invoice_line_id: number;
  message: string;
  created_at: string;
  agent_reply: string;
  outcome: "upheld" | "escalated";
  outcome_reason?: string;
  cognee_context?: string;
}

export interface InvoiceDetail extends Invoice {
  lines: {
    id: number;
    decision_id: number;
    stripe_invoice_item_id: string | null;
    description: string;
    amount_pence: number;
    is_goodwill: boolean;
    decision: Decision;
    request_summary: string;
    disputes: Dispute[];
  }[];
}

export interface ProofLine {
  line_id: number;
  description: string;
  amount_pence: number;
  value_pence: number;
  summary: string;
  evidence: {
    message: { quote: string; date: string; day: string; source: string; channel: string; author: string; simulated: boolean };
    time: { date: string; minutes: number; description: string }[];
    minutes_logged: number;
    minutes_billed: number;
    clauses: { ref: string; text: string }[];
    explanation: string;
  };
  disputes: Dispute[];
}

export interface Proof {
  business_name: string;
  freelancer_name: string;
  client_name: string;
  period: string;
  period_label: string;
  total_pence: number;
  goodwill_value_pence: number;
  status: string;
  hosted_invoice_url: string | null;
  extra_work: ProofLine[];
  on_the_house: ProofLine[];
}

export interface Rule {
  id: number;
  rule_ref: string;
  text: string;
  params: Record<string, unknown> | null;
  enabled: boolean;
  parse_status: "pending" | "parsed" | "not_understood" | "error";
  parse_note: string | null;
  applies_to: string;
}

export interface SettingsPayload {
  integrations: Record<string, { mode: string; detail: string | null }>;
  rules: Rule[];
  clock: { now: string; demo_now: string | null };
  clients: { slug: string; name: string }[];
}

export interface MemoryStats {
  node_sets: string[];
  clients: { slug: string; name: string; dataset: string; remembered: Record<string, number>; pending: Record<string, number>; graph_available: boolean }[];
  llm_ok: boolean;
}
