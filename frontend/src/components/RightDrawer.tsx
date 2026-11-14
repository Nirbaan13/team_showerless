import React, { useState } from 'react';
import type {
  SpherexEpochFrame,
  CandidateObject,
  CandidateClassification,
  ConfidenceLevel,
  SpectralDataPoint,
} from '../types/spherex';
import { SpectrumPlot } from './SpectrumPlot';
import { CommunityVerificationStream } from './CommunityVerificationStream';
import { CheckCircle, Radio, Activity, HelpCircle, MessageSquare, Maximize2, Minimize2, FileText } from 'lucide-react';

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
  onBroadcastToChat?: (text: string) => void;
  onOpenDiscoveryReport?: () => void;
}

export const RightDrawer: React.FC<RightDrawerProps> = ({
  frames,
  activeFrameIndex,
  onSelectFrame,
  candidate,
  spectrumData,
  onUpdateCandidateClassification,
  onOpenDiscoveryReport,
}) => {
  const [activeTab, setActiveTab] = useState<'triage' | 'spectrum' | 'community' | 'health'>('community');
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
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
    <aside
      className={`${
        isExpanded ? 'w-[520px]' : 'w-80'
      } bg-paper-900 border-l border-paper-800 flex flex-col h-[calc(100vh-3rem)] text-xs select-none transition-all duration-200 z-20`}
    >
      {/* Drawer Header & Width Expansion Controls */}
      <div className="flex border-b border-paper-800 bg-paper-950 items-center justify-between px-2">
        <div className="flex space-x-1">
          <button
            onClick={() => setActiveTab('community')}
            className={`py-2 px-2.5 font-mono text-[11px] font-medium border-b-2 flex items-center gap-1.5 transition-colors ${
              activeTab === 'community'
                ? 'border-ochre-400 text-paper-100 bg-paper-900'
                : 'border-transparent text-paper-400 hover:text-paper-200'
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5 text-ochre-400" />
            <span>Chat</span>
          </button>

          <button
            onClick={() => setActiveTab('triage')}
            className={`py-2 px-2.5 font-mono text-[11px] font-medium border-b-2 flex items-center gap-1.5 transition-colors ${
              activeTab === 'triage'
                ? 'border-ochre-400 text-paper-100 bg-paper-900'
                : 'border-transparent text-paper-400 hover:text-paper-200'
            }`}
          >
            <CheckCircle className="w-3.5 h-3.5" />
            <span>Triage</span>
          </button>

          <button
            onClick={() => setActiveTab('spectrum')}
            className={`py-2 px-2.5 font-mono text-[11px] font-medium border-b-2 flex items-center gap-1.5 transition-colors ${
              activeTab === 'spectrum'
                ? 'border-ochre-400 text-paper-100 bg-paper-900'
                : 'border-transparent text-paper-400 hover:text-paper-200'
            }`}
          >
            <Radio className="w-3.5 h-3.5" />
            <span>102 Bands</span>
          </button>

          <button
            onClick={() => setActiveTab('health')}
            className={`py-2 px-2 font-mono text-[11px] font-medium border-b-2 flex items-center gap-1 transition-colors ${
              activeTab === 'health'
                ? 'border-ochre-400 text-paper-100 bg-paper-900'
                : 'border-transparent text-paper-400 hover:text-paper-200'
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            <span>FITS</span>
          </button>
        </div>

        {/* Panel Expand / Shrink Toggle Button */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="p-1.5 rounded hover:bg-paper-800 text-paper-400 hover:text-paper-100 transition-colors"
          title={isExpanded ? 'Collapse panel width' : 'Expand chat & inspection panel'}
        >
          {isExpanded ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
        </button>
      </div>

      {/* Drawer Body Content */}
      <div className="flex-1 overflow-y-auto">
        {/* TAB 1: EXPANDABLE PEER CHAT */}
        {activeTab === 'community' && (
          <CommunityVerificationStream activeCandidateId={candidate?.id || null} />
        )}

        {/* TAB 2: CITIZEN SCIENCE CANDIDATE TRIAGE */}
        {activeTab === 'triage' && (
          <div className="p-4 space-y-4">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-paper-100 uppercase tracking-wider text-[11px]">
                  Object Inspection
                </span>
                <span className="text-[10px] font-mono text-ochre-400">
                  {candidate ? candidate.id : 'None Selected'}
                </span>
              </div>
              <p className="text-xs text-paper-400 leading-relaxed">
                Review candidate motion across SPHEREx observation epochs.
              </p>
            </div>

            {candidate ? (
              <div className="space-y-3">
                {candidate.isKnownCatalogMatch && (
                  <div className="p-3 rounded-lg bg-paper-950 border border-paper-800 space-y-1">
                    <div className="font-mono text-xs text-emerald-400 font-medium">
                      Matched: {candidate.matchedCatalog}
                    </div>
                    <div className="text-[10px] font-mono text-paper-400">
                      ID: {candidate.catalogId || 'N/A'}
                    </div>
                  </div>
                )}

                {/* 1-Click Classification Buttons */}
                <div>
                  <label className="text-[10px] font-mono text-paper-400 block mb-1.5 uppercase">
                    Classification Category
                  </label>
                  <div className="grid grid-cols-2 gap-1.5">
                    {[
                      { id: 'moving_object', label: 'Moving Object', desc: 'Proper motion' },
                      { id: 'transient', label: 'Transient', desc: 'Single-epoch flare' },
                      { id: 'already_known', label: 'Catalog Known', desc: 'Verified star' },
                      { id: 'artifact', label: 'Artifact', desc: 'Bad pixel / CR' },
                    ].map((item) => {
                      const isSelected = selectedClass === item.id;
                      return (
                        <button
                          key={item.id}
                          onClick={() => setSelectedClass(item.id as CandidateClassification)}
                          className={`p-2 rounded-lg border text-left transition-colors ${
                            isSelected
                              ? 'bg-paper-800 border-ochre-400 text-paper-100 font-medium'
                              : 'bg-paper-950 border-paper-800 text-paper-400 hover:text-paper-200'
                          }`}
                        >
                          <div className="font-mono text-xs">{item.label}</div>
                          <div className="text-[10px] text-paper-500 mt-0.5">{item.desc}</div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Confidence Level */}
                <div>
                  <label className="text-[10px] font-mono text-paper-400 block mb-1.5 uppercase">
                    Confidence Level
                  </label>
                  <div className="grid grid-cols-3 gap-1.5">
                    {(['low', 'medium', 'high'] as ConfidenceLevel[]).map((lvl) => (
                      <button
                        key={lvl}
                        onClick={() => setSelectedConfidence(lvl)}
                        className={`py-1.5 rounded-lg font-mono text-[10px] uppercase border transition-colors ${
                          selectedConfidence === lvl
                            ? 'bg-paper-800 border-ochre-400 text-ochre-300 font-semibold'
                            : 'bg-paper-950 border-paper-800 text-paper-400 hover:text-paper-200'
                        }`}
                      >
                        {lvl}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Notes Input */}
                <div>
                  <label className="text-[10px] font-mono text-paper-400 block mb-1 uppercase">
                    Verification Log
                  </label>
                  <textarea
                    rows={2}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Enter observation notes or PSF characteristics..."
                    className="w-full bg-paper-950 border border-paper-800 rounded-lg p-2 font-mono text-xs text-paper-100 focus:outline-none focus:border-ochre-400 resize-none"
                  />
                </div>

                {/* Save Confirmation */}
                <button
                  onClick={handleSaveTriage}
                  className="w-full py-2 bg-paper-100 hover:bg-white text-paper-950 rounded-lg font-mono text-xs font-semibold transition-all flex items-center justify-center gap-2 shadow-sm"
                >
                  <CheckCircle className="w-3.5 h-3.5 text-ochre-600" />
                  <span>{isSaved ? 'Classification Recorded ✓' : 'Save Classification'}</span>
                </button>

                {/* View Full Candidate Discovery Report */}
                {onOpenDiscoveryReport && (
                  <button
                    onClick={onOpenDiscoveryReport}
                    className="w-full py-2 bg-paper-800 hover:bg-paper-750 border border-ochre-400 text-ochre-300 rounded-lg font-mono text-xs font-semibold transition-all flex items-center justify-center gap-2 shadow-sm"
                    title="Open full scientific summary with 102-band spectrum plot, Gaia/WISE cross-check, and JSON export"
                  >
                    <FileText className="w-3.5 h-3.5 text-ochre-400" />
                    <span>View Candidate Discovery Report →</span>
                  </button>
                )}

                {/* Clear Future Feature Badges */}
                <div className="pt-2 border-t border-paper-800 space-y-1.5">
                  <span className="text-[10px] font-mono text-paper-500 uppercase">
                    Automated Processing Pipeline:
                  </span>
                  <div className="flex gap-2">
                    <button
                      disabled
                      className="flex-1 py-1 px-2 rounded bg-paper-950 border border-paper-800/60 text-[10px] font-mono text-paper-500 cursor-not-allowed text-center"
                      title="This feature will run on Paul's backend server in v1.1"
                    >
                      <span>ML Classifier</span>
                      <span className="block text-[8px] text-ochre-500/80">(Backend Pending)</span>
                    </button>
                    <button
                      disabled
                      className="flex-1 py-1 px-2 rounded bg-paper-950 border border-paper-800/60 text-[10px] font-mono text-paper-500 cursor-not-allowed text-center"
                      title="Direct submission to NASA IRSA archive planned for v1.1"
                    >
                      <span>Submit to IRSA</span>
                      <span className="block text-[8px] text-ochre-500/80">(Future API)</span>
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="p-6 rounded-xl border border-dashed border-paper-800 text-center space-y-2">
                <HelpCircle className="w-8 h-8 text-paper-600 mx-auto" />
                <div className="font-mono text-xs text-paper-300">No Target Selected</div>
                <p className="text-[11px] text-paper-500 max-w-xs mx-auto">
                  Click any object in the celestial starfield to inspect its multi-epoch motion vectors.
                </p>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: 102-BAND SPECTRUM */}
        {activeTab === 'spectrum' && (
          <div className="p-4 space-y-3">
            <span className="font-semibold text-paper-100 uppercase tracking-wider text-xs block">
              102-Band Spectrophotometry
            </span>
            <SpectrumPlot
              data={spectrumData}
              objectLabel={candidate?.matchedCatalog || candidate?.id || "Target"}
            />
            <div className="p-3 rounded-lg bg-paper-950 border border-paper-800 text-xs text-paper-400 leading-relaxed font-sans">
              <strong>Absorption Diagnosis:</strong> Distinct depression at 3.05 µm (H₂O) and 4.27 µm (CO₂) features typical of cold sub-stellar dwarf atmospheres.
            </div>
          </div>
        )}

        {/* TAB 4: DATA HEALTH TELEMETRY */}
        {activeTab === 'health' && (
          <div className="p-4 space-y-3">
            <span className="font-semibold text-paper-100 uppercase tracking-wider text-xs block">
              FITS Frame Telemetry
            </span>
            <div className="space-y-1.5">
              {frames.map((f, idx) => (
                <div
                  key={f.frameId}
                  onClick={() => f.isAvailable && onSelectFrame(idx)}
                  className={`p-2.5 rounded-lg border text-xs font-mono transition-colors ${
                    !f.isAvailable
                      ? 'bg-rose-950/20 border-rose-900/50 text-rose-300'
                      : idx === activeFrameIndex
                      ? 'bg-paper-800 border-ochre-400 text-paper-100'
                      : 'bg-paper-950 border-paper-800 text-paper-400 hover:text-paper-200 cursor-pointer'
                  }`}
                >
                  <div className="flex justify-between font-medium">
                    <span>Epoch {f.epochIndex + 1} ({f.observationDate.split('T')[0]})</span>
                    <span>Band {f.detectorArray}</span>
                  </div>
                  <div className="text-[11px] text-paper-500 mt-1">
                    Flagged: {f.flaggedPixelPercentage}% • CR: {f.cosmicRayHits} • SNR: {f.headerMetadata.snrEstimated}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
