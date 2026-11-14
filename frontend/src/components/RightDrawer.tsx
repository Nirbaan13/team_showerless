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
    <aside className="w-80 bg-nasa-surface border-l border-nasa-border flex flex-col h-[calc(100vh-3rem)] text-xs select-none z-20">
      {/* Tab Navigation */}
      <div className="flex border-b border-nasa-border bg-nasa-dark">
        <button
          onClick={() => setActiveTab('triage')}
          className={`flex-1 py-2 font-mono text-[11px] font-medium border-b-2 flex items-center justify-center gap-1.5 transition-colors ${
            activeTab === 'triage'
              ? 'border-blue-500 text-blue-200 bg-nasa-surface'
              : 'border-transparent text-nasa-textMuted hover:text-nasa-textMain'
          }`}
        >
          <CheckCircle className="w-3.5 h-3.5" />
          <span>Triage</span>
        </button>

        <button
          onClick={() => setActiveTab('spectrum')}
          className={`flex-1 py-2 font-mono text-[11px] font-medium border-b-2 flex items-center justify-center gap-1.5 transition-colors ${
            activeTab === 'spectrum'
              ? 'border-blue-500 text-blue-200 bg-nasa-surface'
              : 'border-transparent text-nasa-textMuted hover:text-nasa-textMain'
          }`}
        >
          <Radio className="w-3.5 h-3.5" />
          <span>102 Bands</span>
        </button>

        <button
          onClick={() => setActiveTab('health')}
          className={`flex-1 py-2 font-mono text-[11px] font-medium border-b-2 flex items-center justify-center gap-1.5 transition-colors ${
            activeTab === 'health'
              ? 'border-blue-500 text-blue-200 bg-nasa-surface'
              : 'border-transparent text-nasa-textMuted hover:text-nasa-textMain'
          }`}
        >
          <Activity className="w-3.5 h-3.5" />
          <span>FITS Health</span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {/* TAB 1: CITIZEN SCIENCE TRIAGE */}
        {activeTab === 'triage' && (
          <div className="space-y-3">
            <div>
              <div className="flex items-center justify-between mb-0.5">
                <span className="font-semibold text-nasa-textMain uppercase tracking-wider text-[11px]">
                  Object Inspection
                </span>
                <span className="text-[10px] font-mono text-blue-400">
                  {candidate ? candidate.id : 'None'}
                </span>
              </div>
              <p className="text-[11px] text-nasa-textMuted leading-normal">
                Classify candidate motion between SPHEREx observation epochs.
              </p>
            </div>

            {candidate ? (
              <div className="space-y-2.5">
                {/* Catalog Cross-match Info */}
                {candidate.isKnownCatalogMatch && (
                  <div className="p-2 rounded bg-nasa-dark border border-nasa-border">
                    <div className="font-mono text-[11px] text-emerald-400 font-medium">
                      Matched: {candidate.matchedCatalog}
                    </div>
                    <div className="text-[10px] font-mono text-nasa-textMuted">
                      {candidate.catalogId || 'N/A'}
                    </div>
                    {candidate.properMotionMasYr && (
                      <div className="text-[10px] font-mono text-nasa-textMuted">
                        pmRA: {candidate.properMotionMasYr.pmRa} mas/yr | pmDec: {candidate.properMotionMasYr.pmDec} mas/yr
                      </div>
                    )}
                  </div>
                )}

                {/* 1-Click Classification Buttons */}
                <div>
                  <label className="text-[10px] font-mono text-nasa-textMuted block mb-1 uppercase">
                    Classification
                  </label>
                  <div className="grid grid-cols-2 gap-1">
                    {[
                      { id: 'moving_object', label: 'Moving Object', desc: 'Proper motion dipole' },
                      { id: 'transient', label: 'Transient / Flare', desc: 'Episodic flux burst' },
                      { id: 'already_known', label: 'Already Known', desc: 'Catalog verified' },
                      { id: 'artifact', label: 'Artifact', desc: 'Bad pixel / cosmic ray' },
                    ].map((item) => {
                      const isSelected = selectedClass === item.id;
                      return (
                        <button
                          key={item.id}
                          onClick={() => setSelectedClass(item.id as CandidateClassification)}
                          className={`p-1.5 rounded border text-left transition-colors ${
                            isSelected
                              ? 'bg-blue-900/50 border-blue-500 text-blue-100 font-medium'
                              : 'bg-nasa-dark border-nasa-border text-nasa-textMuted hover:border-nasa-subtle'
                          }`}
                        >
                          <div className="font-mono text-[11px]">{item.label}</div>
                          <div className="text-[9px] text-nasa-textMuted">{item.desc}</div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Confidence Level */}
                <div>
                  <label className="text-[10px] font-mono text-nasa-textMuted block mb-1 uppercase">
                    Confidence
                  </label>
                  <div className="grid grid-cols-3 gap-1">
                    {(['low', 'medium', 'high'] as ConfidenceLevel[]).map((lvl) => (
                      <button
                        key={lvl}
                        onClick={() => setSelectedConfidence(lvl)}
                        className={`py-1 rounded font-mono text-[10px] uppercase border transition-colors ${
                          selectedConfidence === lvl
                            ? 'bg-blue-900/60 border-blue-500 text-blue-200 font-semibold'
                            : 'bg-nasa-dark border-nasa-border text-nasa-textMuted hover:text-nasa-textMain'
                        }`}
                      >
                        {lvl}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Notes Input */}
                <div>
                  <label className="text-[10px] font-mono text-nasa-textMuted block mb-1 uppercase">
                    Observation Notes
                  </label>
                  <textarea
                    rows={2}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Enter observation notes or PSF characteristics..."
                    className="w-full bg-nasa-dark border border-nasa-border rounded p-1.5 font-mono text-[11px] text-nasa-textMain focus:outline-none focus:border-blue-500 resize-none"
                  />
                </div>

                {/* Submit Button */}
                <button
                  onClick={handleSaveTriage}
                  className="w-full py-1.5 bg-nasa-blue text-white hover:bg-blue-600 rounded font-mono text-xs font-medium transition-colors flex items-center justify-center gap-1.5"
                >
                  <CheckCircle className="w-3.5 h-3.5" />
                  <span>{isSaved ? 'Recorded ✓' : 'Save Classification'}</span>
                </button>
              </div>
            ) : (
              <div className="p-4 rounded border border-dashed border-nasa-border text-center space-y-1">
                <HelpCircle className="w-6 h-6 text-nasa-textMuted mx-auto" />
                <div className="font-mono text-xs text-nasa-textMuted">No Target Selected</div>
                <p className="text-[10px] text-nasa-textMuted">
                  Click any object in the viewport to classify it.
                </p>
              </div>
            )}
          </div>
        )}

        {/* TAB 2: 102-BAND SPECTRUM */}
        {activeTab === 'spectrum' && (
          <div className="space-y-3">
            <div>
              <span className="font-semibold text-nasa-textMain uppercase tracking-wider text-[11px] block mb-0.5">
                Spectral Decomposition
              </span>
              <p className="text-[11px] text-nasa-textMuted">
                Calibrated 0.75 – 5.00 µm spectrophotometry across 102 channels.
              </p>
            </div>

            <SpectrumPlot
              data={spectrumData}
              objectLabel={candidate?.matchedCatalog || candidate?.id || "Target"}
            />

            <div className="p-2.5 rounded bg-nasa-dark border border-nasa-border space-y-1">
              <div className="font-mono text-[11px] font-medium text-blue-300 flex items-center justify-between">
                <span>Atmospheric Signature</span>
                <span className="text-[10px] text-nasa-textMuted">Fit: 94.2%</span>
              </div>
              <p className="text-[10px] text-nasa-textMuted leading-relaxed">
                Depression at 3.05 µm (H₂O) and 4.27 µm (CO₂) consistent with cold sub-stellar atmosphere.
              </p>
            </div>
          </div>
        )}

        {/* TAB 3: DATA HEALTH */}
        {activeTab === 'health' && (
          <div className="space-y-2">
            <div>
              <span className="font-semibold text-nasa-textMain uppercase tracking-wider text-[11px] block mb-0.5">
                FITS Frame Telemetry
              </span>
              <p className="text-[11px] text-nasa-textMuted">
                Exposure metadata, flagged pixels, and cosmic ray identification.
              </p>
            </div>

            <div className="space-y-1.5">
              {frames.map((f, idx) => {
                const isActive = idx === activeFrameIndex;
                const isSkipped = !f.isAvailable;

                return (
                  <div
                    key={f.frameId}
                    onClick={() => f.isAvailable && onSelectFrame(idx)}
                    className={`p-2 rounded border transition-colors ${
                      isSkipped
                        ? 'bg-red-950/20 border-red-900/50 text-red-300/80 cursor-not-allowed'
                        : isActive
                        ? 'bg-nasa-dark border-blue-500 text-nasa-textMain cursor-pointer'
                        : 'bg-nasa-dark/60 border-nasa-border text-nasa-textMuted hover:border-nasa-subtle cursor-pointer'
                    }`}
                  >
                    <div className="flex items-center justify-between font-mono text-[11px]">
                      <div className="flex items-center gap-1.5 font-medium">
                        <span className={`w-1.5 h-1.5 rounded-full ${isSkipped ? 'bg-red-500' : 'bg-blue-400'}`} />
                        <span>Epoch {f.epochIndex + 1} ({f.observationDate.split('T')[0]})</span>
                      </div>
                      <span className="text-[10px] text-nasa-textMuted">Band {f.detectorArray}</span>
                    </div>

                    {isSkipped ? (
                      <div className="mt-1 text-[10px] font-mono text-red-400/90 flex items-center gap-1">
                        <AlertOctagon className="w-3 h-3 text-red-400 shrink-0" />
                        <span>{f.skipReason}</span>
                      </div>
                    ) : (
                      <div className="mt-1 grid grid-cols-2 gap-1.5 text-[10px] font-mono text-nasa-textMuted">
                        <div>Flagged: {f.flaggedPixelPercentage}%</div>
                        <div>CR Hits: {f.cosmicRayHits}</div>
                        <div>Exp: {f.headerMetadata.exposureTimeSec}s</div>
                        <div>SNR: {f.headerMetadata.snrEstimated}</div>
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
