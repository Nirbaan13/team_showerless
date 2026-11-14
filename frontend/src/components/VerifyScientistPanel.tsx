import React, { useState } from 'react';
import type { VerificationComment, VerificationSetting } from '../types/spherex';
import { getPriorityColors } from '../services/mlRanking';
import { getInitialVerificationComments } from '../services/mockVerificationData';
import {
  UserCheck,
  Sparkles,
  ShieldAlert,
  ArrowRight,
  MessageSquare,
  Compass,
  Clock,
  Layers,
  Search,
} from 'lucide-react';

interface VerifyScientistPanelProps {
  onSelectVerificationTarget: (setting: VerificationSetting) => void;
  isCompact?: boolean;
}

export const VerifyScientistPanel: React.FC<VerifyScientistPanelProps> = ({
  onSelectVerificationTarget,
  isCompact = false,
}) => {
  const [allComments] = useState<VerificationComment[]>(getInitialVerificationComments);
  const [filterVote, setFilterVote] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const filtered = allComments.filter((item) => {
    if (filterVote !== 'all' && item.vote !== filterVote) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchMsg = item.message.toLowerCase().includes(q);
      const matchAuthor = item.author.toLowerCase().includes(q);
      const matchName = item.setting?.candidateName?.toLowerCase().includes(q);
      if (!matchMsg && !matchAuthor && !matchName) return false;
    }
    return true;
  });

  const getVoteBadge = (vote: VerificationComment['vote']) => {
    switch (vote) {
      case 'confirm_motion':
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-300 border border-emerald-700 flex items-center gap-1 font-semibold">
            <UserCheck className="w-2.5 h-2.5" />
            Verified Motion
          </span>
        );
      case 'investigate':
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-950/80 text-amber-300 border border-amber-700 flex items-center gap-1 font-semibold">
            <Sparkles className="w-2.5 h-2.5" />
            Needs Review
          </span>
        );
      case 'artifact':
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-rose-950/80 text-rose-300 border border-rose-700 flex items-center gap-1 font-semibold">
            <ShieldAlert className="w-2.5 h-2.5" />
            Artifact / Noise
          </span>
        );
      default:
        return (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-paper-800 text-paper-300 border border-paper-700">
            Catalog Star
          </span>
        );
    }
  };

  return (
    <div className={`w-full ${isCompact ? 'p-3' : 'max-w-4xl p-4 sm:p-6'} bg-paper-900/90 rounded-2xl border-2 border-black card-tactile space-y-4`}>
      {/* Panel Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-paper-800 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse" />
            <h2 className="text-sm sm:text-base font-bold font-sans text-paper-100 uppercase tracking-wide flex items-center gap-2">
              <span>Scientist & Community Verification Feed</span>
            </h2>
          </div>
          <p className="text-[11px] font-mono text-paper-400 mt-0.5">
            Click any flagged object to open the exact coordinates, detector array, and observer markings for instant verification.
          </p>
        </div>

        {/* Filter controls */}
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3 h-3 text-paper-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search objects or notes..."
              className="bg-paper-950 border border-paper-800 rounded-lg pl-7 pr-2 py-1 text-[11px] font-mono text-paper-200 focus:outline-none focus:border-emerald-400 w-36 sm:w-44"
            />
          </div>

          <select
            value={filterVote}
            onChange={(e) => setFilterVote(e.target.value)}
            className="bg-paper-950 border border-paper-800 rounded-lg px-2 py-1 text-[11px] font-mono text-paper-200 focus:outline-none cursor-pointer"
          >
            <option value="all">All Discussions ({allComments.length})</option>
            <option value="confirm_motion">Confirmed Motion</option>
            <option value="investigate">Needs Review</option>
            <option value="artifact">Artifacts</option>
          </select>
        </div>
      </div>

      {/* Verification Cards Feed */}
      <div className={`grid ${isCompact ? 'grid-cols-1' : 'grid-cols-1 md:grid-cols-2'} gap-3 max-h-[460px] overflow-y-auto pr-1`}>
        {filtered.map((item, idx) => {
          const setting = item.setting;
          if (!setting) return null;
          // Priority rank (1 gets deepest red)
          const priorityRank = idx === 0 ? 1 : idx === 1 ? 1 : idx === 2 ? 2 : 3;
          const pColors = getPriorityColors(priorityRank);

          return (
            <div
              key={item.id}
              onClick={() => onSelectVerificationTarget(setting)}
              className="p-3.5 rounded-xl bg-paper-950 border-2 border-black hover:border-emerald-400/80 transition-all card-tactile cursor-pointer group flex flex-col justify-between space-y-3"
            >
              {/* Card Header: Candidate Name, Priority Badge & Vote */}
              <div className="space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {/* Priority Hexagon Marker Pill */}
                    <span
                      style={{ backgroundColor: pColors.badgeBg, color: pColors.text }}
                      className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded shadow-sm border border-black/40"
                    >
                      P{priorityRank}
                    </span>
                    <h3 className="text-xs font-bold font-sans text-paper-100 group-hover:text-emerald-300 transition-colors">
                      {setting.candidateName}
                    </h3>
                  </div>
                  {getVoteBadge(item.vote)}
                </div>

                {/* Top Comment & Author */}
                <p className="text-[11px] font-sans text-paper-300 leading-relaxed line-clamp-2">
                  "{item.message}"
                </p>
              </div>

              {/* Setting Parameters & Action Link */}
              <div className="pt-2 border-t border-paper-800/80 space-y-2">
                <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-mono text-paper-400">
                  <span className="px-1.5 py-0.5 rounded bg-paper-900 border border-paper-800 flex items-center gap-1 text-ochre-300">
                    <Compass className="w-2.5 h-2.5" />
                    {setting.ra.toFixed(3)}°, {setting.dec >= 0 ? `+${setting.dec.toFixed(3)}` : setting.dec.toFixed(3)}°
                  </span>

                  <span className="px-1.5 py-0.5 rounded bg-paper-900 border border-paper-800 flex items-center gap-1 text-emerald-300">
                    <Layers className="w-2.5 h-2.5" />
                    Array {setting.selectedArray}
                  </span>

                  <span className="px-1.5 py-0.5 rounded bg-paper-900 border border-paper-800">
                    Epoch {setting.activeFrameIndex + 1}
                  </span>

                  <span className="ml-auto text-paper-500 flex items-center gap-1">
                    <Clock className="w-2.5 h-2.5" />
                    {item.author}
                  </span>
                </div>

                {/* Inspect Button */}
                <button
                  type="button"
                  className="w-full py-1.5 px-3 rounded-lg bg-emerald-400 group-hover:bg-emerald-300 text-gray-950 font-mono text-[11px] font-bold border-2 border-black flex items-center justify-center gap-2 transition-transform group-hover:translate-x-0.5"
                >
                  <MessageSquare className="w-3 h-3 stroke-[2.5]" />
                  <span>Verify Object & Open Chat</span>
                  <ArrowRight className="w-3.5 h-3.5 stroke-[2.5]" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
