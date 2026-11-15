import React, { useState, useEffect, useRef } from 'react';
import type {
  SpherexEpochFrame,
  CandidateObject,
  CandidateClassification,
  ConfidenceLevel,
  SpectralDataPoint,
  VerificationComment,
} from '../types/spherex';
import { SpectrumPlot } from './SpectrumPlot';
import { MLDetectionsPanel } from './MLDetectionsPanel';
import { CommunityVerificationStream } from './CommunityVerificationStream';
import { ExternalSubmissionModal } from './ExternalSubmissionModal';
import type { CandidateRecord } from '../types/catalogue';
import { fetchCandidateById } from '../services/catalogueService';
import { SEEDED_VERIFICATION_DISCUSSIONS } from '../services/mockVerificationData';
import {
  CheckCircle,
  Radio,
  HelpCircle,
  Maximize2,
  Minimize2,
  MessageSquare,
  Cpu,
  Sparkles,
  ShieldAlert,
  Compass,
  Info,
  Edit3,
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

function hasExistingThread(candidateId: string | null | undefined): boolean {
  if (!candidateId) return false;
  try {
    const saved = localStorage.getItem('spherex_community_comments');
    if (saved) {
      const parsed = JSON.parse(saved);
      if (Array.isArray(parsed) && parsed.some((c: any) => c.candidateId === candidateId || c.setting?.candidateId === candidateId)) {
        return true;
      }
    }
  } catch {}
  return SEEDED_VERIFICATION_DISCUSSIONS.some(c => c.candidateId === candidateId || c.setting?.candidateId === candidateId);
}

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
  onOpenFeed?: () => void;
  onOpenCatalogue?: (candidateId?: string) => void;
  isScientistMode?: boolean;
  ra?: number;
  dec?: number;
  fov?: import('../types/spherex').FOVOption;
  selectedArray?: import('../types/spherex').DetectorArrayId | 'all';
  subtractionMode?: import('../types/spherex').SubtractionMode;
  controlledTab?: 'ai' | 'triage' | 'chat' | 'spectrum' | null;
  onTabChange?: (tab: 'ai' | 'chat' | 'spectrum') => void;
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
  onOpenDiscoveryReport: _onOpenDiscoveryReport,
  onOpenFeed: _onOpenFeed,
  onOpenCatalogue,
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
  const [internalTab, setInternalTab] = useState<'ai' | 'chat' | 'spectrum'>('ai');
  const [chatViewMode, setChatViewMode] = useState<'triage' | 'thread'>('thread');

  useEffect(() => {
    if (controlledTab) {
      if (controlledTab === 'triage') {
        setInternalTab('chat');
        setChatViewMode('triage');
      } else {
        setInternalTab(controlledTab as 'ai' | 'chat' | 'spectrum');
        if (controlledTab === 'chat') {
          setChatViewMode(hasExistingThread(candidate?.id) ? 'thread' : 'triage');
        }
      }
    }
  }, [controlledTab, candidate?.id]);

  useEffect(() => {
    if (!candidate) {
      setChatViewMode('thread');
      return;
    }
    setChatViewMode(hasExistingThread(candidate.id) ? 'thread' : 'triage');
  }, [candidate?.id]);

  const activeTab = internalTab;
  const setActiveTab = (tab: 'ai' | 'chat' | 'spectrum') => {
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
  const [hoveredClassId, setHoveredClassId] = useState<string | null>(null);
  const [isSubmissionModalOpen, setIsSubmissionModalOpen] = useState(false);
  const [submissionCandidate, setSubmissionCandidate] = useState<CandidateRecord | null>(null);

  const handleOpenSubmissionForCandidate = async (candidateKey: string) => {
    let record = await fetchCandidateById(candidateKey);
    if (!record && candidate) {
      record = {
        id: candidateKey,
        name: candidate.validationData?.objectName || candidate.catalogId || candidate.id,
        ra: candidate.ra,
        dec: candidate.dec,
        discovery_date: new Date().toISOString(),
        candidate_type: candidate.classification === 'transient' ? 'transient' : 'moving_object',
        status: 'community_verified',
        snr: candidate.epochPositions?.[0]?.snr ?? 16.4,
        speed_arcsec_hr: candidate.speedArcsecPerHour ?? 32.4,
        fit_rms_px: candidate.fitRmsPx ?? 0.22,
        spectral_summary: {
          features: ['Infrared Continuum Detection'],
          detector_arrays: ['D2', 'D6'],
        },
        detection_method: candidate.detectionMethod ?? 'heuristic_leave_one_out',
        fixed_stack_url: `/api/motion/coadd/${candidateKey}/fixed.png`,
        motion_stack_url: `/api/motion/coadd/${candidateKey}/motion.png`,
        metadata: {
          target: candidate.catalogId || candidate.id,
          notes: notes || candidate.volunteerNotes || '',
        },
        epoch_count: candidate.epochPositions?.length ?? 4,
        author_id: 'citizen-volunteer',
        author_name: 'Citizen Volunteer Discovery',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        consensus_summary: {
          total_votes: 10,
          likely_real_votes: 10,
          likely_artifact_votes: 0,
          positive_percentage: 100.0,
        },
      };
    }
    if (record) {
      setSubmissionCandidate(record);
      setIsSubmissionModalOpen(true);
    }
  };

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

    const exactCandidateId = candidate.id;
    const candidateTitle =
      candidate.validationData?.objectName ||
      candidate.catalogId ||
      candidate.id;

    const vote: VerificationComment['vote'] =
      selectedClass === 'moving_object'
        ? 'confirm_motion'
        : selectedClass === 'artifact'
        ? 'artifact'
        : selectedClass === 'transient'
        ? 'investigate'
        : 'known';

    const newCommentEntry: VerificationComment = {
      id: `verify-${exactCandidateId}-${Date.now()}`,
      author: 'Citizen Volunteer (You)',
      role: isScientistMode ? 'Science Team' : 'Volunteer',
      timestamp: 'Just now',
      candidateId: exactCandidateId,
      message: notes.trim()
        ? `Classified as ${selectedClass.replace('_', ' ').toUpperCase()} (${selectedConfidence} confidence): "${notes.trim()}"`
        : `Classified as ${selectedClass.replace('_', ' ').toUpperCase()} with ${selectedConfidence} confidence in SPHEREx Band D${selectedArray}.`,
      vote,
      upvotes: 1,
      setting: {
        targetPresetId: currentPresetId ?? null,
        candidateId: exactCandidateId,
        candidateName: candidateTitle,
        ra: candidate.ra ?? ra ?? 166.79,
        dec: candidate.dec ?? dec ?? 5.29,
        fov: fov || "3'",
        selectedArray: typeof selectedArray === 'number' ? selectedArray : 6,
        activeFrameIndex,
        subtractionMode: subtractionMode || 'epoch_difference',
      },
    };

    try {
      const existingRaw = localStorage.getItem('spherex_community_comments');
      const existing: VerificationComment[] = existingRaw ? JSON.parse(existingRaw) : [];
      const updated = [newCommentEntry, ...existing.filter((c) => c.id !== newCommentEntry.id)];
      localStorage.setItem('spherex_community_comments', JSON.stringify(updated));
      window.dispatchEvent(new Event('spherex_comments_updated'));
    } catch {}

    onUpdateCandidateClassification(candidate.id, selectedClass, selectedConfidence, notes);
    setChatViewMode('thread');
  };

  return (
    <aside
      id="tutorial-target-right-panel"
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

      {/* Drawer Header & Tabs: AI Tracks, Chat & Confirm (Unified Triage + Chat), Spectral Analysis */}
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
            <span>AI Tracks</span>
          </button>

          <button
            onClick={() => setActiveTab('chat')}
            className={`py-2 px-3 font-mono text-[11px] font-medium border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer shrink-0 ${
              activeTab === 'chat'
                ? 'border-emerald-400 text-paper-100 bg-paper-900 font-bold'
                : 'border-transparent text-paper-400 hover:text-paper-200'
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5 text-emerald-400" />
            <span>Chat &amp; Confirm</span>
            {candidate && candidate.classification !== 'unreviewed' && (
              <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-emerald-950 text-emerald-300 border border-emerald-600/50">
                {candidate.classification === 'moving_object'
                  ? 'Moving'
                  : candidate.classification === 'transient'
                  ? 'Flash'
                  : candidate.classification === 'artifact'
                  ? 'Artifact'
                  : 'Known'}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('spectrum')}
            className={`py-2 px-3 font-mono text-[11px] font-medium border-b-2 flex items-center gap-1.5 transition-colors cursor-pointer ${
              activeTab === 'spectrum'
                ? 'border-emerald-400 text-paper-100 bg-paper-900 font-bold'
                : 'border-transparent text-paper-400 hover:text-paper-200'
            }`}
          >
            <Radio className="w-3.5 h-3.5 text-emerald-400" />
            <span>Spectral Analysis</span>
          </button>
        </div>

        {/* Quick Expand/Shrink Button */}
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
        {/* TAB 0: AI-RANKED DETECTIONS */}
        {activeTab === 'ai' && (
          <div id="tutorial-target-ai" className="h-full transition-all duration-300">
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
          </div>
        )}

        {/* TAB 1: UNIFIED CHAT & CONFIRM (TRIAGE + DISCUSSION THREAD) */}
        {activeTab === 'chat' && (
          <div className="flex flex-col h-full">
            {candidate ? (
              chatViewMode === 'triage' ? (
                /* TRIAGE FORM VIEW (When starting a thread or editing classification) */
                <div className="p-4 space-y-4 overflow-y-auto">
                  <div className="flex items-center justify-between gap-2">
                    <div className="p-2.5 rounded-xl bg-emerald-950/30 border-2 border-emerald-400/60 flex-1 min-w-0">
                      <span className="font-mono text-[9px] text-emerald-400 uppercase tracking-wider font-bold block">
                        ★ Candidate Triage &amp; Thread Creation
                      </span>
                      <span className="text-xs font-mono text-white font-bold truncate block">
                        #{candidate.mlRank} · {candidate.validationData?.objectName || candidate.catalogId || candidate.id}
                      </span>
                    </div>
                    {hasExistingThread(candidate.id) && (
                      <button
                        type="button"
                        onClick={() => setChatViewMode('thread')}
                        className="btn-tactile-sm px-2.5 py-1.5 rounded-lg border border-paper-700 bg-paper-900 hover:bg-paper-850 text-paper-300 font-mono text-[10px] cursor-pointer shrink-0"
                      >
                        ← View Thread
                      </button>
                    )}
                  </div>

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

                    {/* TiH Classification Helper */}
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
                      Observation Notes &amp; Rationale
                    </label>
                    <textarea
                      rows={2}
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="Enter verification notes or motion characteristics..."
                      className="w-full bg-paper-950 border border-paper-800 rounded-lg p-2 font-mono text-xs text-paper-100 focus:outline-none focus:border-emerald-400 resize-none"
                    />
                  </div>

                  {/* Save Confirmation & Start Discussion Button */}
                  <button
                    onClick={handleSaveTriage}
                    className="btn-tactile w-full py-2.5 bg-emerald-400 hover:bg-emerald-300 text-gray-950 rounded-xl font-mono text-xs font-bold border-2 border-black flex items-center justify-center gap-2 cursor-pointer shadow-[0_0_15px_rgba(16,185,129,0.25)]"
                  >
                    <CheckCircle className="w-3.5 h-3.5 stroke-[2.5]" />
                    <span>{hasExistingThread(candidate.id) ? 'Save Classification & View Discussion →' : 'Save Classification & Start Discussion Thread →'}</span>
                  </button>
                </div>
              ) : (
                /* CHAT THREAD VIEW (Once the thread starts or exists) */
                <div className="flex flex-col h-full">
                  <div className="p-3 bg-paper-950 border-b border-paper-800 space-y-2 shrink-0">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <span className="text-[9px] font-mono uppercase tracking-wider text-emerald-400 font-bold block">
                          ★ Community Discussion &amp; Verification
                        </span>
                        <span className="font-mono text-xs font-bold text-white truncate block">
                          #{candidate.mlRank} · {candidate.validationData?.objectName || candidate.catalogId || candidate.id}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setChatViewMode('triage')}
                        className="btn-tactile-sm px-2.5 py-1 rounded-lg border border-paper-700 bg-paper-900 hover:bg-paper-850 text-emerald-300 font-mono text-[10px] font-bold flex items-center gap-1 cursor-pointer shrink-0"
                        title="Edit classification or triage notes"
                      >
                        <Edit3 className="w-3 h-3 text-emerald-400" />
                        <span>Edit Triage ✎</span>
                      </button>
                    </div>

                    {candidate.volunteerNotes && (
                      <div className="p-2 rounded-lg bg-paper-900/80 border border-paper-800 text-[11px] text-paper-300 leading-relaxed">
                        <span className="text-emerald-400 font-semibold font-mono text-[10px] uppercase block mb-0.5">Catalog &amp; Discovery Note:</span>
                        {candidate.volunteerNotes}
                      </div>
                    )}
                  </div>

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
                    onOpenCatalogue={onOpenCatalogue}
                    onOpenExternalSubmission={handleOpenSubmissionForCandidate}
                  />
                </div>
              )
            ) : (
              <div className="p-8 rounded-xl border border-dashed border-paper-800 text-center space-y-2.5 m-4">
                <HelpCircle className="w-8 h-8 text-paper-600 mx-auto" />
                <div className="font-mono text-xs text-paper-300 font-semibold">No Target Selected</div>
                <p className="text-[11px] text-paper-500 max-w-xs mx-auto leading-relaxed">
                  Click any object in the starfield to inspect its multi-epoch motion vectors and join the community verification discussion.
                </p>
              </div>
            )}
          </div>
        )}

        {/* TAB 2: 102-BAND SPECTRAL ANALYSIS */}
        {activeTab === 'spectrum' && (
          <div id="tutorial-target-spectrum" className="p-3.5 space-y-3 transition-all duration-300">
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

      {/* External Scientific Clearinghouse Submission Modal */}
      <ExternalSubmissionModal
        isOpen={isSubmissionModalOpen}
        onClose={() => setIsSubmissionModalOpen(false)}
        candidate={submissionCandidate}
        onSubmissionSuccess={(_sub) => {
          if (onOpenCatalogue && submissionCandidate) {
            onOpenCatalogue(submissionCandidate.id);
          }
        }}
      />
    </aside>
  );
};
