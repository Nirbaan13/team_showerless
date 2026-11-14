import React, { useMemo } from 'react';
import type { CandidateObject } from '../types/spherex';
import { rankCandidates } from '../services/mlRanking';
import { Cpu, Award } from 'lucide-react';

interface MLDetectionsPanelProps {
  candidates: CandidateObject[];
  selectedCandidateId: string | null;
  onSelectCandidate: (id: string) => void;
  isScientistMode?: boolean;
}

const CLASS_LABEL: Record<string, string> = {
  moving_object: 'Moving',
  transient: 'Flash',
  already_known: 'Known',
  artifact: 'Artifact',
  unreviewed: 'New',
};

export const MLDetectionsPanel: React.FC<MLDetectionsPanelProps> = ({
  candidates,
  selectedCandidateId,
  onSelectCandidate,
  isScientistMode = false,
}) => {
  const ranked = useMemo(() => rankCandidates(candidates), [candidates]);
  const validated = ranked.find((r) => r.candidate.validationData)?.candidate.validationData;

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between anim-fall">
        <span className="font-semibold text-paper-100 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
          <Cpu className="w-4 h-4 text-emerald-400" />
          AI Detections
        </span>
        <span className="text-[10px] font-mono text-paper-400">
          {validated ? `${validated.totalCandidates} tracks scanned` : `${ranked.length} found`}
        </span>
      </div>

      {validated && (
        <div className="p-3 rounded-xl bg-emerald-950/40 border-2 border-emerald-500/60 anim-fall" style={{ animationDelay: '60ms' }}>
          <div className="flex items-center gap-1.5 font-mono font-bold text-[11px] text-emerald-300">
            <Award className="w-4 h-4 text-emerald-400" />
            Found {validated.objectName} in all {validated.exposuresCount} real frames
          </div>
          <div className="grid grid-cols-2 gap-1.5 mt-2 text-[10px] font-mono">
            <div className="bg-paper-950/70 p-1.5 rounded border border-emerald-900/60">
              <span className="text-paper-400 block">Baseline</span>
              <span className="text-emerald-400 font-bold">#{validated.baselineRank} of {validated.totalCandidates}</span>
            </div>
            <div className="bg-paper-950/70 p-1.5 rounded border border-emerald-900/60">
              <span className="text-paper-400 block">Random Forest</span>
              <span className="text-emerald-400 font-bold">#{validated.randomForestRank} of {validated.totalCandidates}</span>
            </div>
          </div>
          {isScientistMode && (
            <div className="mt-2 text-[10px] font-mono text-paper-400">
              Max offset {validated.maxOffsetPx} px · DOI{' '}
              <a href={validated.sourceUrl} target="_blank" rel="noreferrer" className="text-emerald-400 underline">
                {validated.datasetDoi}
              </a>
            </div>
          )}
        </div>
      )}

      <ol className="space-y-1.5">
        {ranked.map((r, i) => {
          const isSelected = r.candidate.id === selectedCandidateId;
          const pct = Math.round(r.score * 100);
          return (
            <li key={r.candidate.id} className="anim-fall" style={{ animationDelay: `${100 + i * 50}ms` }}>
              <button
                onClick={() => onSelectCandidate(r.candidate.id)}
                className={`btn-tactile-sm w-full p-2.5 rounded-lg border-2 border-black text-left flex items-center gap-2.5 cursor-pointer transition-all ${
                  isSelected ? 'bg-paper-800 ring-1 ring-emerald-400' : 'bg-paper-950 hover:bg-paper-900'
                }`}
              >
                <span
                  className={`w-7 h-7 shrink-0 rounded-md border-2 border-black flex items-center justify-center font-mono font-bold text-[11px] ${
                    r.rank === 1 ? 'bg-emerald-400 text-gray-950' : 'bg-paper-800 text-paper-200'
                  }`}
                >
                  #{r.rank}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[11px] text-paper-100 font-semibold truncate">
                      {r.candidate.validationData?.objectName || r.candidate.catalogId || r.candidate.id}
                    </span>
                    <span className="text-[10px] font-mono text-paper-400 shrink-0">
                      {CLASS_LABEL[r.candidate.classification] || 'New'}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    <div className="flex-1 h-1.5 rounded-full bg-paper-800 overflow-hidden">
                      <div
                        className={`h-full ${pct >= 70 ? 'bg-emerald-400' : pct >= 40 ? 'bg-amber-400' : 'bg-rose-400'}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-[10px] font-mono text-paper-300 w-8 text-right">{pct}%</span>
                  </div>
                </div>
              </button>
            </li>
          );
        })}
      </ol>

      {isScientistMode && (
        <p className="text-[10px] font-mono text-paper-500">
          Score = pipeline mlScore if provided, else baseline (SNR, epoch coverage, linear motion, flux stability).
        </p>
      )}
    </div>
  );
};
