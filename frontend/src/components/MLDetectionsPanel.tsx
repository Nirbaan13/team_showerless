import React, { useMemo, useState } from 'react';
import type { CandidateObject, MLAnalysisStatus } from '../types/spherex';
import { rankCandidates } from '../services/mlRanking';
import { Cpu, Sparkles, CheckCircle2, AlertTriangle, Layers } from 'lucide-react';

interface MLDetectionsPanelProps {
  candidates: CandidateObject[];
  selectedCandidateId: string | null;
  onSelectCandidate: (id: string) => void;
  isScientistMode?: boolean;
  mlAnalysisStatus?: MLAnalysisStatus;
  ra?: number;
  dec?: number;
}

const CLASS_LABEL: Record<string, string> = {
  moving_object: 'Moving',
  transient: 'Flash',
  already_known: 'Known',
  artifact: 'Artifact',
  unreviewed: 'New',
};

function StackImage({ src, alt }: { src?: string; alt: string }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  return src && failedUrl !== src
    ? <img src={src} alt={alt} width={29} height={29} onError={() => setFailedUrl(src)} className="w-full aspect-square bg-black [image-rendering:pixelated]" />
    : <div role="status" className="aspect-square flex items-center justify-center bg-paper-900 text-xs text-paper-400 text-center">Stack unavailable</div>;
}

export const MLDetectionsPanel: React.FC<MLDetectionsPanelProps> = ({
  candidates,
  selectedCandidateId,
  onSelectCandidate,
  isScientistMode = false,
  mlAnalysisStatus,
  ra,
  dec,
}) => {
  const [rankingMode, setRankingMode] = useState<'heuristic' | 'forest'>('heuristic');

  const isStored = mlAnalysisStatus?.resultSource === 'stored';
  const baseRanked = useMemo(() => rankCandidates(candidates), [candidates]);

  const ranked = useMemo(() => {
    const items = [...baseRanked];
    if (!isStored) return items.sort((a, b) => (a.candidate.mlRank ?? a.rank) - (b.candidate.mlRank ?? b.rank)).map(item => ({ ...item, displayRank: item.candidate.mlRank ?? item.rank }));
    if (rankingMode === 'forest') {
      items.sort((a, b) => {
        const rfA =
          a.candidate.randomForestRank ??
          a.candidate.validationData?.randomForestRank ??
          a.candidate.heuristicRank ??
          a.rank;
        const rfB =
          b.candidate.randomForestRank ??
          b.candidate.validationData?.randomForestRank ??
          b.candidate.heuristicRank ??
          b.rank;
        if (rfA !== rfB) return rfA - rfB;
        return b.score - a.score;
      });
    } else {
      items.sort((a, b) => {
        const hA =
          a.candidate.heuristicRank ??
          a.candidate.validationData?.baselineRank ??
          a.rank;
        const hB =
          b.candidate.heuristicRank ??
          b.candidate.validationData?.baselineRank ??
          b.rank;
        if (hA !== hB) return hA - hB;
        return b.score - a.score;
      });
    }

    return items.map((item, idx) => {
      const displayRank =
        rankingMode === 'forest'
          ? item.candidate.randomForestRank ??
            item.candidate.validationData?.randomForestRank ??
            idx + 1
          : item.candidate.heuristicRank ??
            item.candidate.validationData?.baselineRank ??
            idx + 1;
      return {
        ...item,
        displayRank,
      };
    });
  }, [baseRanked, rankingMode, isStored]);

  const validated = useMemo(
    () => baseRanked.find((r) => r.candidate.validationData)?.candidate.validationData,
    [baseRanked]
  );

  const activeCandidate = useMemo(() => {
    return (
      candidates.find((c) => c.id === selectedCandidateId) ||
      ranked[0]?.candidate ||
      null
    );
  }, [candidates, selectedCandidateId, ranked]);

  return (
    <div className="p-3.5 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between anim-fall">
        <span className="font-semibold text-paper-100 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
          <Cpu className="w-4 h-4 text-emerald-400" />
          AI Track Ranker &amp; Insights
        </span>
        <span className="text-[10px] font-mono text-paper-300 bg-paper-950 px-2 py-0.5 rounded border border-paper-800">
          {validated ? `${validated.totalCandidates} tracks` : `${ranked.length} tracks`}
        </span>
      </div>

      {/* Simultaneous Coordinate ML Analysis Status */}
      {mlAnalysisStatus && mlAnalysisStatus.state !== 'idle' && (
        <div
          className={`p-2.5 rounded-xl border transition-all anim-fall ${
            mlAnalysisStatus.state === 'running'
              ? 'bg-emerald-950/30 border-emerald-400/70 space-y-2'
              : mlAnalysisStatus.state === 'failed' ? 'bg-red-950/30 border-red-400/70' : 'bg-paper-950 border-emerald-500/40'
          }`}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 min-w-0">
              {mlAnalysisStatus.state === 'running' ? (
                <Cpu className="w-3.5 h-3.5 text-emerald-400 animate-spin shrink-0" />
              ) : mlAnalysisStatus.state === 'failed' ? (
                <AlertTriangle className="w-3.5 h-3.5 text-red-400 shrink-0" />
              ) : (
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              )}
              <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-emerald-300 truncate">
                {mlAnalysisStatus.state === 'running'
                  ? mlAnalysisStatus.stepIndex === 1 ? 'Loading observations…' : 'Preparing difference images…'
                  : mlAnalysisStatus.state === 'failed' ? 'Coordinate ML failed' : isStored ? 'Stored benchmark · no new inference' : 'Coordinate ML Ready'}
              </span>
            </div>
            {ra !== undefined && dec !== undefined && (
              <span className="text-[9px] font-mono text-paper-400 shrink-0">
                {ra.toFixed(2)}°, {dec >= 0 ? `+${dec.toFixed(2)}` : dec.toFixed(2)}°
              </span>
            )}
          </div>

          {mlAnalysisStatus.state === 'failed' && <p className="mt-2 text-xs text-red-300">{mlAnalysisStatus.stage}. Motion cannot be assessed until analysis completes.</p>}
          {mlAnalysisStatus.state === 'running' && (
            <div className="space-y-1.5">
              <p className="text-[10px] font-mono text-paper-200">{mlAnalysisStatus.stage}</p>
              <div className="w-full h-1.5 bg-paper-900 rounded-full overflow-hidden border border-paper-800">
                <div
                  className="h-full bg-gradient-to-r from-emerald-400 to-sky-400 transition-all duration-300"
                  style={{ width: `${mlAnalysisStatus.progress}%` }}
                />
              </div>
              <div className="grid grid-cols-3 gap-1 pt-0.5 text-[9px] font-mono">
                <span className={mlAnalysisStatus.stepIndex >= 1 ? 'text-emerald-300 font-bold' : 'text-paper-500'}>
                  1. Download
                </span>
                <span className={mlAnalysisStatus.stepIndex >= 2 ? 'text-emerald-300 font-bold' : 'text-paper-500'}>
                  2. Difference
                </span>
                <span className={mlAnalysisStatus.stepIndex >= 3 ? 'text-emerald-300 font-bold' : 'text-paper-500'}>
                  3. Results
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      <section aria-label="Analysis provenance" className="p-2.5 rounded-xl bg-paper-950 border border-paper-800 text-[10px] font-mono space-y-1 break-words">
        <p>Result source: {isStored ? 'Packaged benchmark review (/motion/review.json)' : 'Backend analysis'}</p>
        <p>Model: <span>{mlAnalysisStatus?.modelName ?? 'Model ID unavailable in stored review'}</span></p>
        <p>Algorithm: <span>{mlAnalysisStatus?.modelFamily ?? (isStored ? 'Stored leave-one-out / BLOOM tracks; optional RF ranks' : 'Unavailable')}</span></p>
        {mlAnalysisStatus?.modelSha256 && <details><summary>Model SHA-256</summary><p>{mlAnalysisStatus.modelSha256}</p></details>}
        {mlAnalysisStatus?.scoreKind && <p>Score kind: <span>{mlAnalysisStatus.scoreKind}</span></p>}
        {mlAnalysisStatus?.scoreDescription && <p>{mlAnalysisStatus.scoreDescription}</p>}
        <p>Scores order candidates; they are not discovery probabilities.</p>
      </section>
      {isStored && <div className="flex gap-2" role="group" aria-label="Stored ranking method">
        <button type="button" aria-pressed={rankingMode === 'heuristic'} onClick={() => setRankingMode('heuristic')} className="px-2 py-1 border rounded text-xs">Stored heuristic rank</button>
        <button type="button" aria-pressed={rankingMode === 'forest'} disabled={!candidates.some(c => c.randomForestRank != null)} onClick={() => setRankingMode('forest')} className="px-2 py-1 border rounded text-xs disabled:opacity-40">Stored RF rank</button>
      </div>}

      {/* Stack assets are evidence only when returned by the pipeline. */}
      {activeCandidate && (
        <section className="p-3 rounded-xl bg-paper-950 border border-paper-800 space-y-3" aria-label="Candidate image stacks">
          <h3 className="font-mono text-[11px] font-bold text-paper-100 flex items-center gap-1.5"><Layers className="w-3.5 h-3.5" />Shift &amp; Stack Coadd</h3>
          <p className="text-[10px] text-paper-400">
            {activeCandidate.stackContributingExposures !== undefined
              ? `${activeCandidate.stackContributingExposures} co-added exposures ${activeCandidate.stackContributingExposures >= 3 ? '(≥3 visits)' : '(<3 insufficient to stack)'}`
              : 'Co-add exposure count unavailable'}
          </p>
          <div className="grid grid-cols-2 gap-2">
            <figure className="space-y-1">
              <StackImage src={activeCandidate.fixedStackDataUrl} alt="Fixed sky position stack" />
              <figcaption className="text-[10px] text-paper-300">Fixed sky position</figcaption>
            </figure>
            <figure className="space-y-1">
              <StackImage src={activeCandidate.motionStackDataUrl} alt="Following the fitted track stack" />
              <figcaption className="text-[10px] text-paper-300">Along fitted track</figcaption>
            </figure>
          </div>
          <p className="text-[10px] text-paper-400">Compare the returned stacks; unavailable images provide no evidence about motion.</p>
        </section>
      )}

      {/* Ranked Candidates List Header */}
      <div className="flex items-center justify-between pt-0.5 px-0.5">
        <span className="text-[10px] font-mono uppercase tracking-wider text-paper-400 font-bold">
          Ranked Objects ({ranked.length})
        </span>
        <span className="text-[9px] font-mono text-emerald-400">
          Click to inspect on sky
        </span>
      </div>

      {/* Ranked Candidates List */}
      <ol className="space-y-2">
        {ranked.map((r, i) => {
          const isSelected = r.candidate.id === selectedCandidateId;
          const hRank = r.candidate.heuristicRank ?? r.candidate.validationData?.baselineRank ?? i + 1;
          const rfRank = r.candidate.randomForestRank ?? r.candidate.validationData?.randomForestRank;
          const isBloom = r.candidate.detectionMethod === 'bloom_centroids';

          return (
            <li
              key={r.candidate.id}
              className="anim-fall"
              style={{ animationDelay: `${80 + i * 35}ms` }}
            >
              <button
                type="button"
                onClick={() => onSelectCandidate(r.candidate.id)}
                className={`btn-tactile-sm w-full p-2.5 rounded-xl border-2 text-left flex items-center gap-2.5 cursor-pointer transition-all relative overflow-hidden ${
                  isSelected
                    ? 'bg-emerald-950/35 border-emerald-400 ring-2 ring-emerald-400/50 shadow-[0_0_18px_rgba(16,185,129,0.25)]'
                    : 'bg-paper-950 border-black opacity-80 hover:opacity-100 hover:bg-paper-900 hover:border-paper-700'
                }`}
              >
                {/* Left Accent Stripe on Selected Candidate */}
                {isSelected && (
                  <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-emerald-400" />
                )}

                <span
                  className={`w-7 h-7 shrink-0 rounded-md border-2 border-black flex items-center justify-center font-mono font-bold text-[11px] ${
                    isSelected
                      ? 'bg-emerald-400 text-gray-950'
                      : r.displayRank === 1
                      ? rankingMode === 'forest'
                        ? 'bg-sky-400 text-gray-950'
                        : isBloom
                        ? 'bg-amber-400 text-gray-950'
                        : 'bg-emerald-400/80 text-gray-950'
                      : 'bg-paper-800 text-paper-300'
                  }`}
                >
                  #{r.displayRank}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1.5">
                    <span className="font-mono text-[11px] text-paper-100 font-bold truncate flex items-center gap-1">
                      {r.candidate.isKnownCatalogMatch && (
                        <Sparkles className="w-3 h-3 text-emerald-400 shrink-0" />
                      )}
                      <span className="truncate">
                        {r.candidate.validationData?.objectName ||
                          r.candidate.catalogId ||
                          r.candidate.id}
                      </span>
                    </span>
                    {isSelected ? (
                      <span className="text-[9px] font-mono font-bold text-gray-950 bg-emerald-400 shrink-0 px-1.5 py-0.5 rounded border border-black shadow-sm">
                        ★ SELECTED
                      </span>
                    ) : (
                      <span className="text-[9px] font-mono text-paper-400 shrink-0 px-1.5 py-0.5 rounded bg-paper-900 border border-paper-800">
                        {isBloom ? 'BLOOM' : CLASS_LABEL[r.candidate.classification] || 'Track'}
                      </span>
                    )}
                  </div>
                  <div className="mt-1 flex items-center justify-between text-[9px] font-mono text-paper-400">
                    <span>
                      H:#{hRank}
                      {rfRank != null ? ` · RF:#${rfRank}` : ''} ·{' '}
                      {r.candidate.speedArcsecPerHour !== undefined ? `${r.candidate.speedArcsecPerHour.toFixed(1)}″/h` : 'Speed unavailable'}
                    </span>
                    <span className={isSelected ? 'text-emerald-300 font-bold' : 'text-paper-300 font-semibold'}>
                      {!isStored && r.source === 'pipeline' ? `Score ${r.score.toFixed(3)}` : 'Stored rank'}
                    </span>
                  </div>

                </div>
              </button>
            </li>
          );
        })}
      </ol>

      {isScientistMode && (
        <p className="text-[10px] font-mono text-paper-500">
          Stored ranking controls reorder packaged results. Live results retain the server ranking.
        </p>
      )}
    </div>
  );
};
