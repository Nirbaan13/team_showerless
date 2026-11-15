/** Persistent registry client. Failed requests never create local scientific records. */
import type { CandidateRecord, ClassificationRecord, ValidationCheckRecord, CatalogueKPIs, CatalogueFilterOptions, ConsensusMetrics } from '../types/catalogue';
import type { CandidateObject } from '../types/spherex';

export function resolveCatalogueCandidateId(candidate: CandidateObject | null): string | null {
  if (!candidate) return null;
  return candidate.catalogueId ?? (/^PX-\d+$/i.test(candidate.id) ? candidate.id.toUpperCase() : null);
}

export function evaluateConsensus(
  candidate: CandidateRecord,
  classifications: ClassificationRecord[],
  validationChecks: ValidationCheckRecord[]
): { status: CandidateRecord['status']; metrics: ConsensusMetrics } {
  // Author vote check
  const authorId = candidate.author_id;
  const filteredVotes: ClassificationRecord[] = [];
  let authorCounted = false;

  for (const c of classifications) {
    if (c.user_id === authorId) {
      if (!authorCounted) {
        filteredVotes.push(c);
        authorCounted = true;
      }
    } else {
      filteredVotes.push(c);
    }
  }

  const total = filteredVotes.length;
  const likelyReal = filteredVotes.filter((v) => v.vote === 'likely_real').length;
  const likelyArtifact = filteredVotes.filter((v) => v.vote === 'likely_artifact').length;
  const uncertain = filteredVotes.filter((v) => v.vote === 'uncertain').length;
  const alreadyKnown = filteredVotes.filter((v) => v.vote === 'already_known').length;

  const positiveRatio = total > 0 ? likelyReal / total : 0;
  const artifactRatio = total > 0 ? likelyArtifact / total : 0;

  const valSummary: Record<string, string> = {};
  for (const vc of validationChecks) {
    valSummary[vc.check_name] = vc.status;
  }
  const hasFailedChecks = Object.values(valSummary).includes('failed');
  const checksPassed =
    validationChecks.length >= 3 &&
    !hasFailedChecks &&
    Object.values(valSummary).filter((s) => s === 'passed').length >= 2;

  let newStatus = candidate.status;

  if (candidate.status === 'submitted_external' || candidate.status === 'externally_confirmed') {
    newStatus = candidate.status;
  } else if (total >= 5 && artifactRatio >= 0.5) {
    newStatus = 'rejected';
  } else if (total >= 10 && positiveRatio >= 0.8 && checksPassed && artifactRatio < 0.15) {
    newStatus = 'community_verified';
  } else if (total >= 3 && positiveRatio >= 0.66) {
    newStatus = candidate.status === 'community_verified' && total >= 10 ? 'community_verified' : 'under_review';
  } else {
    newStatus = 'under_review';
  }

  const metrics: ConsensusMetrics = {
    total_votes: total,
    likely_real: likelyReal,
    likely_artifact: likelyArtifact,
    uncertain: uncertain,
    already_known: alreadyKnown,
    positive_ratio: Number(positiveRatio.toFixed(3)),
    artifact_ratio: Number(artifactRatio.toFixed(3)),
    level1_qualified: total >= 3 && positiveRatio >= 0.66,
    level2_qualified: total >= 10 && positiveRatio >= 0.8 && checksPassed,
    checks_passed: checksPassed,
    validation_summary: valSummary,
  };

  return { status: newStatus, metrics };
}


async function registryRequest(path: string, init?: RequestInit): Promise<any> {
  const response = await fetch(`/api/catalogue${path}`, init);
  if (!response.ok) throw new Error(`Registry unavailable (HTTP ${response.status})`);
  const result = await response.json();
  return result;
}

export function computeKPIs(candidates: CandidateRecord[]): CatalogueKPIs {
  return {
    total_candidates: candidates.length,
    under_review: candidates.filter(c => c.status === 'under_review').length,
    community_verified: candidates.filter(c => c.status === 'community_verified').length,
    passed_validation: candidates.filter(c => c.status === 'validation_passed').length,
    submitted_external: candidates.filter(c => c.status === 'submitted_external').length,
    externally_confirmed: candidates.filter(c => c.status === 'externally_confirmed').length,
  };
}

export async function fetchCatalogueCandidates(options: Partial<CatalogueFilterOptions> = {}): Promise<{ candidates: CandidateRecord[]; total: number; kpis: CatalogueKPIs }> {
  const params = new URLSearchParams();
  if (options.searchQuery) params.set('q', options.searchQuery);
  if (options.candidateType && options.candidateType !== 'all') params.set('type', options.candidateType);
  if (options.status && options.status !== 'all') params.set('status', options.status);
  if (options.spectralBand && options.spectralBand !== 'all') params.set('band', options.spectralBand);
  if (options.sortBy) params.set('sort', options.sortBy);
  const data = await registryRequest(`/candidates?${params}`);
  if (!Array.isArray(data.candidates)) throw new Error('Registry unavailable: invalid list response');
  return { candidates: data.candidates, total: data.total ?? data.candidates.length, kpis: data.kpis ?? computeKPIs(data.candidates) };
}

export async function fetchCandidateById(candidateId: string): Promise<CandidateRecord | null> {
  const data = await registryRequest(`/candidates/${encodeURIComponent(candidateId)}`);
  if (data?.id !== candidateId) throw new Error('Registry unavailable: mismatched candidate identity');
  return { ...data, consensus: data.consensus ?? evaluateConsensus(data, data.classifications ?? [], data.validation_checks ?? []).metrics };
}

export async function createCandidateRecord(partial: Omit<CandidateRecord, 'id' | 'discovery_date' | 'created_at' | 'updated_at' | 'status'> & { id?: string }): Promise<CandidateRecord> {
  return registryRequest('/candidates', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(partial) });
}

export async function submitClassificationVote(candidateId: string, user: { id: string; name: string; role: 'Volunteer' | 'Researcher' | 'Science Team' }, vote: 'likely_real' | 'likely_artifact' | 'uncertain' | 'already_known', notes?: string, suggestedType?: string): Promise<{ success: boolean; message: string; newStatus?: string }> {
  try {
    const data = await registryRequest(`/candidates/${encodeURIComponent(candidateId)}/classify`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: user.id, user_name: user.name, user_role: user.role, vote, notes, suggested_type: suggestedType, fingerprint_hash: `fp-${user.id}-${window.navigator.userAgent.slice(0, 20)}` }) });
    return { success: true, message: 'Classification recorded by the registry.', newStatus: data.new_status };
  } catch (error) {
    return { success: false, message: error instanceof Error ? error.message : 'Classification was not recorded.' };
  }
}
