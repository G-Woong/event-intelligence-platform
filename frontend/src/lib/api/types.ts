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
  title: string;
  summary: string;
  theme: string;
  sectors: string[];
  confidence_score: number;
  created_at: string;
  score?: number;
}

export interface EventSearchResponse {
  total: number;
  hits: EventSearchHit[];
}

export interface Theme {
  id: string;
  name: string;
  description?: string;
  event_count?: number;
}

export interface Sector {
  id: string;
  name: string;
  description?: string;
  event_count?: number;
}

export interface HealthResponse {
  status: string;
  components?: Record<string, string>;
  version?: string;
}

export interface JobStatus {
  id: string;
  status: string;
  created_at: string;
  updated_at?: string;
  error?: string;
}
