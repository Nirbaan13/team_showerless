import React, { useState, useEffect, useRef } from 'react';
import type {
  SpherexEpochFrame,
  CandidateObject,
  CandidateClassification,
  ConfidenceLevel,
  SpectralDataPoint,
} from '../types/spherex';
import { SpectrumPlot } from './SpectrumPlot';
import { CommunityVerificationStream } from './CommunityVerificationStream';
import {
  CheckCircle,
  Radio,
  Activity,
  HelpCircle,
  Maximize2,
  Minimize2,
  FileText,
  ExternalLink,
  Award,
  GripVertical,
  MessageSquare,
} from 'lucide-react';

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
  onOpenDiscoveryReport?: () => void;
  isScientistMode?: boolean;
}

export const RightDrawer: React.FC<RightDrawerProps> = ({
  frames,
  activeFrameIndex,
  onSelectFrame,
  candidate,
  spectrumData,
  onUpdateCandidateClassification,
  onOpenDiscoveryReport,
  isScientistMode = false,
}) => {
  const [activeTab, setActiveTab] = useState<'triage' | 'chat' | 'spectrum' | 'health'>('triage');
  const [width, setWidth] = useState<number>(360);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [notes, setNotes] = useState(candidate?.volunteerNotes || '');
  const [selectedClass, setSelectedClass] = useState<CandidateClassification>(
    candidate?.classification || 'unreviewed'
  );
  const [selectedConfidence, setSelectedConfidence] = useState<ConfidenceLevel>(
    candidate?.confidence || 'medium'
  );
  const [isSaved, setIsSaved] = useState(false);

  const startXRef = useRef<number>(0);
  const startWidthRef = useRef<number>(360);

  // In Scientist Mode, prioritize the Spectrophotometry analysis tab
  useEffect(() => {
    if (isScientistMode) {
      setActiveTab('spectrum');
    }
  }, [isScientistMode]);

  useEffect(() => {
    if (candidate) {
      setNotes(candidate.volunteerNotes);
      setSelectedClass(candidate.classification);
      setSelectedConfidence(candidate.confidence);
      setIsSaved(false);
    }
  }, [candidate]);

  // Handle Drag-to-Resize on Left Border
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    startXRef.current = e.clientX;
    startWidthRef.current = width;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const delta = startXRef.current - moveEvent.clientX;
      const minW = 280;
      const maxW = Math.min(760, window.innerWidth * 0.65);
      const newWidth = Math.max(minW, Math.min(maxW, startWidthRef.current + delta));
      setWidth(newWidth);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };

    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  const handleToggleExpand = () => {
    setWidth((prev) => (prev > 420 ? 340 : 540));
  };

  const handleSaveTriage = () => {
    if (!candidate) return;
    onUpdateCandidateClassification(candidate.id, selectedClass, selectedConfidence, notes);
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2000);
  };

  return (
    <aside
      style={{ width: `${width}px` }}
      className="relative bg-paper-900 border-l border-paper-800 flex flex-col h-[calc(100vh-3rem)] text-xs select-none z-20 shrink-0 transition-[width] duration-75"
    >
      {/* Draggable Left Resize Handle */}
      <div
        onMouseDown={handleMouseDown}
        className={`absolute top-0 bottom-0 -left-1.5 w-3 cursor-col-resize z-40 flex items-center justify-center group ${
          isDragging ? 'bg-emerald-400/20' : 'hover:bg-emerald-400/20'
        } transition-colors`}
        title="Drag left/right to resize panel width freely"
      >
        <div
          className={`w-1 h-8 rounded-full ${
            isDragging ? 'bg-emerald-400' : 'bg-paper-700 group-hover:bg-emerald-400'
          } transition-colors`}
        />
      </div>

      {/* Drawer Header & Tabs */}
      <div className="flex border-b border-paper-800 bg-paper-950 items-center justify-between px-2">
        <div className="flex space-x-1">
          <button
            onClick={() => setActiveTab('triage')}
            className={`py-2 px-3 font-mono text-[11px] font-medium border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer ${
              activeTab === 'triage'
                ? 'border-emerald-400 text-paper-100 bg-paper-900 font-bold'
                : 'border-transparent text-paper-400 hover:text-paper-200'
            }`}
          >
            <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
            <span>Triage</span>
          </button>

          <button
            onClick={() => setActiveTab('chat')}
            className={`py-2 px-2.5 font-mono text-[11px] font-medium border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer ${
              activeTab === 'chat'
                ? 'border-emerald-400 text-paper-100 bg-paper-900 font-bold'
                : 'border-transparent text-paper-400 hover:text-paper-200'
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5 text-emerald-400" />
            <span>Chat</span>
          </button>

          <button
            onClick={() => setActiveTab('spectrum')}
            className={`py-2 px-3 font-mono text-[11px] font-medium border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer ${
              activeTab === 'spectrum'
                ? 'border-emerald-400 text-paper-100 bg-paper-900 font-bold'
                : 'border-transparent text-paper-400 hover:text-paper-200'
            }`}
          >
            <Radio className={`w-3.5 h-3.5 ${isScientistMode ? 'text-emerald-400' : ''}`} />
            <span>102 Bands</span>
            {isScientistMode && (
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            )}
          </button>

          <button
            onClick={() => setActiveTab('health')}
            className={`py-2 px-3 font-mono text-[11px] font-medium border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer ${
              activeTab === 'health'
                ? 'border-emerald-400 text-paper-100 bg-paper-900 font-bold'
                : 'border-transparent text-paper-400 hover:text-paper-200'
            }`}
          >
            <Activity className={`w-3.5 h-3.5 ${isScientistMode ? 'text-emerald-400' : ''}`} />
            <span>FITS</span>
            {isScientistMode && (
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            )}
          </button>
        </div>

        {/* Quick Expand/Shrink Button + Drag hint */}
        <div className="flex items-center gap-1">
          <span className="text-[10px] font-mono text-paper-600 mr-1 hidden sm:inline flex items-center gap-0.5">
            <GripVertical className="w-3 h-3" />
            {width}px
          </span>
          <button
            onClick={handleToggleExpand}
            className="p-1.5 rounded hover:bg-paper-800 text-paper-400 hover:text-paper-100 transition-colors cursor-pointer"
            title={width > 420 ? 'Reset panel width (340px)' : 'Expand panel width (540px)'}
          >
            {width > 420 ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Drawer Body Content */}
      <div className="flex-1 overflow-y-auto">
        {/* TAB 1: CANDIDATE TRIAGE & VERIFICATION */}
        {activeTab === 'triage' && (
          <div className="p-4 space-y-4">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-paper-100 uppercase tracking-wider text-[11px]">
                  Object Inspection
                </span>
                <span className="text-[11px] font-mono text-emerald-400 font-bold">
                  {candidate ? candidate.id : 'None Selected'}
                </span>
              </div>
              <p className="text-xs text-paper-400 leading-relaxed">
                Review candidate motion across SPHEREx observation epochs and record your verification.
              </p>
            </div>

            {candidate ? (
              <div className="space-y-3.5">
                {/* 3I/ATLAS Real Interim Detection Callout */}
                {candidate.validationData && (
                  <div className="p-3 rounded-xl bg-emerald-950/40 border-2 border-emerald-500/60 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-[11px] text-emerald-300 flex items-center gap-1.5">
                        <Award className="w-4 h-4 text-emerald-400" />
                        Real SPHEREx Detection
                      </span>
                      <span className="text-[9px] font-mono bg-emerald-900/60 text-emerald-200 px-1.5 py-0.5 rounded border border-emerald-700">
                        {candidate.validationData.exposuresCount} Real Exposures
                      </span>
                    </div>

                    <p className="text-[11px] text-paper-300 leading-relaxed font-sans">
                      Detector successfully identified <strong className="text-white">3I/ATLAS</strong> across all {candidate.validationData.exposuresCount} real SPHEREx frames within <strong className="text-emerald-300">{candidate.validationData.maxOffsetPx} pixels</strong> of published ephemeris.
                    </p>

                    <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono pt-1 border-t border-emerald-800/60">
                      <div className="bg-paper-950/70 p-1.5 rounded border border-emerald-900/60">
                        <span className="text-paper-400 block text-[9px]">Baseline Heuristic</span>
                        <span className="text-emerald-400 font-bold">Rank 1st of 25</span>
                      </div>
                      <div className="bg-paper-950/70 p-1.5 rounded border border-emerald-900/60">
                        <span className="text-paper-400 block text-[9px]">Random Forest ML</span>
                        <span className="text-emerald-400 font-bold">Rank 2nd of 25</span>
                      </div>
                    </div>

                    <div className="text-[9px] text-paper-400 flex items-center justify-between pt-0.5 font-mono">
                      <span>DOI: {candidate.validationData.datasetDoi}</span>
                      <a
                        href={candidate.validationData.sourceUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="text-emerald-400 hover:text-emerald-300 inline-flex items-center gap-1 underline"
                      >
                        NASA IRSA <ExternalLink className="w-2.5 h-2.5" />
                      </a>
                    </div>
                  </div>
                )}

                {/* Known Catalog Match Badge */}
                {candidate.isKnownCatalogMatch && !candidate.validationData && (
                  <div className="p-2.5 rounded-lg bg-paper-950 border border-paper-800 space-y-1">
                    <span className="font-mono text-[10px] text-paper-400 block uppercase">
                      Known Catalog Cross-Match
                    </span>
                    <div className="flex items-center justify-between text-xs font-mono text-paper-200">
                      <span className="text-emerald-400 font-semibold">{candidate.matchedCatalog}</span>
                      <span className="text-paper-400">{candidate.catalogId}</span>
                    </div>
                  </div>
                )}

                {/* Candidate Classification */}
                <div>
                  <label className="text-[10px] font-mono text-paper-400 block mb-1.5 uppercase font-semibold">
                    Volunteer Classification
                  </label>
                  <div className="grid grid-cols-2 gap-1.5">
                    {[
                      { id: 'moving_object', label: 'Moving Object', desc: 'Consistent track' },
                      { id: 'transient', label: 'Transient', desc: 'Single-epoch burst' },
                      { id: 'already_known', label: 'Known Catalog', desc: 'Matches Gaia/WISE' },
                      { id: 'artifact', label: 'Artifact', desc: 'Bad pixel / CR' },
                    ].map((item) => {
                      const isSelected = selectedClass === item.id;
                      return (
                        <button
                          key={item.id}
                          onClick={() => setSelectedClass(item.id as CandidateClassification)}
                          className={`btn-tactile-sm p-2 rounded-lg border-2 border-black text-left transition-all cursor-pointer ${
                            isSelected
                              ? 'bg-emerald-400 text-gray-950 font-bold'
                              : 'bg-paper-950 text-paper-400 hover:text-paper-200'
                          }`}
                        >
                          <div className="font-mono text-[11px]">{item.label}</div>
                          <div className={`text-[9px] mt-0.5 ${isSelected ? 'text-gray-900' : 'text-paper-500'}`}>
                            {item.desc}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Confidence Level */}
                <div>
                  <label className="text-[10px] font-mono text-paper-400 block mb-1.5 uppercase font-semibold">
                    Confidence Level
                  </label>
                  <div className="grid grid-cols-3 gap-1.5">
                    {(['low', 'medium', 'high'] as ConfidenceLevel[]).map((lvl) => (
                      <button
                        key={lvl}
                        onClick={() => setSelectedConfidence(lvl)}
                        className={`btn-tactile-sm py-1.5 rounded-lg font-mono text-[10px] uppercase border-2 border-black transition-all cursor-pointer ${
                          selectedConfidence === lvl
                            ? 'bg-emerald-400 text-gray-950 font-bold'
                            : 'bg-paper-950 text-paper-400 hover:text-paper-200'
                        }`}
                      >
                        {lvl}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Notes Input */}
                <div>
                  <label className="text-[10px] font-mono text-paper-400 block mb-1 uppercase font-semibold">
                    Observation Notes
                  </label>
                  <textarea
                    rows={2}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Enter observation notes or PSF characteristics..."
                    className="w-full bg-paper-950 border border-paper-800 rounded-lg p-2 font-mono text-xs text-paper-100 focus:outline-none focus:border-emerald-400 resize-none"
                  />
                </div>

                {/* Save Confirmation */}
                <button
                  onClick={handleSaveTriage}
                  className="btn-tactile w-full py-2.5 bg-emerald-400 hover:bg-emerald-300 text-gray-950 rounded-xl font-mono text-xs font-bold border-2 border-black flex items-center justify-center gap-2 cursor-pointer"
                >
                  <CheckCircle className="w-3.5 h-3.5 stroke-[2.5]" />
                  <span>{isSaved ? 'Classification Recorded ✓' : 'Save Classification'}</span>
                </button>

                {/* View Full Candidate Discovery Report */}
                {onOpenDiscoveryReport && (
                  <button
                    onClick={onOpenDiscoveryReport}
                    className="btn-tactile w-full py-2.5 bg-paper-800 hover:bg-paper-750 border-2 border-black text-emerald-300 rounded-xl font-mono text-xs font-bold flex items-center justify-center gap-2 cursor-pointer"
                    title="Open full scientific summary with 102-band spectrum plot, Gaia/WISE cross-check, and JSON export"
                  >
                    <FileText className="w-3.5 h-3.5 text-emerald-400" />
                    <span>View Candidate Discovery Report →</span>
                  </button>
                )}
              </div>
            ) : (
              <div className="p-8 rounded-xl border border-dashed border-paper-800 text-center space-y-2.5">
                <HelpCircle className="w-8 h-8 text-paper-600 mx-auto" />
                <div className="font-mono text-xs text-paper-300 font-semibold">No Target Selected</div>
                <p className="text-[11px] text-paper-500 max-w-xs mx-auto leading-relaxed">
                  Click any object in the celestial starfield to inspect its multi-epoch motion vectors.
                </p>
              </div>
            )}
          </div>
        )}

        {/* TAB 2: VERIFICATION NOTES & COMMUNITY CHAT */}
        {activeTab === 'chat' && (
          <CommunityVerificationStream activeCandidateId={candidate?.id || null} />
        )}

        {/* TAB 3: 102-BAND SPECTROPHOTOMETRY */}
        {activeTab === 'spectrum' && (
          <div className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-paper-100 uppercase tracking-wider text-xs block">
                102-Band Spectrophotometry
              </span>
              <span className="text-[10px] font-mono text-emerald-400 bg-paper-950 px-2 py-0.5 rounded border border-paper-800">
                0.75 – 5.00 µm
              </span>
            </div>

            <SpectrumPlot
              data={spectrumData}
              objectLabel={candidate?.matchedCatalog || candidate?.id || "Target"}
            />

            <div className="p-3 rounded-lg bg-paper-950 border border-paper-800 text-xs text-paper-400 leading-relaxed font-sans space-y-1">
              <div className="font-mono text-[11px] text-paper-200 font-semibold">
                Molecular Absorption Diagnostics:
              </div>
              <p>
                Depressions at 3.05 µm (H₂O ice) and 4.27 µm (CO₂) match cold sub-stellar dwarf and cometary coma spectra.
              </p>
            </div>
          </div>
        )}

        {/* TAB 3: DATA HEALTH & FITS TELEMETRY */}
        {activeTab === 'health' && (
          <div className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-paper-100 uppercase tracking-wider text-xs block">
                FITS Frame Telemetry
              </span>
              <span className="text-[10px] font-mono text-emerald-400 bg-paper-950 px-2 py-0.5 rounded border border-paper-800">
                {isScientistMode ? 'Calibrated L2/L3' : 'Raw Headers'}
              </span>
            </div>

            {/* In Scientist Mode: Primary HDU FITS Header Card */}
            {isScientistMode && (
              <div className="p-3 bg-paper-950 border border-emerald-500/40 rounded-lg font-mono text-[10px] space-y-1 text-emerald-300">
                <div className="font-bold text-emerald-400 text-[11px] border-b border-paper-800 pb-1 flex justify-between">
                  <span>Primary HDU Header</span>
                  <span className="text-paper-400 font-normal">Level 2 Calibrated</span>
                </div>
                <div>SIMPLE  =                    T / Standard FITS</div>
                <div>BITPIX  =                  -32 / IEEE 32-bit float</div>
                <div>NAXIS   =                    2 / 2D image matrix</div>
                <div>NAXIS1  =                 2048 / Fast axis px</div>
                <div>NAXIS2  =                 2048 / Slow axis px</div>
                <div>BUNIT   = 'MJy/sr  '           / Flux units</div>
                <div>RADESYS = 'ICRS    '           / Astrometric ref</div>
                <div>EQUINOX =               2000.0 / Epoch</div>
                <div>CD1_1   =        -1.722222E-03 / CD matrix deg/px</div>
                <div>CD2_2   =         1.722222E-03 / CD matrix deg/px</div>
              </div>
            )}

            <div className="space-y-1.5">
              {frames.map((f, idx) => (
                <div
                  key={f.frameId}
                  onClick={() => f.isAvailable && onSelectFrame(idx)}
                  className={`p-2.5 rounded-lg border text-xs font-mono transition-colors ${
                    !f.isAvailable
                      ? 'bg-rose-950/20 border-rose-900/50 text-rose-300'
                      : idx === activeFrameIndex
                      ? 'bg-paper-800 border-emerald-400 text-paper-100'
                      : 'bg-paper-950 border-paper-800 text-paper-400 hover:text-paper-200 cursor-pointer'
                  }`}
                >
                  <div className="flex justify-between font-medium">
                    <span>Epoch {f.epochIndex + 1} ({f.observationDate.split('T')[0]})</span>
                    <span className="text-emerald-400">Band {f.detectorArray}</span>
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
