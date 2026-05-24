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
