export interface FinalEventCard {
  id: string;
  title: string;
  summary: string;
  theme: string;
  sectors: string[];
  entities: string[];
  impact_path: string;
  evidence: string[];
  confidence_score: number;
  status: string;
  created_at: string;
}

// ── Event 타임라인 (D-2b) — backend Event/EventUpdate/EventTimelineResponse 와 1:1 ──
// (backend/app/schemas/events.py Event/EventUpdate/EventTimelineResponse). read-only.
export interface Event {
  id: string;
  canonical_title: string;
  status: string; // active | dormant | closed
  first_seen_at: string;
  last_update_at: string;
  heat: number;
  domains: string[];
  tags: string[];
  primary_entity_ids: string[];
  snapshot_card_id: string | null;
}

// EventUpdate.evidence 는 write 시 allowlist 키만 sanitize 됨(url/source_type/role/confidence/
// relation/observed_at). 프론트는 이 알려진 키만 렌더(임의 본문/PII 미노출).
export interface EventUpdateEvidence {
  url?: string;
  source_type?: string;
  role?: string;
  confidence?: number;
  relation?: string;
  observed_at?: string;
}

export interface EventUpdate {
  id: string;
  event_id: string;
  observed_at: string;
  delta_summary: string;
  evidence: EventUpdateEvidence[];
  added_domains: string[];
  source_refs: string[];
  heat_delta: number;
}

export interface EventTimelineResponse {
  event: Event;
  updates: EventUpdate[];
}

export interface EventSearchHit {
  id: string;
  card_id?: string;
  title: string;
  summary: string | null;
  theme: string | null;
  sectors: string[];
  status?: string | null;
  confidence_score: number | null;
  score: number;
  created_at: string | null;
}

export interface EventSearchResponse {
  total: number;
  hits: EventSearchHit[];
}

export interface Theme {
  id: string;
  name: string;
  label?: string;
  description?: string;
  event_count?: number;
}

export interface Sector {
  id: string;
  name: string;
  label?: string;
  description?: string;
  event_count?: number;
}

export interface HealthResponse {
  status: string;
  version?: string;
  components?: { redis?: string; milvus?: string; postgres?: string; opensearch?: string };
  redis?: string;
  milvus?: string;
  postgres?: string;
}

export interface JobStatus {
  id: string;
  status: string;
  created_at: string;
  updated_at?: string;
  error?: string;
}
