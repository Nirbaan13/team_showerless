import React, { useState } from 'react';
import type {
  SpherexEpochFrame,
  CandidateObject,
  CandidateClassification,
  ConfidenceLevel,
  SpectralDataPoint,
} from '../types/spherex';
import { SpectrumPlot } from './SpectrumPlot';
import { Activity, Radio, CheckCircle, AlertOctagon, HelpCircle } from 'lucide-react';

interface RightDrawerProps {
  frames: SpherexEpochFrame[];
  activeFrameIndex: number;
  onSelectFrame: (index: number) => void;
  candidate: CandidateObject | null;
  spectrumData: SpectralDataPoint[];
  onUpdateCandidateClassification: (
    candidateId: string,
    classification: CandidateClassification,
    confidence: ConfidenceLevel,
    notes: string
  ) => void;
}

export const RightDrawer: React.FC<RightDrawerProps> = ({
  frames,
  activeFrameIndex,
  onSelectFrame,
  candidate,
  spectrumData,
  onUpdateCandidateClassification,
}) => {
  const [activeTab, setActiveTab] = useState<'health' | 'spectrum' | 'triage'>('triage');
  const [notes, setNotes] = useState(candidate?.volunteerNotes || '');
  const [selectedClass, setSelectedClass] = useState<CandidateClassification>(
    candidate?.classification || 'unreviewed'
  );
  const [selectedConfidence, setSelectedConfidence] = useState<ConfidenceLevel>(
    candidate?.confidence || 'medium'
  );
  const [isSaved, setIsSaved] = useState(false);

  React.useEffect(() => {
    if (candidate) {
      setNotes(candidate.volunteerNotes);
      setSelectedClass(candidate.classification);
      setSelectedConfidence(candidate.confidence);
      setIsSaved(false);
    }
  }, [candidate]);

  const handleSaveTriage = () => {
    if (!candidate) return;
    onUpdateCandidateClassification(candidate.id, selectedClass, selectedConfidence, notes);
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2000);
  };

  return (
    <aside className="w-96 bg-space-900/95 border-l border-space-700/80 flex flex-col h-[calc(100vh-3.5rem)] text-xs select-none z-20">
      {/* Tab Navigation */}
      <div className="flex border-b border-space-700/80 bg-space-950/60">
        <button
          onClick={() => setActiveTab('triage')}
          className={`flex-1 py-2.5 font-mono text-[11px] font-medium border-b-2 flex items-center justify-center gap-1.5 transition-colors ${
            activeTab === 'triage'
              ? 'border-cyan-400 text-cyan-300 bg-space-900'
              : 'border-transparent text-space-400 hover:text-space-200'
          }`}
        >
          <CheckCircle className="w-3.5 h-3.5" />
          <span>Triage</span>
        </button>

        <button
          onClick={() => setActiveTab('spectrum')}
          className={`flex-1 py-2.5 font-mono text-[11px] font-medium border-b-2 flex items-center justify-center gap-1.5 transition-colors ${
            activeTab === 'spectrum'
              ? 'border-cyan-400 text-cyan-300 bg-space-900'
              : 'border-transparent text-space-400 hover:text-space-200'
          }`}
        >
          <Radio className="w-3.5 h-3.5" />
          <span>102-Band Spectra</span>
        </button>

        <button
          onClick={() => setActiveTab('health')}
          className={`flex-1 py-2.5 font-mono text-[11px] font-medium border-b-2 flex items-center justify-center gap-1.5 transition-colors ${
            activeTab === 'health'
              ? 'border-cyan-400 text-cyan-300 bg-space-900'
              : 'border-transparent text-space-400 hover:text-space-200'
          }`}
        >
          <Activity className="w-3.5 h-3.5" />
          <span>Data Health</span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* TAB 1: CITIZEN SCIENCE TRIAGE */}
        {activeTab === 'triage' && (
          <div className="space-y-4">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="font-telemetry text-space-100 font-semibold text-[11px] uppercase tracking-wider">
                  Target Inspection
                </span>
                <span className="text-[10px] font-mono text-cyan-400">
                  {candidate ? candidate.id : 'No Target Selected'}
                </span>
              </div>
              <p className="text-[11px] text-space-400 leading-relaxed font-sans">
                Review candidate motion across SPHEREx epochs. Confirm or dismiss based on motion consistency and catalog cross-matches.
              </p>
            </div>

            {candidate ? (
              <div className="space-y-3.5">
                {/* Catalog Match Pill */}
                {candidate.isKnownCatalogMatch && (
                  <div className="p-2.5 rounded bg-space-950 border border-space-700/80 flex items-start gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 mt-1 shrink-0" />
                    <div>
                      <div className="font-mono text-[11px] text-emerald-300 font-medium">
                        Catalog Cross-Match: {candidate.matchedCatalog}
                      </div>
                      <div className="text-[10px] font-mono text-space-400">
                        ID: {candidate.catalogId || 'N/A'}
                      </div>
                      {candidate.properMotionMasYr && (
                        <div className="text-[10px] font-mono text-space-400">
                          μ_RA: {candidate.properMotionMasYr.pmRa} mas/yr | μ_Dec: {candidate.properMotionMasYr.pmDec} mas/yr
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* 1-Click Classification Buttons (Zooniverse Backyard Worlds Style) */}
                <div>
                  <label className="text-[10px] font-mono text-space-400 block mb-1.5 uppercase">
                    Discovery Classification
                  </label>
                  <div className="grid grid-cols-2 gap-1.5">
                    {[
                      { id: 'moving_object', label: 'Moving Object', desc: 'Proper motion dipoles' },
                      { id: 'transient', label: 'Transient / Flare', desc: 'Single epoch flux burst' },
                      { id: 'already_known', label: 'Already Known', desc: 'Verified catalog match' },
                      { id: 'artifact', label: 'Artifact / Noise', desc: 'Bad pixel / cosmic ray' },
                    ].map((item) => {
                      const isSelected = selectedClass === item.id;
                      return (
                        <button
                          key={item.id}
                          onClick={() => setSelectedClass(item.id as CandidateClassification)}
                          className={`p-2 rounded border text-left transition-all ${
                            isSelected
                              ? 'bg-cyan-950/70 border-cyan-400 text-cyan-200 shadow-[0_0_8px_rgba(0,242,254,0.2)]'
                              : 'bg-space-950 border-space-700/80 text-space-300 hover:border-space-600'
                          }`}
                        >
                          <div className="font-mono text-[11px] font-semibold">{item.label}</div>
                          <div className="text-[9px] text-space-400 font-sans">{item.desc}</div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Confidence Level */}
                <div>
                  <label className="text-[10px] font-mono text-space-400 block mb-1.5 uppercase">
                    Confidence Level
                  </label>
                  <div className="grid grid-cols-3 gap-1.5">
                    {(['low', 'medium', 'high'] as ConfidenceLevel[]).map((lvl) => (
                      <button
                        key={lvl}
                        onClick={() => setSelectedConfidence(lvl)}
                        className={`py-1 rounded font-mono text-[11px] uppercase border transition-all ${
                          selectedConfidence === lvl
                            ? 'bg-cyan-950 border-cyan-400 text-cyan-300 font-bold'
                            : 'bg-space-950 border-space-700 text-space-400 hover:text-space-200'
                        }`}
                      >
                        {lvl}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Notes Input */}
                <div>
                  <label className="text-[10px] font-mono text-space-400 block mb-1 uppercase">
                    Observer Log / Rationale
                  </label>
                  <textarea
                    rows={3}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Enter observation rationale, PSF anomaly notes, or motion characteristics..."
                    className="w-full bg-space-950 border border-space-700 rounded p-2 font-mono text-[11px] text-space-200 focus:outline-none focus:border-cyan-400 resize-none"
                  />
                </div>

                {/* Save Confirmation Button */}
                <button
                  onClick={handleSaveTriage}
                  className="w-full py-2 bg-cyan-950 border border-cyan-400 text-cyan-300 hover:bg-cyan-900 rounded font-mono text-xs font-semibold shadow-[0_0_12px_rgba(0,242,254,0.2)] transition-all flex items-center justify-center gap-1.5"
                >
                  <CheckCircle className="w-3.5 h-3.5" />
                  <span>{isSaved ? 'Classification Recorded ✓' : 'Submit Candidate Triage'}</span>
                </button>
              </div>
            ) : (
              <div className="p-6 rounded border border-dashed border-space-700 text-center space-y-2">
                <HelpCircle className="w-8 h-8 text-space-600 mx-auto" />
                <div className="font-mono text-xs text-space-300">No Candidate Selected</div>
                <p className="text-[10px] text-space-500 font-sans">
                  Click any object in the celestial canvas to inspect its multi-epoch motion vectors and classify it.
                </p>
              </div>
            )}
          </div>
        )}

        {/* TAB 2: 102-BAND SPECTRUM */}
        {activeTab === 'spectrum' && (
          <div className="space-y-4">
            <div>
              <div className="font-telemetry text-space-100 font-semibold text-[11px] uppercase tracking-wider mb-1">
                Spectral Decomposition
              </div>
              <p className="text-[11px] text-space-400 leading-relaxed font-sans">
                Full 0.75 – 5.00 µm continuous spectrophotometry resolved across SPHEREx's 102 linear-variable filter (LVF) channels.
              </p>
            </div>

            <SpectrumPlot
              data={spectrumData}
              objectLabel={candidate?.matchedCatalog || candidate?.id || "Target"}
            />

            {/* Material Classification Badge */}
            <div className="p-3 rounded bg-space-950 border border-space-700/80 space-y-2">
              <div className="font-mono text-[11px] font-semibold text-cyan-300 flex items-center justify-between">
                <span>Spectroscopic Signature</span>
                <span className="text-[10px] bg-cyan-950 text-cyan-400 px-1.5 py-0.5 rounded border border-cyan-500/30">
                  Model Fit: 94.2%
                </span>
              </div>
              <p className="text-[10px] font-sans text-space-300 leading-relaxed">
                Strong 3.05 µm water-ice feature depression and 4.27 µm carbon dioxide absorption signature consistent with cold sub-stellar atmosphere (T_eff ≈ 280 K).
              </p>
            </div>
          </div>
        )}

        {/* TAB 3: DATA HEALTH SEQUENCE */}
        {activeTab === 'health' && (
          <div className="space-y-3">
            <div>
              <div className="font-telemetry text-space-100 font-semibold text-[11px] uppercase tracking-wider mb-1">
                Epoch Sequence Telemetry
              </div>
              <p className="text-[11px] text-space-400 leading-relaxed font-sans">
                FITS exposure data health, bad pixel flagging, and cosmic ray identification per epoch.
              </p>
            </div>

            <div className="space-y-2">
              {frames.map((f, idx) => {
                const isActive = idx === activeFrameIndex;
                const isSkipped = !f.isAvailable;

                return (
                  <div
                    key={f.frameId}
                    onClick={() => f.isAvailable && onSelectFrame(idx)}
                    className={`p-2.5 rounded border transition-all ${
                      isSkipped
                        ? 'bg-red-950/20 border-red-500/40 text-red-300/80 cursor-not-allowed'
                        : isActive
                        ? 'bg-space-800 border-cyan-400 text-space-100 shadow-[0_0_8px_rgba(0,242,254,0.15)] cursor-pointer'
                        : 'bg-space-950 border-space-700/80 text-space-300 hover:border-space-600 cursor-pointer'
                    }`}
                  >
                    <div className="flex items-center justify-between font-mono text-[11px]">
                      <div className="flex items-center gap-1.5 font-semibold">
                        <span className={`w-1.5 h-1.5 rounded-full ${isSkipped ? 'bg-red-400' : 'bg-cyan-400'}`} />
                        <span>Epoch {f.epochIndex + 1} ({f.observationDate.split('T')[0]})</span>
                      </div>
                      <span className="text-[10px] text-space-400">Band {f.detectorArray}</span>
                    </div>

                    {isSkipped ? (
                      <div className="mt-1 text-[10px] font-mono text-red-400/90 flex items-center gap-1">
                        <AlertOctagon className="w-3 h-3 text-red-400 shrink-0" />
                        <span>{f.skipReason}</span>
                      </div>
                    ) : (
                      <div className="mt-1.5 grid grid-cols-2 gap-2 text-[10px] font-mono text-space-400">
                        <div>
                          Flagged Pixels:{' '}
                          <span className={f.flaggedPixelPercentage > 1.0 ? 'text-amber-400' : 'text-space-200'}>
                            {f.flaggedPixelPercentage}%
                          </span>
                        </div>
                        <div>
                          CR Hits: <span className="text-space-200">{f.cosmicRayHits}</span>
                        </div>
                        <div>
                          Exp Time: <span className="text-space-200">{f.headerMetadata.exposureTimeSec}s</span>
                        </div>
                        <div>
                          SNR (est): <span className="text-cyan-400">{f.headerMetadata.snrEstimated}</span>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
