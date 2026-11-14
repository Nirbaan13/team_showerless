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
import { MLDetectionsPanel } from './MLDetectionsPanel';
import {
  CheckCircle,
  Radio,
  HelpCircle,
  Maximize2,
  Minimize2,
  FileText,
  MessageSquare,
  Cpu,
} from 'lucide-react';

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
}

export const RightDrawer: React.FC<RightDrawerProps> = ({
  candidates,
  selectedCandidateId,
  onSelectCandidate,
  candidate,
  spectrumData,
  onUpdateCandidateClassification,
  onOpenDiscoveryReport,
  isScientistMode = false,
}) => {
  const [activeTab, setActiveTab] = useState<'ai' | 'triage' | 'chat' | 'spectrum'>('ai');
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
          />
        )}

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

            {/* 102 bands = 6 detectors x 17 channels (matches IRSA cutouts grouped per detector D1–D6) */}
            <div className="grid grid-cols-6 gap-1 text-[10px] font-mono text-center">
              {[
                ['D1', '0.75–1.1'],
                ['D2', '1.1–1.6'],
                ['D3', '1.6–2.4'],
                ['D4', '2.4–3.8'],
                ['D5', '3.8–4.4'],
                ['D6', '4.4–5.0'],
              ].map(([d, r]) => (
                <div key={d} className="p-1 rounded bg-paper-950 border border-paper-800">
                  <div className="text-emerald-400 font-bold">{d}</div>
                  {isScientistMode && <div className="text-paper-500">{r}µm</div>}
                </div>
              ))}
            </div>

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
                </div>
              </details>
            )}
          </div>
        )}

      </div>
    </aside>
  );
};
