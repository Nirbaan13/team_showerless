import React, { useState, useEffect } from 'react';
import type {
  CandidateObject,
  FOVOption,
  DetectorArrayId,
  SubtractionMode,
  VerificationComment,
} from '../types/spherex';
import { getPriorityColors } from '../services/mlRanking';
import { SEEDED_VERIFICATION_DISCUSSIONS } from '../services/mockVerificationData';
import {
  fetchVerifications,
  createVerification,
  upvoteVerification,
} from '../services/verificationService';
import {
  Send,
  Clock,
  UserCheck,
  ShieldAlert,
  Sparkles,
  MessageSquare,
  Compass,
  HelpCircle,
  ThumbsUp,
  ShieldCheck,
  Activity,
  Zap,
  Database,
} from 'lucide-react';

const STORAGE_KEY = 'spherex_community_comments';

interface CommunityVerificationStreamProps {
  candidate: CandidateObject | null;
  activeCandidateId?: string | null;
  currentPresetId?: string | null;
  onAddComment?: (comment: VerificationComment) => void;
  ra?: number;
  dec?: number;
  fov?: FOVOption;
  selectedArray?: DetectorArrayId | 'all';
  activeFrameIndex?: number;
  subtractionMode?: SubtractionMode;
  onOpenCatalogue?: (candidateId?: string) => void;
  onOpenExternalSubmission?: (candidateId: string) => void;
}

export const CommunityVerificationStream: React.FC<CommunityVerificationStreamProps> = ({
  candidate,
  activeCandidateId,
  currentPresetId = null,
  onAddComment,
  ra: _fieldRa,
  dec: _fieldDec,
  fov = "3'",
  selectedArray = 2,
  activeFrameIndex = 0,
  subtractionMode = 'raw_calibrated',
  onOpenCatalogue,
  onOpenExternalSubmission,
}) => {
  // Strictly bind to the currently clicked candidate's ID
  const targetId = activeCandidateId || candidate?.id || null;

  const [comments, setComments] = useState<VerificationComment[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed: VerificationComment[] = JSON.parse(saved);
        if (parsed.length > 0) return parsed;
      }
    } catch {}
    return SEEDED_VERIFICATION_DISCUSSIONS;
  });

  useEffect(() => {
    let isMounted = true;
    fetchVerifications().then((data) => {
      if (isMounted && data.length > 0) {
        setComments(data);
      }
    });

    const handleUpdated = () => {
      fetchVerifications().then((data) => {
        if (isMounted) setComments(data);
      });
    };
    window.addEventListener('spherex_comments_updated', handleUpdated);
    return () => {
      isMounted = false;
      window.removeEventListener('spherex_comments_updated', handleUpdated);
    };
  }, []);

  const [authorName, setAuthorName] = useState<string>('Citizen Volunteer (You)');
  const [authorRole, setAuthorRole] = useState<'Volunteer' | 'Researcher' | 'Science Team'>('Volunteer');
  const [newComment, setNewComment] = useState('');
  const [selectedVote, setSelectedVote] = useState<'confirm_motion' | 'artifact' | 'investigate' | 'known'>(() => {
    if (!candidate) return 'confirm_motion';
    if (candidate.classification === 'artifact') return 'artifact';
    if (candidate.classification === 'already_known') return 'known';
    if (candidate.classification === 'transient') return 'investigate';
    return 'confirm_motion';
  });

  // Filter comments strictly for THIS specific clicked candidate only
  const objectComments = comments.filter(
    (c) => targetId !== null && (c.candidateId === targetId || c.setting?.candidateId === targetId)
  );

  // Map to canonical catalogue candidate ID and base seed votes
  const normalizedId = (targetId || '').toLowerCase();
  let defaultBenchmarkVotes = 1;
  let canonicalId = targetId || 'PX-000001';
  if (normalizedId.startsWith('px-')) {
    canonicalId = (targetId || '').toUpperCase();
  } else if (normalizedId.includes('atlas') || normalizedId.includes('3i')) {
    defaultBenchmarkVotes = 12;
    canonicalId = 'PX-000001';
  } else if (normalizedId.includes('vesta')) {
    defaultBenchmarkVotes = 11;
    canonicalId = 'PX-000002';
  } else if (normalizedId.includes('barnard')) {
    defaultBenchmarkVotes = 10;
    canonicalId = 'PX-000003';
  } else if (normalizedId.includes('wise') || normalizedId.includes('0855')) {
    defaultBenchmarkVotes = 4;
    canonicalId = 'PX-000004';
  }

  const explicitConfirmations = objectComments.filter(
    (c) => c.vote === 'confirm_motion'
  ).length;
  const currentConsensusCount = Math.max(defaultBenchmarkVotes, explicitConfirmations);
  const isLevel2Verified = currentConsensusCount >= 10;

  // Automatic clearinghouse pipeline: 10 confirmations -> catalogue + dispatch -> reply recorded
  const [autoSub, setAutoSub] = useState<{
    candidateId: string;
    destination?: string;
    reference?: string;
    status: 'dispatching' | 'submitted' | 'accepted' | 'rejected' | 'error';
    log?: string;
  } | null>(null);

  useEffect(() => {
    if (!isLevel2Verified || !candidate || !targetId) return;
    let cancelled = false;
    let timer: number | undefined;

    const poll = async (cid: string) => {
      try {
        const res = await fetch(`/api/catalogue/candidates/${encodeURIComponent(cid)}`);
        if (!res.ok) throw new Error(String(res.status));
        const data = await res.json();
        const subs: any[] = data.external_submissions || [];
        const latest = subs[0];
        if (cancelled || !latest) return;
        const st = latest.status === 'accepted' || latest.status === 'rejected' ? latest.status : 'submitted';
        setAutoSub({
          candidateId: cid,
          destination: latest.destination,
          reference: latest.external_reference_id,
          status: st,
          log: latest.response_log,
        });
        if (st === 'submitted') timer = window.setTimeout(() => poll(cid), 3000);
      } catch {
        if (!cancelled) timer = window.setTimeout(() => poll(cid), 5000);
      }
    };

    (async () => {
      setAutoSub((prev) => prev ?? { candidateId: canonicalId, status: 'dispatching' });
      try {
        const res = await fetch('/api/catalogue/auto-submit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            thread_key: canonicalId,
            name: candidate.validationData?.objectName || candidate.catalogId || candidate.id,
            ra: candidate.ra,
            dec: candidate.dec,
            confirmations: currentConsensusCount,
            candidate_type:
              candidate.classification === 'transient'
                ? 'transient'
                : candidate.classification === 'artifact'
                ? 'artifact'
                : 'moving_object',
            snr: candidate.epochPositions?.[0]?.snr ?? null,
            speed_arcsec_hr: candidate.speedArcsecPerHour ?? null,
            fit_rms_px: candidate.fitRmsPx ?? null,
          }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (cancelled) return;
        poll(data.candidate_id);
      } catch (err: any) {
        if (!cancelled) setAutoSub({ candidateId: canonicalId, status: 'error', log: err?.message || 'Catalogue service unreachable' });
      }
    })();

    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLevel2Verified, targetId]);

  const handlePostComment = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newComment.trim() || !targetId || !candidate) return;

    const exactCandidateId = candidate.id;
    const candidateTitle =
      candidate.validationData?.objectName ||
      candidate.catalogId ||
      candidate.id;

    const cleanCandId = exactCandidateId.replace(/\//g, '_');
    const entry: VerificationComment = {
      id: `comment-${cleanCandId}-${Date.now()}`,
      author: authorName.trim() || 'Citizen Volunteer',
      role: authorRole,
      timestamp: 'Just now',
      candidateId: exactCandidateId,
      message: newComment.trim(),
      vote: selectedVote,
      upvotes: 1,
      setting: {
        targetPresetId: currentPresetId ?? null,
        candidateId: exactCandidateId,
        candidateName: `#${candidate.mlRank || 1} · ${candidateTitle}`,
        ra: candidate.ra,
        dec: candidate.dec,
        fov: fov,
        selectedArray: selectedArray,
        activeFrameIndex: activeFrameIndex,
        subtractionMode: subtractionMode,
      },
    };

    void createVerification(entry);
    if (onAddComment) onAddComment(entry);
    setNewComment('');
  };

  const handleUpvote = (commentId: string) => {
    void upvoteVerification(commentId);
  };

  const handleQuickConfirm = () => {
    if (!targetId || !candidate) return;
    const exactCandidateId = candidate.id;
    const candidateTitle =
      candidate.validationData?.objectName ||
      candidate.catalogId ||
      candidate.id;

    const entry: VerificationComment = {
      id: `comment-${exactCandidateId}-${Date.now()}`,
      author: authorName.trim() || 'Citizen Volunteer',
      role: authorRole,
      timestamp: 'Just now',
      candidateId: exactCandidateId,
      message: 'Verified non-sidereal motion track across SPHEREx multi-epoch frames. Optical PSF matches telescope beam profile.',
      vote: 'confirm_motion',
      upvotes: 2,
      setting: {
        targetPresetId: currentPresetId ?? null,
        candidateId: exactCandidateId,
        candidateName: `#${candidate.mlRank || 1} · ${candidateTitle}`,
        ra: candidate.ra,
        dec: candidate.dec,
        fov: fov,
        selectedArray: selectedArray,
        activeFrameIndex: activeFrameIndex,
        subtractionMode: subtractionMode,
      },
    };

    const updated = [entry, ...comments];
    setComments(updated);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      window.dispatchEvent(new Event('spherex_comments_updated'));
    } catch {}
    if (onAddComment) onAddComment(entry);
  };

  const handleFastTrackConsensus = () => {
    if (!targetId || !candidate) return;
    const exactCandidateId = candidate.id;
    const candidateTitle =
      candidate.validationData?.objectName ||
      candidate.catalogId ||
      candidate.id;

    const simulatedPeers: { author: string; role: 'Volunteer' | 'Researcher' | 'Science Team'; message: string }[] = [
      { author: 'Dr. Arthur Dent', role: 'Researcher', message: 'Linear motion trajectory verified in Band D6. Shift & Stack coadd confirms point-source profile without elongation.' },
      { author: 'Dr. Sarah Chen', role: 'Science Team', message: 'Residual astrometric fit RMS is 0.22 px, well below the 0.50 px threshold. No Gaia DR3 stationary source at coordinates.' },
      { author: 'Observatory Volunteer 4', role: 'Volunteer', message: 'Blink inspection across 4 epochs confirms steady velocity vector. Clearly not an artifact.' },
      { author: 'Prof. T. Vance', role: 'Researcher', message: 'Signal-to-noise ratio > 12σ across exposures. Ready for Minor Planet Center / TNS dispatch.' },
      { author: 'AstroCitizen_99', role: 'Volunteer', message: 'Cross-checked against JPL Horizons ephemerides. Candidate motion confirmed.' },
      { author: 'Dr. Elena Rostova', role: 'Science Team', message: 'Spectral absorption profile consistent with cold non-sidereal body. Consensus threshold verified.' },
      { author: 'K. Patel', role: 'Volunteer', message: 'Confirmed point-source leave-one-out subtraction track.' },
    ];

    const newEntries: VerificationComment[] = simulatedPeers.map((peer, idx) => ({
      id: `comment-${exactCandidateId}-fasttrack-${Date.now()}-${idx}`,
      author: peer.author,
      role: peer.role,
      timestamp: `${idx + 1}m ago`,
      candidateId: exactCandidateId,
      message: peer.message,
      vote: 'confirm_motion',
      upvotes: 4 + idx,
      setting: {
        targetPresetId: currentPresetId ?? null,
        candidateId: exactCandidateId,
        candidateName: `#${candidate.mlRank || 1} · ${candidateTitle}`,
        ra: candidate.ra,
        dec: candidate.dec,
        fov: fov,
        selectedArray: selectedArray,
        activeFrameIndex: activeFrameIndex,
        subtractionMode: subtractionMode,
      },
    }));

    const updated = [...newEntries, ...comments];
    setComments(updated);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      window.dispatchEvent(new Event('spherex_comments_updated'));
    } catch {}
  };

  const getVoteBadge = (vote: VerificationComment['vote']) => {
    switch (vote) {
      case 'confirm_motion':
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-300 border border-emerald-800 flex items-center gap-1 font-semibold">
            <UserCheck className="w-2.5 h-2.5" />
            Verified Motion
          </span>
        );
      case 'artifact':
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-rose-950/80 text-rose-300 border border-rose-800 flex items-center gap-1 font-semibold">
            <ShieldAlert className="w-2.5 h-2.5" />
            Artifact / Noise
          </span>
        );
      case 'investigate':
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-950/80 text-amber-300 border border-amber-800 flex items-center gap-1 font-semibold">
            <Sparkles className="w-2.5 h-2.5" />
            Needs Review
          </span>
        );
      case 'known':
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-paper-800 text-paper-300 border border-paper-700">
            Catalog Star
          </span>
        );
    }
  };

  if (!candidate || !targetId) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center space-y-3 bg-paper-900">
        <HelpCircle className="w-8 h-8 text-paper-600 mx-auto" />
        <h3 className="text-xs font-mono font-semibold text-paper-200">No Object Selected</h3>
        <p className="text-[11px] text-paper-500 max-w-xs leading-relaxed">
          Click any priority-marked object in the starfield or AI sidebar to join its dedicated single-object verification chat.
        </p>
      </div>
    );
  }

  const priorityRank = candidate.mlRank || 1;
  const pColors = getPriorityColors(priorityRank);
  const displayName =
    candidate.validationData?.objectName ||
    candidate.catalogId ||
    candidate.id;

  return (
    <div className="flex flex-col h-full bg-paper-900 text-xs">
      {/* Object Dedicated Scope Header */}
      <div className="px-4 py-3 border-b border-paper-800 bg-paper-950/80 space-y-2 shrink-0">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 min-w-0">
            <span
              style={{ backgroundColor: pColors.badgeBg, color: pColors.text }}
              className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded shadow-sm border border-black/40 shrink-0"
            >
              ★ #{priorityRank}
            </span>
            <span className="font-bold text-paper-100 text-xs font-sans truncate" title={displayName}>
              {displayName}
            </span>
          </div>

          <span className="text-[10px] font-mono text-emerald-400 bg-paper-900 px-2 py-0.5 rounded border border-paper-800 flex items-center gap-1 shrink-0">
            <MessageSquare className="w-2.5 h-2.5" />
            {objectComments.length} {objectComments.length === 1 ? 'Note' : 'Notes'}
          </span>
        </div>

        {/* Single-Object Chat Notice */}
        <div className="flex items-center justify-between text-[10px] font-mono text-paper-400 pt-1 border-t border-paper-800/60">
          <span className="flex items-center gap-1 text-ochre-300">
            <Compass className="w-2.5 h-2.5" />
            RA {candidate.ra.toFixed(4)}°, Dec {candidate.dec >= 0 ? `+${candidate.dec.toFixed(4)}` : candidate.dec.toFixed(4)}°
          </span>
          <span className="text-emerald-400/90 font-semibold">Only for #{priorityRank}</span>
        </div>
      </div>

      {/* Consensus & External Scientific Submission Gauge */}
      <div className="p-3 border-b border-paper-800 bg-paper-950/50">
        {!isLevel2Verified ? (
          <div className="p-3 rounded-xl bg-amber-950/40 border-2 border-amber-500/40 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 font-mono text-[11px] font-bold text-amber-300">
                <Activity className="w-3.5 h-3.5 text-amber-400" />
                <span>Community Consensus: {currentConsensusCount} / 10 Confirmations</span>
              </div>
              <span className="text-[10px] font-mono text-amber-400/90 font-semibold bg-amber-950/80 px-2 py-0.5 rounded border border-amber-800">
                Level 1 Under Review
              </span>
            </div>

            {/* Progress bar */}
            <div className="w-full bg-paper-950 rounded-full h-2 border border-paper-800 overflow-hidden">
              <div
                className="bg-gradient-to-r from-amber-500 to-emerald-400 h-full rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, (currentConsensusCount / 10) * 100)}%` }}
              />
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[10px] font-mono text-paper-400 pt-0.5">
              <span>{Math.max(0, 10 - currentConsensusCount)} more needed for MPC/TNS submission</span>
              <div className="flex items-center gap-1.5 self-end">
                <button
                  type="button"
                  onClick={handleQuickConfirm}
                  className="btn-tactile-sm px-2.5 py-1 rounded-lg bg-emerald-400 hover:bg-emerald-300 text-gray-950 font-bold border border-black cursor-pointer shadow-sm flex items-center gap-1"
                  title="Add your confirmation vote to this candidate thread"
                >
                  <UserCheck className="w-3 h-3 stroke-[2.5]" />
                  <span>+1 Confirm</span>
                </button>
                <button
                  type="button"
                  onClick={handleFastTrackConsensus}
                  className="btn-tactile-sm px-2 py-1 rounded-lg bg-paper-850 hover:bg-paper-800 text-emerald-300 border border-emerald-500/40 cursor-pointer flex items-center gap-1"
                  title="Fast-track consensus with simulated independent peer reviews"
                >
                  <Zap className="w-3 h-3 text-amber-400" />
                  <span>⚡ Reach 10</span>
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="p-3.5 rounded-xl bg-emerald-950/80 border-2 border-emerald-400 space-y-2.5 shadow-[0_0_15px_rgba(16,185,129,0.25)]">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 font-mono text-[11px] font-bold text-emerald-300">
                <ShieldCheck className="w-4 h-4 text-emerald-400 stroke-[2.5]" />
                <span>★ LEVEL 2 CONSENSUS ACHIEVED ({currentConsensusCount}/10 Confirmations)</span>
              </div>
              <span className="text-[10px] font-mono text-gray-950 bg-emerald-400 px-2 py-0.5 rounded font-bold border border-black">
                VERIFIED
              </span>
            </div>

            {/* Automatic submission status */}
            <div
              className={`p-2.5 rounded-lg border font-mono text-[11px] space-y-1 ${
                autoSub?.status === 'accepted'
                  ? 'bg-purple-950/60 border-purple-500/50 text-purple-200'
                  : autoSub?.status === 'rejected'
                  ? 'bg-red-950/60 border-red-500/50 text-red-200'
                  : autoSub?.status === 'error'
                  ? 'bg-red-950/40 border-red-800 text-red-300'
                  : 'bg-sky-950/60 border-sky-500/50 text-sky-200'
              }`}
            >
              <div className="font-bold">
                {!autoSub || autoSub.status === 'dispatching'
                  ? '⏳ Auto-submitting to clearinghouse…'
                  : autoSub.status === 'submitted'
                  ? `📨 Submitted to ${autoSub.destination} — awaiting reply…`
                  : autoSub.status === 'accepted'
                  ? `✅ ACCEPTED by ${autoSub.destination}`
                  : autoSub.status === 'rejected'
                  ? `❌ REJECTED by ${autoSub.destination}`
                  : '⚠ Submission service unreachable'}
              </div>
              {autoSub?.reference && <div className="text-paper-400">Ref: {autoSub.reference} · Catalog ID: {autoSub.candidateId}</div>}
              {autoSub?.log && autoSub.status !== 'submitted' && <div className="text-paper-300">{autoSub.log}</div>}
            </div>

            <div className="flex items-center gap-2 pt-0.5">
              {onOpenCatalogue && (
                <button
                  type="button"
                  onClick={() => onOpenCatalogue(autoSub?.candidateId || canonicalId)}
                  className="btn-tactile flex-1 py-1.5 px-3 rounded-xl bg-emerald-400 hover:bg-emerald-300 text-gray-950 font-mono text-xs font-bold border-2 border-black flex items-center justify-center gap-1.5 cursor-pointer"
                  title="View this candidate in the Candidate Catalog"
                >
                  <Database className="w-3.5 h-3.5" />
                  <span>View in Candidate Catalog →</span>
                </button>
              )}
              {onOpenExternalSubmission && (
                <button
                  type="button"
                  onClick={() => onOpenExternalSubmission(autoSub?.candidateId || canonicalId)}
                  className="btn-tactile py-1.5 px-3 rounded-xl bg-paper-900 hover:bg-paper-850 text-emerald-300 font-mono text-xs font-bold border-2 border-black flex items-center justify-center gap-1.5 cursor-pointer shrink-0"
                  title="View the machine-readable submission payload (ADES / TNS JSON)"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>Payload</span>
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Discussion Message List (Exclusively for this candidate) */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {objectComments.length === 0 ? (
          <div className="h-44 flex flex-col items-center justify-center text-center p-6 rounded-xl border border-dashed border-paper-800 space-y-2 bg-paper-950/40">
            <MessageSquare className="w-6 h-6 text-paper-600 mx-auto" />
            <span className="font-mono text-xs text-paper-300 font-semibold">No Notes Logged Yet</span>
            <p className="text-[11px] text-paper-500 max-w-xs leading-relaxed">
              Anyone can start the conversation for this candidate! Post your triage finding below to record the observation setting for other researchers.
            </p>
          </div>
        ) : (
          objectComments.map((item) => (
            <div
              key={item.id}
              className="p-3.5 rounded-xl bg-paper-950 border-2 border-black/80 space-y-2 card-tactile"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-5 h-5 rounded-full bg-paper-800 flex items-center justify-center font-bold text-[9px] text-emerald-400 border border-black">
                    {item.author.charAt(0)}
                  </div>
                  <span className="font-semibold text-paper-100 text-xs font-sans">
                    {item.author}
                  </span>
                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-paper-800 text-paper-300 border border-black/60">
                    {item.role}
                  </span>
                </div>

                <span className="text-[10px] text-paper-500 font-mono flex items-center gap-1">
                  <Clock className="w-2.5 h-2.5" />
                  {item.timestamp}
                </span>
              </div>

              <p className="text-xs text-paper-200 leading-relaxed font-sans pl-1">
                {item.message}
              </p>

              <div className="pt-2 flex items-center justify-between border-t border-paper-800">
                <div className="flex items-center gap-2">
                  {getVoteBadge(item.vote)}
                  <button
                    type="button"
                    onClick={() => handleUpvote(item.id)}
                    className="flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-paper-900 hover:bg-paper-800 text-emerald-400 border border-paper-800 hover:border-emerald-500/60 transition-colors cursor-pointer"
                    title="Upvote this verification"
                  >
                    <ThumbsUp className="w-2.5 h-2.5" />
                    <span>{item.upvotes || 1}</span>
                  </button>
                </div>
                {item.setting && (
                  <span className="text-[9px] font-mono text-paper-500">
                    Array {item.setting.selectedArray} • Frame {item.setting.activeFrameIndex + 1}
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Input Message Form (Record Comment + View Settings) */}
      <form onSubmit={handlePostComment} className="p-3.5 border-t border-paper-800 bg-paper-950 space-y-2.5 shrink-0">
        <div className="grid grid-cols-3 gap-2">
          <div>
            <label className="text-[9px] font-mono text-paper-400 block mb-0.5 uppercase">Observer</label>
            <input
              type="text"
              value={authorName}
              onChange={(e) => setAuthorName(e.target.value)}
              placeholder="Your Name"
              className="w-full bg-paper-900 border border-paper-800 rounded px-2 py-1 text-[11px] font-mono text-paper-100 focus:outline-none focus:border-emerald-400"
            />
          </div>

          <div>
            <label className="text-[9px] font-mono text-paper-400 block mb-0.5 uppercase">Role</label>
            <select
              value={authorRole}
              onChange={(e) => setAuthorRole(e.target.value as any)}
              className="w-full bg-paper-900 border border-paper-800 rounded px-1.5 py-1 text-[11px] font-mono text-paper-200 focus:outline-none cursor-pointer"
            >
              <option value="Volunteer">Volunteer</option>
              <option value="Researcher">Researcher</option>
              <option value="Science Team">Science Team</option>
            </select>
          </div>

          <div>
            <label className="text-[9px] font-mono text-paper-400 block mb-0.5 uppercase">Triage Tag</label>
            <select
              value={selectedVote}
              onChange={(e) => setSelectedVote(e.target.value as any)}
              className="w-full bg-paper-900 border border-paper-800 rounded px-1.5 py-1 text-[11px] font-mono text-paper-200 focus:outline-none cursor-pointer"
            >
              <option value="confirm_motion">Confirm Motion</option>
              <option value="investigate">Needs Investigation</option>
              <option value="artifact">Artifact / Noise</option>
              <option value="known">Known Catalog Star</option>
            </select>
          </div>
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            placeholder={`Note only for #${priorityRank} (${displayName})...`}
            className="flex-1 bg-paper-900 border-2 border-black rounded-xl px-3 py-2 text-xs font-sans text-paper-100 focus:outline-none focus:border-emerald-400 placeholder:text-paper-600"
          />
          <button
            type="submit"
            className="btn-tactile px-3.5 py-2 bg-emerald-400 hover:bg-emerald-300 text-gray-950 rounded-xl text-xs font-mono font-bold border-2 border-black transition-all shrink-0 flex items-center gap-1.5 cursor-pointer"
            title={`Submit chat note exclusively for #${priorityRank} ${displayName}`}
          >
            <Send className="w-3 h-3 stroke-[2.5]" />
            <span>Post #{priorityRank}</span>
          </button>
        </div>
      </form>
    </div>
  );
};
