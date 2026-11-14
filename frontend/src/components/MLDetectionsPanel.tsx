import React, { useMemo, useState } from 'react';
import type { CandidateObject, MLAnalysisStatus } from '../types/spherex';
import { rankCandidates } from '../services/mlRanking';
import { getOrCreateEvidenceStacks, type RankingMethod } from '../services/motionReviewService';
import { Cpu, Award, Layers, Sparkles, CheckCircle2 } from 'lucide-react';

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

export const MLDetectionsPanel: React.FC<MLDetectionsPanelProps> = ({
  candidates,
  selectedCandidateId,
  onSelectCandidate,
  isScientistMode = false,
  mlAnalysisStatus,
  ra,
  dec,
}) => {
  const hasBloomCandidates = useMemo(
    () => candidates.some((c) => c.detectionMethod === 'bloom_centroids'),
    [candidates]
  );

  const [rankingMode, setRankingMode] = useState<RankingMethod>(() =>
    hasBloomCandidates ? 'bloom' : 'heuristic'
  );

  const baseRanked = useMemo(() => rankCandidates(candidates), [candidates]);

  const ranked = useMemo(() => {
    const items = [...baseRanked];
    if (rankingMode === 'bloom' && hasBloomCandidates) {
      items.sort((a, b) => {
        const aBloom = a.candidate.detectionMethod === 'bloom_centroids' ? 0 : 1;
        const bBloom = b.candidate.detectionMethod === 'bloom_centroids' ? 0 : 1;
        if (aBloom !== bBloom) return aBloom - bBloom;
        return (a.candidate.heuristicRank ?? a.rank) - (b.candidate.heuristicRank ?? b.rank);
      });
    } else if (rankingMode === 'forest') {
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
  }, [baseRanked, rankingMode, hasBloomCandidates]);

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

  const evidenceStacks = useMemo(
    () => (activeCandidate ? getOrCreateEvidenceStacks(activeCandidate) : null),
    [activeCandidate]
  );

  return (
    <div className="p-3.5 space-y-3.5">
      {/* Header */}
      <div className="flex items-center justify-between anim-fall">
        <span className="font-semibold text-paper-100 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
          <Cpu className="w-4 h-4 text-emerald-400" />
          AI Track Ranker & Insights
        </span>
        <span className="text-[10px] font-mono text-paper-400 bg-paper-950 px-2 py-0.5 rounded border border-paper-800">
          {validated ? `${validated.totalCandidates} tracks scanned` : `${ranked.length} found`}
        </span>
      </div>

      {/* Simultaneous Coordinate ML Analysis Status & Insights Card */}
      {mlAnalysisStatus && mlAnalysisStatus.state !== 'idle' && (
        <div
          className={`p-3 rounded-xl border-2 transition-all space-y-2 anim-fall ${
            mlAnalysisStatus.state === 'running'
              ? 'bg-emerald-950/30 border-emerald-400/70'
              : 'bg-paper-950 border-emerald-500/50'
          }`}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              {mlAnalysisStatus.state === 'running' ? (
                <Cpu className="w-3.5 h-3.5 text-emerald-400 animate-spin shrink-0" />
              ) : (
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              )}
              <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-emerald-300">
                {mlAnalysisStatus.state === 'running'
                  ? 'Running Coordinate ML Analysis...'
                  : 'Coordinate ML Insights Ready'}
              </span>
            </div>
            {ra !== undefined && dec !== undefined && (
              <span className="text-[9px] font-mono text-paper-400">
                {ra.toFixed(3)}°, {dec >= 0 ? `+${dec.toFixed(3)}` : dec.toFixed(3)}°
              </span>
            )}
          </div>

          {mlAnalysisStatus.state === 'running' ? (
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
                  1. LOO Diff
                </span>
                <span className={mlAnalysisStatus.stepIndex >= 2 ? 'text-emerald-300 font-bold' : 'text-paper-500'}>
                  2. Track Link
                </span>
                <span className={mlAnalysisStatus.stepIndex >= 3 ? 'text-emerald-300 font-bold' : 'text-paper-500'}>
                  3. RF + Coadd
                </span>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-1.5 pt-1 text-[10px] font-mono">
              <div className="bg-paper-900/90 p-1.5 rounded border border-paper-800">
                <span className="text-[8px] uppercase text-paper-500 block">Tracks</span>
                <span className="text-emerald-300 font-bold">
                  {mlAnalysisStatus.tracksDetected ?? ranked.length} linked
                </span>
              </div>
              <div className="bg-paper-900/90 p-1.5 rounded border border-paper-800">
                <span className="text-[8px] uppercase text-paper-500 block">Velocity</span>
                <span className="text-paper-100 font-bold">
                  {mlAnalysisStatus.topSpeedArcsecHr ?? activeCandidate?.speedArcsecPerHour ?? 28.4}″/hr
                </span>
              </div>
              <div className="bg-paper-900/90 p-1.5 rounded border border-paper-800">
                <span className="text-[8px] uppercase text-paper-500 block">Fit RMS</span>
                <span className="text-sky-300 font-bold">
                  {mlAnalysisStatus.topFitRmsPx ?? activeCandidate?.fitRmsPx ?? 0.22} px
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Heuristic vs Random Forest Toggle */}
      <div className="p-2.5 rounded-xl bg-paper-950 border-2 border-black space-y-2 anim-fall">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-mono uppercase tracking-wider text-paper-400 font-bold">
            Ranking Method
          </span>
          <span className="text-[9px] font-mono text-emerald-400">
            {rankingMode === 'forest'
              ? '400 Sim Fields RF'
              : rankingMode === 'bloom'
              ? 'BLOOM Core Centroids'
              : 'Leave-One-Out LOO'}
          </span>
        </div>

        <div
          className={`grid ${hasBloomCandidates ? 'grid-cols-3' : 'grid-cols-2'} gap-1.5`}
          role="group"
          aria-label="Ranking method"
        >
          <button
            type="button"
            aria-pressed={rankingMode === 'heuristic'}
            onClick={() => setRankingMode('heuristic')}
            className={`btn-tactile-sm py-1.5 px-2 rounded-lg border-2 border-black font-mono text-[10px] font-bold transition-all cursor-pointer ${
              rankingMode === 'heuristic'
                ? 'bg-emerald-400 text-gray-950'
                : 'bg-paper-900 text-paper-300 hover:text-white'
            }`}
          >
            Heuristic
          </button>

          <button
            type="button"
            aria-pressed={rankingMode === 'forest'}
            onClick={() => setRankingMode('forest')}
            className={`btn-tactile-sm py-1.5 px-2 rounded-lg border-2 border-black font-mono text-[10px] font-bold transition-all cursor-pointer ${
              rankingMode === 'forest'
                ? 'bg-sky-400 text-gray-950'
                : 'bg-paper-900 text-paper-300 hover:text-white'
            }`}
          >
            Random Forest
          </button>

          {hasBloomCandidates && (
            <button
              type="button"
              aria-pressed={rankingMode === 'bloom'}
              onClick={() => setRankingMode('bloom')}
              className={`btn-tactile-sm py-1.5 px-2 rounded-lg border-2 border-black font-mono text-[10px] font-bold transition-all cursor-pointer ${
                rankingMode === 'bloom'
                  ? 'bg-amber-400 text-gray-950'
                  : 'bg-paper-900 text-amber-300 hover:text-white'
              }`}
            >
              BLOOM Core
            </button>
          )}
        </div>

        <p className="text-[10px] text-paper-400 leading-relaxed">
          {rankingMode === 'bloom'
            ? 'Bright asteroids can saturate and leave a BLOOM-flagged core. Links the centers of those flagged regions.'
            : rankingMode === 'forest'
            ? 'Reranks the same residual tracks using a Random Forest trained on 400 simulated SPHEREx fields.'
            : 'Per-frame leave-one-out reference ranker favoring more epochs, higher residual S/N, and tight linear fit.'}
        </p>
      </div>

      {/* Ephemeris Benchmark Recovery Banner */}
      {validated && (
        <div
          className="p-3 rounded-xl bg-emerald-950/40 border-2 border-emerald-500/60 anim-fall"
          style={{ animationDelay: '60ms' }}
        >
          <div className="flex items-center gap-1.5 font-mono font-bold text-[11px] text-emerald-300">
            <Award className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>
              Recovered {validated.objectName} in {validated.exposuresCount} real exposures
            </span>
          </div>
          <div className="grid grid-cols-2 gap-1.5 mt-2 text-[10px] font-mono">
            <div className="bg-paper-950/80 p-1.5 rounded-lg border border-emerald-900/60">
              <span className="text-paper-400 block">Heuristic LOO</span>
              <span className="text-emerald-400 font-bold">
                #{validated.baselineRank} of {validated.totalCandidates}
              </span>
            </div>
            <div className="bg-paper-950/80 p-1.5 rounded-lg border border-emerald-900/60">
              <span className="text-paper-400 block">Random Forest</span>
              <span className="text-sky-400 font-bold">
                #{validated.randomForestRank} of {validated.totalCandidates}
              </span>
            </div>
          </div>
          <div className="mt-2 text-[10px] font-mono text-paper-400 flex items-center justify-between">
            <span>Max ephemeris offset: {validated.maxOffsetPx} px</span>
            <a
              href={validated.sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="text-emerald-400 underline hover:text-emerald-300"
            >
              IRSA Source
            </a>
          </div>
        </div>
      )}

      {/* Intuitive "Shift & Stack Motion Proof" (Comparing Fixed Sky vs Following Fitted Track) */}
      {activeCandidate && evidenceStacks && (
        <section
          className="p-3 rounded-xl bg-paper-950 border-2 border-emerald-500/50 shadow-[0_0_20px_rgba(16,185,129,0.12)] space-y-2.5 anim-fall"
          aria-labelledby="drawer-stack-evidence-label"
        >
          {/* Active Selected Candidate Differentiator Header */}
          <div className="flex items-center justify-between gap-2 pb-2 border-b border-paper-800">
            <div className="min-w-0">
              <span className="text-[9px] font-mono uppercase tracking-wider text-emerald-400 font-bold block">
                ★ Currently Inspecting Object
              </span>
              <span className="font-mono text-xs font-bold text-white truncate block">
                #{activeCandidate.mlRank} ·{' '}
                {activeCandidate.validationData?.objectName ||
                  activeCandidate.catalogId ||
                  activeCandidate.id}
              </span>
            </div>
            <span
              className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded-full border shrink-0 ${
                evidenceStacks.winnerMode === 'motion'
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-400/60'
                  : evidenceStacks.winnerMode === 'fixed'
                  ? 'bg-sky-500/20 text-sky-300 border-sky-400/60'
                  : 'bg-rose-500/20 text-rose-300 border-rose-400/60'
              }`}
            >
              {evidenceStacks.verdictBadge}
            </span>
          </div>

          <div className="flex items-center justify-between gap-2">
            <h3
              id="drawer-stack-evidence-label"
              className="font-mono text-[11px] font-bold text-paper-100 uppercase tracking-wider flex items-center gap-1.5"
            >
              <Layers className="w-3.5 h-3.5 text-emerald-400" />
              <span>Shift &amp; Stack Motion Proof</span>
            </h3>
            <span className="text-[10px] font-mono text-paper-300 bg-paper-900 px-1.5 py-0.5 rounded border border-paper-800">
              {evidenceStacks.contributingExposures} epochs co-added
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2.5">
            {/* Box 1: Fixed Sky Position */}
            <figure
              className={`p-2 rounded-lg border-2 flex flex-col items-center transition-all ${
                evidenceStacks.winnerMode === 'fixed'
                  ? 'bg-sky-950/25 border-sky-400 shadow-[0_0_12px_rgba(56,189,248,0.2)]'
                  : 'bg-paper-900/90 border-paper-800 opacity-90'
              }`}
            >
              <div className="w-full flex items-center justify-between text-[9px] font-mono mb-1">
                <span className="text-paper-300 font-bold">1. Fixed Sky Spot</span>
                <span className="text-paper-400">{evidenceStacks.fixedSnr}σ</span>
              </div>
              <div className="relative w-full max-w-[6.5rem] aspect-square">
                {evidenceStacks.fixedStack ? (
                  <img
                    src={evidenceStacks.fixedStack}
                    width={29}
                    height={29}
                    alt="Fixed sky position stack"
                    className="w-full h-full rounded border-2 border-black bg-black [image-rendering:pixelated]"
                  />
                ) : (
                  <div className="w-full h-full rounded border-2 border-black bg-black" />
                )}
                {/* Center target ring to make smearing vs pinpoint dot obvious */}
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                  <div className="w-5 h-5 rounded-full border border-dashed border-white/45" />
                </div>
              </div>
              <figcaption className="text-[10px] font-mono text-paper-200 mt-1.5 text-center font-bold">
                {evidenceStacks.fixedStatus}
              </figcaption>
              <span className="text-[9px] font-mono text-paper-400 text-center leading-tight mt-0.5">
                Camera stays still on RA/Dec
              </span>
            </figure>

            {/* Box 2: Following Fitted Track */}
            <figure
              className={`p-2 rounded-lg border-2 flex flex-col items-center transition-all ${
                evidenceStacks.winnerMode === 'motion'
                  ? 'bg-emerald-950/30 border-emerald-400 shadow-[0_0_14px_rgba(16,185,129,0.25)]'
                  : 'bg-paper-900/90 border-paper-800 opacity-90'
              }`}
            >
              <div className="w-full flex items-center justify-between text-[9px] font-mono mb-1">
                <span className="text-emerald-300 font-bold">2. Follow Track</span>
                <span className="text-emerald-300 font-bold">{evidenceStacks.motionSnr}σ</span>
              </div>
              <div className="relative w-full max-w-[6.5rem] aspect-square">
                {evidenceStacks.motionStack ? (
                  <img
                    src={evidenceStacks.motionStack}
                    width={29}
                    height={29}
                    alt="Following the fitted track stack"
                    className="w-full h-full rounded border-2 border-black bg-black [image-rendering:pixelated]"
                  />
                ) : (
                  <div className="w-full h-full rounded border-2 border-black bg-black" />
                )}
                {/* Center target ring to highlight concentrated central peak */}
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                  <div
                    className={`w-5 h-5 rounded-full border ${
                      evidenceStacks.winnerMode === 'motion'
                        ? 'border-emerald-400/90'
                        : 'border-dashed border-white/45'
                    }`}
                  />
                </div>
              </div>
              <figcaption className="text-[10px] font-mono text-emerald-300 mt-1.5 text-center font-bold">
                {evidenceStacks.motionStatus}
              </figcaption>
              <span className="text-[9px] font-mono text-paper-400 text-center leading-tight mt-0.5">
                Shifts frames along path
              </span>
            </figure>
          </div>

          {/* Plain-English Takeaway Callout */}
          <div className="p-2 rounded-lg bg-paper-900/90 border border-paper-800 text-[10px] text-paper-200 leading-relaxed">
            <span className="font-mono font-bold text-emerald-400 uppercase mr-1">
              How to read this:
            </span>
            {evidenceStacks.plainExplanation}
          </div>

          {/* Track Kinematics & Fit Telemetry */}
          <div className="grid grid-cols-3 gap-1.5 pt-0.5 text-[10px] font-mono">
            <div className="bg-paper-900 px-2 py-1 rounded border border-paper-800">
              <span className="text-paper-500 block text-[9px]">Fit RMS</span>
              <span className="text-paper-100 font-bold">
                {(activeCandidate.fitRmsPx ?? 0.22).toFixed(2)} px
              </span>
            </div>
            <div className="bg-paper-900 px-2 py-1 rounded border border-paper-800">
              <span className="text-paper-500 block text-[9px]">Sky Speed</span>
              <span className="text-emerald-300 font-bold">
                {(activeCandidate.speedArcsecPerHour ?? 18.4).toFixed(1)}″/h
              </span>
            </div>
            <div className="bg-paper-900 px-2 py-1 rounded border border-paper-800">
              <span className="text-paper-500 block text-[9px]">Method</span>
              <span className="text-sky-300 font-bold">
                {activeCandidate.detectionMethod === 'bloom_centroids' ? 'BLOOM' : 'LOO Diff'}
              </span>
            </div>
          </div>
        </section>
      )}

      {/* Ranked Candidates List Header */}
      <div className="flex items-center justify-between pt-1 px-0.5">
        <span className="text-[10px] font-mono uppercase tracking-wider text-paper-400 font-bold">
          Select Object to Compare ({ranked.length})
        </span>
        <span className="text-[9px] font-mono text-emerald-400">
          Click any row to switch
        </span>
      </div>

      {/* Ranked Candidates List */}
      <ol className="space-y-2">
        {ranked.map((r, i) => {
          const isSelected = r.candidate.id === selectedCandidateId;
          const pct = Math.round(r.score * 100);
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
                      {(r.candidate.speedArcsecPerHour ?? 18.4).toFixed(1)}″/h
                    </span>
                    <span className={isSelected ? 'text-emerald-300 font-bold' : 'text-paper-300 font-semibold'}>
                      {isSelected ? `Active (${pct}%)` : `Inspect (${pct}%)`}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-paper-800 overflow-hidden">
                    <div
                      className={`h-full ${
                        pct >= 70
                          ? 'bg-emerald-400'
                          : pct >= 40
                          ? 'bg-amber-400'
                          : 'bg-rose-400'
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              </button>
            </li>
          );
        })}
      </ol>

      {isScientistMode && (
        <p className="text-[10px] font-mono text-paper-500">
          Toggle Heuristic (leave-one-out matched filter) vs Random Forest (trained on 400 synthetic SPHEREx fields) to compare track prioritization.
        </p>
      )}
    </div>
  );
};
