import React, { useState } from 'react';
import { MessageSquare, Send, Clock } from 'lucide-react';

export interface VerificationComment {
  id: string;
  author: string;
  role: 'Volunteer' | 'Researcher' | 'Science Team';
  timestamp: string;
  candidateId: string;
  message: string;
  vote: 'confirm_motion' | 'artifact' | 'investigate' | 'known';
}

const INITIAL_COMMENTS: VerificationComment[] = [
  {
    id: 'c1',
    author: 'Elena Rostova',
    role: 'Volunteer',
    timestamp: '18m ago',
    candidateId: 'cand-barnard-primary',
    message: 'Confirmed motion across all 5 epochs. The dipole direction aligns with Gaia DR3 proper motion vector (pmDec ~ 10,362 mas/yr).',
    vote: 'confirm_motion',
  },
  {
    id: 'c2',
    author: 'Dr. Marcus Vance',
    role: 'Science Team',
    timestamp: '1 hour ago',
    candidateId: 'cand-barnard-primary',
    message: 'Verified. Secondary spectral analysis shows strong 3.05 um water-ice feature depression matching sub-stellar dwarf classification.',
    vote: 'confirm_motion',
  },
  {
    id: 'c3',
    author: 'Kaelen Miller',
    role: 'Researcher',
    timestamp: '3 hours ago',
    candidateId: 'cand-barnard-anomaly-1',
    message: 'Epoch 2 flare check: appears in Band 4 but completely absent in Band 1. Potential infrared-loud transient or cosmic ray hit in raw telemetry.',
    vote: 'investigate',
  },
];

interface CommunityVerificationStreamProps {
  activeCandidateId: string | null;
}

export const CommunityVerificationStream: React.FC<CommunityVerificationStreamProps> = ({
  activeCandidateId,
}) => {
  const [comments, setComments] = useState<VerificationComment[]>(INITIAL_COMMENTS);
  const [newComment, setNewComment] = useState('');
  const [selectedVote, setSelectedVote] = useState<'confirm_motion' | 'artifact' | 'investigate' | 'known'>('confirm_motion');

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
    };

    setComments([entry, ...comments]);
    setNewComment('');
  };

  const getVoteBadge = (vote: VerificationComment['vote']) => {
    switch (vote) {
      case 'confirm_motion':
        return <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800">Verified Motion</span>;
      case 'artifact':
        return <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-rose-950/60 text-rose-300 border border-rose-800">Artifact / Noise</span>;
      case 'investigate':
        return <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-800">Needs Review</span>;
      case 'known':
        return <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-stone-800 text-stone-300 border border-stone-700">Catalog Match</span>;
    }
  };

  return (
    <div className="flex flex-col h-full bg-paper-900 border-l border-paper-800 text-xs">
      {/* Header */}
      <div className="p-3.5 border-b border-paper-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-3.5 h-3.5 text-ochre-400" />
          <span className="font-mono uppercase text-[11px] font-semibold text-paper-100 tracking-wider">
            Peer Cross-Verification
          </span>
        </div>
        <span className="text-[10px] font-mono text-paper-400">
          {comments.length} Logged Discussions
        </span>
      </div>

      {/* Discussion List */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-3">
        {comments.map((item) => (
          <div
            key={item.id}
            className="p-3 rounded-md bg-paper-950 border border-paper-800 space-y-1.5 text-paper-300"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-paper-100 text-[11px] font-sans">
                  {item.author}
                </span>
                <span className="text-[9px] font-mono px-1 rounded bg-paper-800 text-paper-400">
                  {item.role}
                </span>
              </div>
              <span className="text-[10px] text-paper-500 font-mono flex items-center gap-1">
                <Clock className="w-2.5 h-2.5" />
                {item.timestamp}
              </span>
            </div>

            <p className="text-[11px] text-paper-300 leading-relaxed font-sans">
              {item.message}
            </p>

            <div className="pt-1 flex items-center justify-between border-t border-paper-800/80">
              {getVoteBadge(item.vote)}
              <span className="text-[10px] font-mono text-paper-500">
                Target: {item.candidateId}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* New Peer Verification Input */}
      <form onSubmit={handlePostComment} className="p-3 border-t border-paper-800 bg-paper-950 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-mono text-paper-400 uppercase">Your Verification Vote</span>
          <select
            value={selectedVote}
            onChange={(e) => setSelectedVote(e.target.value as any)}
            className="bg-paper-900 border border-paper-800 rounded px-1.5 py-0.5 text-[10px] font-mono text-paper-200"
          >
            <option value="confirm_motion">Confirm Motion</option>
            <option value="investigate">Needs Investigation</option>
            <option value="artifact">Likely Artifact</option>
            <option value="known">Known Object</option>
          </select>
        </div>

        <div className="flex gap-1.5">
          <input
            type="text"
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            placeholder="Share observation note with NASA volunteers..."
            className="flex-1 bg-paper-900 border border-paper-800 rounded px-2.5 py-1.5 text-[11px] font-sans text-paper-100 focus:outline-none focus:border-ochre-500"
          />
          <button
            type="submit"
            className="px-3 py-1.5 bg-paper-800 hover:bg-paper-700 text-paper-100 rounded text-xs font-mono transition-colors flex items-center gap-1"
          >
            <Send className="w-3 h-3 text-ochre-400" />
            <span>Send</span>
          </button>
        </div>
      </form>
    </div>
  );
};
