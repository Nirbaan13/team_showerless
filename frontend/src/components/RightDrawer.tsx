import React, { useState, useEffect, useRef } from 'react';
import type {
  SpherexEpochFrame,
  CandidateObject,
  CandidateClassification,
  ConfidenceLevel,
  SpectralDataPoint,
} from '../types/spherex';
import { SpectrumPlot } from './SpectrumPlot';
import { MLDetectionsPanel } from './MLDetectionsPanel';
import { CommunityVerificationStream } from './CommunityVerificationStream';
import {
  CheckCircle,
  Radio,
  HelpCircle,
  Maximize2,
  Minimize2,
  FileText,
  MessageSquare,
  Cpu,
  Sparkles,
  ShieldAlert,
  Compass,
  Info,
} from 'lucide-react';

interface ClassificationGuideItem {
  id: CandidateClassification;
  name: string;
  badge: string;
  badgeBg: string;
  badgeText: string;
  criteria: string;
  distinction: string;
}

const CLASSIFICATION_GUIDE: Record<string, ClassificationGuideItem> = {
  transient: {
    id: 'transient',
    name: 'Transient (Flare / Supernova)',
    badge: 'Sudden Burst',
    badgeBg: 'rgba(245, 158, 11, 0.2)',
    badgeText: '#f59e0b',
    criteria: 'Sudden flux spike in 1–2 epochs + fixed sky coordinates + true multi-pixel optical PSF.',
    distinction: 'Optical PSF spread distinguishes it from sharp 1px cosmic rays. Fixed position separates it from moving bodies.',
  },
  artifact: {
    id: 'artifact',
    name: 'Artifact (Cosmic Ray / Glitch)',
    badge: 'Detector Noise',
    badgeBg: 'rgba(244, 63, 94, 0.2)',
    badgeText: '#f43f5e',
    criteria: 'Sharp 1-pixel spike or line streak in only 1 exposure with no physical optical beam spread.',
    distinction: 'Lacks multi-pixel optical PSF wings. Disappears completely in all other telescope pointings.',
  },
  moving_object: {
    id: 'moving_object',
    name: 'Moving Object (Asteroid / Comet)',
    badge: 'Linear Track',
    badgeBg: 'rgba(16, 185, 129, 0.2)',
    badgeText: '#10b981',
    criteria: 'Smooth positional track across epochs with steady optical PSF and predictable velocity vector.',
    distinction: 'Centroid shifts smoothly each epoch (unlike stationary transients that stay at the same pixel).',
  },
  already_known: {
    id: 'already_known',
    name: 'Known Catalog Star',
    badge: 'Catalog Baseline',
    badgeBg: 'rgba(148, 163, 184, 0.2)',
    badgeText: '#94a3b8',
    criteria: 'Stationary multi-epoch source matching Gaia DR3 or AllWISE within <1.5″.',
    distinction: 'Stable baseline brightness catalogued in historical sky surveys; no unexpected outbursts.',
  },
};

interface RightDrawerProps {
  frames?: SpherexEpochFrame[];
  activeFrameIndex?: number;
  onSelectFrame?: (index: number) => void;
  candidates: CandidateObject[];
  selectedCandidateId: string | null;
  onSelectCandidate: (id: string) => void;
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
  ra?: number;
  dec?: number;
  fov?: import('../types/spherex').FOVOption;
  selectedArray?: import('../types/spherex').DetectorArrayId | 'all';
  subtractionMode?: import('../types/spherex').SubtractionMode;
  controlledTab?: 'ai' | 'triage' | 'chat' | 'spectrum' | null;
  onTabChange?: (tab: 'ai' | 'triage' | 'chat' | 'spectrum') => void;
  mlAnalysisStatus?: import('../types/spherex').MLAnalysisStatus;
  currentPresetId?: string | null;
  className?: string;
}

export const RightDrawer: React.FC<RightDrawerProps> = ({
  frames: _frames,
  activeFrameIndex = 0,
  onSelectFrame: _onSelectFrame,
  candidates,
  selectedCandidateId,
  onSelectCandidate,
  candidate,
  spectrumData,
  onUpdateCandidateClassification,
  onOpenDiscoveryReport,
  isScientistMode = false,
  ra,
  dec,
  fov,
  selectedArray,
  subtractionMode,
  controlledTab,
  onTabChange,
  mlAnalysisStatus,
  currentPresetId = null,
  className = '',
}) => {
  const [internalTab, setInternalTab] = useState<'ai' | 'triage' | 'chat' | 'spectrum'>('ai');
  const activeTab = controlledTab ?? internalTab;
  const setActiveTab = (tab: 'ai' | 'triage' | 'chat' | 'spectrum') => {
    setInternalTab(tab);
    if (onTabChange) onTabChange(tab);
  };
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
  const [hoveredClassId, setHoveredClassId] = useState<string | null>(null);
  const currentGuide =
    CLASSIFICATION_GUIDE[
      hoveredClassId || (selectedClass !== 'unreviewed' ? selectedClass : 'transient')
    ] || CLASSIFICATION_GUIDE.transient;

  const startXRef = useRef<number>(0);
  const startWidthRef = useRef<number>(360);

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
      style={typeof window !== 'undefined' && window.innerWidth < 1024 ? undefined : { width: `${width}px` }}
      className={`relative bg-paper-900 border-l border-paper-800 flex flex-col h-full lg:h-[calc(100vh-3rem)] text-xs select-none z-20 shrink-0 transition-[width] duration-75 ${className}`}
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
            onClick={() => setActiveTab('ai')}
            className={`py-2 px-3 font-mono text-[11px] font-medium border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer ${
              activeTab === 'ai'
                ? 'border-emerald-400 text-paper-100 bg-paper-900 font-bold'
                : 'border-transparent text-paper-400 hover:text-paper-200'
            }`}
          >
            <Cpu className="w-3.5 h-3.5 text-emerald-400" />
            <span>AI</span>
          </button>

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
            className={`py-2 px-2.5 font-mono text-[11px] font-medium border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer ${
              activeTab === 'spectrum'
                ? 'border-emerald-400 text-paper-100 bg-paper-900 font-bold'
                : 'border-transparent text-paper-400 hover:text-paper-200'
            }`}
          >
            <Radio className="w-3.5 h-3.5 text-emerald-400" />
            <span>Spectral Analysis</span>
          </button>

        </div>

        {/* Quick Expand/Shrink Button + Drag hint */}
        <div className="flex items-center gap-1">
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
        {/* TAB 0: AI-RANKED DETECTIONS (main feature) */}
        {activeTab === 'ai' && (
          <MLDetectionsPanel
            candidates={candidates}
            selectedCandidateId={selectedCandidateId}
            onSelectCandidate={(id) => {
              onSelectCandidate(id);
            }}
            isScientistMode={isScientistMode}
            mlAnalysisStatus={mlAnalysisStatus}
            ra={ra}
            dec={dec}
          />
        )}

        {/* TAB 1: CANDIDATE TRIAGE & VERIFICATION */}
        {activeTab === 'triage' && (
          <div className="p-4 space-y-4">
            <div className="p-2.5 rounded-xl bg-emerald-950/30 border-2 border-emerald-400/60 flex items-center justify-between gap-2">
              <div className="min-w-0">
                <span className="font-mono text-[9px] text-emerald-400 uppercase tracking-wider font-bold block">
                  ★ Selected Object on Sky
                </span>
                <span className="text-xs font-mono text-white font-bold truncate block">
                  {candidate
                    ? `#${candidate.mlRank} · ${
                        candidate.validationData?.objectName ||
                        candidate.catalogId ||
                        candidate.id
                      }`
                    : 'None Selected'}
                </span>
              </div>
              {candidate && (
                <span className="text-[9px] font-mono font-bold text-gray-950 bg-emerald-400 px-2 py-0.5 rounded border border-black shrink-0">
                  ACTIVE
                </span>
              )}
            </div>

            {candidate ? (
              <div className="space-y-3.5">
                {/* Known Catalog Match Badge */}
                {candidate.isKnownCatalogMatch && (
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
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-[10px] font-mono text-paper-400 uppercase font-semibold">
                      Volunteer Classification
                    </label>
                    <span className="text-[9px] font-mono text-paper-500">
                      Hover for TiH Guide
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    {[
                      { id: 'moving_object', label: 'Moving Object', desc: 'Consistent track' },
                      { id: 'transient', label: 'Transient', desc: 'Single-epoch burst' },
                      { id: 'already_known', label: 'Known Catalog', desc: 'Matches Gaia/WISE' },
                      { id: 'artifact', label: 'Artifact', desc: 'Bad pixel / CR' },
                    ].map((item) => {
                      const isSelected = selectedClass === item.id;
                      const isHovered = hoveredClassId === item.id;
                      return (
                        <button
                          key={item.id}
                          onClick={() => setSelectedClass(item.id as CandidateClassification)}
                          onMouseEnter={() => setHoveredClassId(item.id)}
                          onMouseLeave={() => setHoveredClassId(null)}
                          className={`btn-tactile-sm p-2 rounded-lg border-2 border-black text-left transition-all cursor-pointer ${
                            isSelected
                              ? 'bg-emerald-400 text-gray-950 font-bold'
                              : isHovered
                              ? 'bg-paper-800 text-emerald-300'
                              : 'bg-paper-950 text-paper-400 hover:text-paper-200'
                          }`}
                        >
                          <div className="font-mono text-[11px]">{item.label}</div>
                        </button>
                      );
                    })}
                  </div>

                  {/* TiH Classification Helper: Volunteer Mode Only & Decluttered */}
                  {!isScientistMode && (
                    <div className="mt-2 p-2.5 rounded-xl bg-paper-950 border border-paper-800 space-y-1.5 anim-fall text-[10px]">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          {currentGuide.id === 'transient' && <Sparkles className="w-3.5 h-3.5 text-amber-400" />}
                          {currentGuide.id === 'artifact' && <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />}
                          {currentGuide.id === 'moving_object' && <Compass className="w-3.5 h-3.5 text-emerald-400" />}
                          {currentGuide.id === 'already_known' && <Info className="w-3.5 h-3.5 text-slate-400" />}
                          <span className="font-mono font-bold text-paper-100">{currentGuide.name}</span>
                        </div>
                        <span
                          style={{ backgroundColor: currentGuide.badgeBg, color: currentGuide.badgeText }}
                          className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded border border-black/40"
                        >
                          {currentGuide.badge}
                        </span>
                      </div>

                      <div className="text-paper-300 flex items-start gap-1">
                        <span className="text-emerald-400 font-bold shrink-0">✓ Key:</span>
                        <span>{currentGuide.criteria}</span>
                      </div>

                      <div className="text-paper-400 flex items-start gap-1 pt-1 border-t border-paper-850">
                        <span className="text-rose-400 font-bold shrink-0">✕ Distinguish:</span>
                        <span>{currentGuide.distinction}</span>
                      </div>
                    </div>
                  )}
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

        {/* TAB 2: CANDIDATE VERIFICATION DISCUSSION & NOTES THREAD */}
        {activeTab === 'chat' && (
          <CommunityVerificationStream
            key={candidate?.id || selectedCandidateId || 'none'}
            candidate={candidate}
            activeCandidateId={candidate?.id || selectedCandidateId || null}
            currentPresetId={currentPresetId}
            ra={ra}
            dec={dec}
            fov={fov}
            selectedArray={selectedArray}
            activeFrameIndex={activeFrameIndex}
            subtractionMode={subtractionMode}
          />
        )}

        {/* TAB 3: 102-BAND SPECTRAL ANALYSIS */}
        {activeTab === 'spectrum' && (
          <div className="p-3.5 space-y-3">
            <SpectrumPlot
              data={spectrumData}
              objectLabel={
                candidate?.validationData?.objectName ||
                candidate?.matchedCatalog ||
                candidate?.catalogId ||
                candidate?.id ||
                "Target"
              }
              ra={ra}
              dec={dec}
              candidateId={candidate?.id || selectedCandidateId}
              isScientistMode={isScientistMode}
            />

            {isScientistMode && (
              <details className="p-3 bg-paper-950 border border-emerald-500/40 rounded-lg font-mono text-[10px] text-emerald-300">
                <summary className="cursor-pointer font-bold text-emerald-400 text-[11px]">FITS header (Primary HDU)</summary>
                <div className="mt-2 space-y-1">
                  <div>BITPIX  = -32 / IEEE 32-bit float</div>
                  <div>NAXIS1  = 2048 / NAXIS2 = 2048</div>
                  <div>BUNIT   = 'MJy/sr' / Flux units</div>
                  <div>RADESYS = 'ICRS' / EQUINOX = 2000.0</div>
                  <div>CD1_1   = -1.722222E-03 / deg/px</div>
                  <div>CD2_2   =  1.722222E-03 / deg/px</div>
                  <div>WCS-WAVE= 'Secondary HDU key W' / 102 bands</div>
                </div>
              </details>
            )}
          </div>
        )}

      </div>
    </aside>
  );
};
