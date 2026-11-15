/**
 * PlanetX Persistent Astronomical Candidate & Scientific Submission Types
 */

export type CandidateType =
  | 'moving_object'
  | 'transient'
  | 'variable_star'
  | 'artifact'
  | 'unclassified';

export type CandidateStatus =
  | 'under_review'
  | 'community_verified'
  | 'validation_passed'
  | 'submitted_external'
  | 'externally_confirmed'
  | 'rejected';

export type ClassificationVote =
  | 'likely_real'
  | 'likely_artifact'
  | 'uncertain'
  | 'already_known';

export type UserRole = 'Volunteer' | 'Researcher' | 'Science Team';

export type ValidationCheckName =
  | 'gaia_crossmatch'
  | 'snr_threshold'
  | 'multi_epoch_motion'
  | 'spectral_plausibility';

export type ValidationStatus = 'passed' | 'failed' | 'inconclusive' | 'pending';

export type SubmissionDestination = 'MPC' | 'TNS' | 'VSX';

export type SubmissionStatus =
  | 'eligibility_pending'
  | 'eligible'
  | 'package_prepared'
  | 'submitted'
  | 'accepted'
  | 'rejected';

export interface ClassificationRecord {
  id: string;
  candidate_id: string;
  user_id: string;
  user_name: string;
  user_role: UserRole;
  vote: ClassificationVote;
  suggested_type?: string;
  notes?: string;
  created_at: string;
  fingerprint_hash?: string;
}

export interface ValidationCheckRecord {
  id: string;
  candidate_id: string;
  check_name: ValidationCheckName;
  status: ValidationStatus;
  details: Record<string, any>;
  evaluated_at: string;
}

export interface ExternalSubmissionRecord {
  id: string;
  candidate_id: string;
  destination: SubmissionDestination;
  status: SubmissionStatus;
  external_reference_id?: string;
  payload_text?: string;
  submitted_at: string;
  response_log?: string;
}

export interface ConsensusMetrics {
  total_votes: number;
  likely_real: number;
  likely_artifact: number;
  uncertain: number;
  already_known: number;
  positive_ratio: number;
  artifact_ratio: number;
  level1_qualified: boolean;
  level2_qualified: boolean;
  checks_passed: boolean;
  validation_summary: Record<string, string>;
}

export interface CandidateRecord {
  id: string; // Permanent PlanetX ID (e.g., PX-000001)
  name: string;
  ra: number;
  dec: number;
  discovery_date: string;
  candidate_type: CandidateType;
  status: CandidateStatus;
  snr: number | null;
  speed_arcsec_hr: number | null;
  fit_rms_px: number | null;
  spectral_summary: Record<string, any>;
  detection_method:
    | 'heuristic_leave_one_out'
    | 'random_forest'
    | 'bloom_centroids'
    | 'volunteer_blink'
    | string;
  fixed_stack_url: string;
  motion_stack_url: string;
  metadata: Record<string, any>;
  epoch_count: number;
  author_id?: string;
  author_name?: string;
  created_at: string;
  updated_at: string;
  consensus_summary?: {
    total_votes: number;
    likely_real_votes: number;
    likely_artifact_votes: number;
    positive_percentage: number;
  };
  classifications?: ClassificationRecord[];
  validation_checks?: ValidationCheckRecord[];
  external_submissions?: ExternalSubmissionRecord[];
  consensus?: ConsensusMetrics;
}

export interface CatalogueKPIs {
  total_candidates: number;
  under_review: number;
  community_verified: number;
  passed_validation: number;
  submitted_external: number;
  externally_confirmed: number;
  rejected?: number;
}

export interface CatalogueFilterOptions {
  searchQuery: string;
  candidateType: CandidateType | 'all';
  status: CandidateStatus | 'all';
  spectralBand: 'all' | 'D1' | 'D2' | 'D3' | 'D4' | 'D5' | 'D6';
  sortBy: 'id_desc' | 'id_asc' | 'snr_desc' | 'speed_desc' | 'discovery_date_desc';
}
