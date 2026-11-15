import type { VerificationComment } from '../types/spherex';
import { SEEDED_VERIFICATION_DISCUSSIONS } from './mockVerificationData';

const STORAGE_KEY = 'spherex_community_comments';

function getLocalVerifications(): VerificationComment[] {
  try {
    const saved = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null;
    if (saved) {
      const parsed: VerificationComment[] = JSON.parse(saved);
      if (Array.isArray(parsed) && parsed.length > 0) {
        return parsed;
      }
    }
  } catch {
    // Ignore JSON/localStorage failure
  }
  return SEEDED_VERIFICATION_DISCUSSIONS;
}

function saveLocalVerifications(comments: VerificationComment[]): void {
  try {
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(comments));
    }
  } catch {
    // Ignore storage quota or disabled localStorage
  }
}

function notifyUpdated(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('spherex_comments_updated'));
  }
}

/**
 * Fetches verification comments from the persistent SQLite backend API,
 * falling back seamlessly to local storage when the backend is offline.
 */
export async function fetchVerifications(candidateId?: string): Promise<VerificationComment[]> {
  const url = candidateId
    ? `/api/motion/verifications?candidate_id=${encodeURIComponent(candidateId)}`
    : '/api/motion/verifications';

  try {
    const res = await fetch(url);
    if (res.ok) {
      const remoteData: VerificationComment[] = await res.json();
      if (Array.isArray(remoteData)) {
        // Merge with local comments to preserve any un-synced local edits
        const local = getLocalVerifications();
        const mergedMap = new Map<string, VerificationComment>();

        // Remote has precedence
        for (const item of remoteData) {
          mergedMap.set(item.id, item);
        }
        for (const item of local) {
          if (!mergedMap.has(item.id)) {
            mergedMap.set(item.id, item);
          }
        }
        const merged = Array.from(mergedMap.values());
        saveLocalVerifications(merged);
        return candidateId
          ? merged.filter((c) => c.candidateId === candidateId || c.setting?.candidateId === candidateId)
          : merged;
      }
    }
  } catch {
    // Backend offline or unreachable: fall back to local storage
  }

  const local = getLocalVerifications();
  return candidateId
    ? local.filter((c) => c.candidateId === candidateId || c.setting?.candidateId === candidateId)
    : local;
}

/**
 * Posts a verification note or scientist triage review to the backend.
 */
export async function createVerification(comment: VerificationComment): Promise<VerificationComment> {
  // Update local storage immediately for optimistic UI
  const local = getLocalVerifications();
  const updatedLocal = [comment, ...local.filter((c) => c.id !== comment.id)];
  saveLocalVerifications(updatedLocal);
  notifyUpdated();

  try {
    const res = await fetch('/api/motion/verifications', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(comment),
    });
    if (res.ok) {
      const persisted: VerificationComment = await res.json();
      // Update with server confirmed record
      const refreshed = [persisted, ...updatedLocal.filter((c) => c.id !== comment.id && c.id !== persisted.id)];
      saveLocalVerifications(refreshed);
      notifyUpdated();
      return persisted;
    }
  } catch {
    // Keep local version when offline
  }

  return comment;
}

/**
 * Upvotes a verification comment both in the persistent backend and locally.
 */
export async function upvoteVerification(commentId: string): Promise<number> {
  // Optimistically bump upvote locally
  const local = getLocalVerifications();
  let newCount = 1;
  const updated = local.map((c) => {
    if (c.id === commentId) {
      newCount = (c.upvotes || 0) + 1;
      return { ...c, upvotes: newCount };
    }
    return c;
  });
  saveLocalVerifications(updated);
  notifyUpdated();

  try {
    const res = await fetch(`/api/motion/verifications/${encodeURIComponent(commentId)}/upvote`, {
      method: 'POST',
    });
    if (res.ok) {
      const data = await res.json();
      if (typeof data.upvotes === 'number') {
        newCount = data.upvotes;
        const confirmed = getLocalVerifications().map((c) =>
          c.id === commentId ? { ...c, upvotes: newCount } : c
        );
        saveLocalVerifications(confirmed);
        notifyUpdated();
      }
    }
  } catch {
    // Retain optimistic count
  }

  return newCount;
}

/**
 * Fetches all registered candidates from the backend.
 */
export async function fetchBackendCandidates(): Promise<any[]> {
  try {
    const res = await fetch('/api/motion/candidates');
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // Fall back to empty list if backend offline
  }
  return [];
}

/**
 * Registers or updates a candidate record in the backend.
 */
export async function saveBackendCandidate(candidate: {
  id: string;
  ra: number;
  dec: number;
  classification: string;
  confidence: string;
  notes?: string;
  metadata?: any;
}): Promise<any> {
  try {
    const res = await fetch('/api/motion/candidates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(candidate),
    });
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // Ignore network failure
  }
  return candidate;
}
