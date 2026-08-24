export type SearchMode = "keyword" | "vector" | "hybrid" | "auto";

export interface AuthSession {
  user_id: number | null;
  username: string;
  display_name: string | null;
  role: "admin" | "project_manager" | "viewer";
  capabilities: string[];
  sessionTimeoutMinutes: number;
}

export interface Project {
  id: number;
  name: string;
  description: string | null;
  photo_library_path: string;
  thumbnail_path: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  total: number;
  items: Project[];
}

export interface Photo {
  id: number;
  project_id: number;
  file_name: string;
  mime_type: string | null;
  width: number | null;
  height: number | null;
  taken_at: string | null;
  file_size: number | null;
  status: string;
  thumbnail_path: string | null;
  updated_at: string;
}

export interface PhotoDetail extends Photo {
  gps_latitude: number | null;
  gps_longitude: number | null;
  country_name: string | null;
  admin1: string | null;
  admin2: string | null;
  city: string | null;
  district: string | null;
  formatted_address: string | null;
  camera_make: string | null;
  camera_model: string | null;
  lens_model: string | null;
  focal_length: string | null;
  aperture: string | null;
  exposure_time: string | null;
  iso: number | null;
}

export interface PhotoListResponse {
  total: number;
  page: number;
  page_size: number;
  items: Photo[];
  next_cursor?: string | null;
  has_more?: boolean | null;
}

export interface SearchResultItem {
  photo_id: number;
  file_name: string;
  thumbnail_url: string;
  updated_at: string;
  taken_at: string | null;
  width: number | null;
  height: number | null;
  caption: string | null;
  matched_tags: string[];
  score: number;
}

export interface SearchResponse {
  query: string;
  total: number;
  page: number;
  page_size: number;
  items: SearchResultItem[];
}
