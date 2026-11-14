import React, { useState } from 'react';
import { Send, Clock, UserCheck, ShieldAlert, Sparkles, Filter } from 'lucide-react';

export interface VerificationComment {
  id: string;
  author: string;
  role: 'Volunteer' | 'Researcher' | 'Science Team';
  timestamp: string;
  candidateId: string;
  message: string;
  vote: 'confirm_motion' | 'artifact' | 'investigate' | 'known';
  upvotes: number;
}

const STORAGE_KEY = 'spherex_community_comments';

interface CommunityVerificationStreamProps {
  activeCandidateId: string | null;
  onAddComment?: (comment: VerificationComment) => void;
}

export const CommunityVerificationStream: React.FC<CommunityVerificationStreamProps> = ({
  activeCandidateId,
  onAddComment,
}) => {
  const [comments, setComments] = useState<VerificationComment[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) return JSON.parse(saved);
    } catch {}
    return [];
  });
  const [newComment, setNewComment] = useState('');
  const [selectedVote, setSelectedVote] = useState<'confirm_motion' | 'artifact' | 'investigate' | 'known'>('confirm_motion');
  const [filterType, setFilterType] = useState<string>('all');

  const handlePostComment = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newComment.trim()) return;

    const entry: VerificationComment = {
      id: `c-${Date.now()}`,
      author: 'Citizen Volunteer (You)',
      role: 'Volunteer',
      timestamp: 'Just now',
      candidateId: activeCandidateId || 'general',
      message: newComment.trim(),
      vote: selectedVote,
      upvotes: 1,
    };

    const updated = [entry, ...comments];
    setComments(updated);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    } catch {}
    if (onAddComment) onAddComment(entry);
    setNewComment('');
  };

  const getVoteBadge = (vote: VerificationComment['vote']) => {
    switch (vote) {
      case 'confirm_motion':
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950/70 text-emerald-300 border border-emerald-800/80 flex items-center gap-1">
            <UserCheck className="w-2.5 h-2.5" />
            Verified Motion
          </span>
        );
      case 'artifact':
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-rose-950/70 text-rose-300 border border-rose-800/80 flex items-center gap-1">
            <ShieldAlert className="w-2.5 h-2.5" />
            Artifact / Noise
          </span>
        );
      case 'investigate':
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-950/70 text-amber-300 border border-amber-800/80 flex items-center gap-1">
            <Sparkles className="w-2.5 h-2.5" />
            Needs Review
          </span>
        );
      case 'known':
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-paper-800 text-paper-300 border border-paper-700">
            Catalog Match
          </span>
        );
    }
  };

  const filteredComments = comments.filter((c) => {
    if (filterType === 'all') return true;
    if (filterType === 'current') return c.candidateId === activeCandidateId;
    return c.vote === filterType;
  });

  return (
    <div className="flex flex-col h-full bg-paper-900 text-xs">
      {/* Sub-Header & Filter */}
      <div className="px-4 py-2.5 border-b border-paper-800 flex items-center justify-between bg-paper-950/60">
        <div className="flex items-center gap-1.5 text-[11px] font-mono text-paper-400">
          <Filter className="w-3 h-3 text-emerald-400" />
          <span>Filter:</span>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="bg-paper-900 border border-paper-800 rounded px-1.5 py-0.5 text-[10px] font-mono text-paper-200 focus:outline-none"
          >
            <option value="all">All Notes ({comments.length})</option>
            <option value="current">Current Target Only</option>
            <option value="confirm_motion">Confirmed Motion</option>
            <option value="investigate">Needs Review</option>
            <option value="artifact">Artifacts</option>
          </select>
        </div>

        <span className="text-[10px] font-mono text-paper-500">
          {activeCandidateId ? `Target: ${activeCandidateId}` : 'All Targets'}
        </span>
      </div>

      {/* Discussion List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {filteredComments.length === 0 && (
          <div className="h-44 flex flex-col items-center justify-center text-center p-6 rounded-xl border border-dashed border-paper-800 space-y-2">
            <Send className="w-6 h-6 text-paper-600 mx-auto" />
            <span className="font-mono text-xs text-paper-300 font-semibold">No Notes Logged Yet</span>
            <p className="text-[11px] text-paper-500 max-w-xs leading-relaxed">
              Post an observation note or verification finding below to log your discussion for this celestial target.
            </p>
          </div>
        )}

        {filteredComments.map((item) => (
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
              {getVoteBadge(item.vote)}
              <span className="text-[10px] font-mono text-paper-500">
                {item.candidateId}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Input Message Area */}
      <form onSubmit={handlePostComment} className="p-3.5 border-t border-paper-800 bg-paper-950 space-y-2.5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-mono text-paper-400 uppercase tracking-wider font-semibold">
            Verification Tag
          </span>
          <select
            value={selectedVote}
            onChange={(e) => setSelectedVote(e.target.value as any)}
            className="bg-paper-900 border-2 border-black rounded-lg px-2 py-1 text-[10px] font-mono text-paper-200 focus:outline-none cursor-pointer"
          >
            <option value="confirm_motion">Confirm Motion</option>
            <option value="investigate">Needs Investigation</option>
            <option value="artifact">Likely Artifact / Noise</option>
            <option value="known">Known Catalog Star</option>
          </select>
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            placeholder="Share observation note with NASA volunteers..."
            className="flex-1 bg-paper-900 border-2 border-black rounded-xl px-3 py-2 text-xs font-sans text-paper-100 focus:outline-none focus:border-emerald-400 placeholder:text-paper-600"
          />
          <button
            type="submit"
            className="btn-tactile px-4 py-2 bg-emerald-400 hover:bg-emerald-300 text-gray-950 rounded-xl text-xs font-mono font-bold border-2 border-black transition-all shrink-0 flex items-center gap-1.5 cursor-pointer"
          >
            <Send className="w-3 h-3 stroke-[2.5]" />
            <span>Post</span>
          </button>
        </div>
      </form>
    </div>
  );
};
