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
