import { useState, useMemo, useEffect, useRef } from 'react';
import type {
  TargetPreset,
  FOVOption,
  DetectorArrayId,
  SubtractionMode,
  CatalogOverlayState,
  CandidateClassification,
  ConfidenceLevel,
  CandidateObject,
  SpherexEpochFrame,
  VerificationSetting,
  MLAnalysisStatus,
  ObservationLoadStatus,
} from './types/spherex';
import {
  getMockEpochFrames,
  getMockCandidates,
  findCandidateAcrossAllPresets,
  getMock102BandSpectrum,
  NASA_TEST_PRESETS,
  STORED_PRESET_IDS,
} from './services/mockSpherexApi';
import {
  fetchLiveBackendCutoutAnalysis,
} from './services/spherexBackendApi';
import {
  subscribeMotionReviews,
} from './services/motionReviewService';
import {
  fetchLiveCatalogForCoordinate,
  type LiveCatalogResponse,
} from './services/catalogService';
import { availableImageModes } from './services/imageArtifacts';
import { useUrlSync } from './hooks/useUrlSync';
import { useArchiveObservations } from './hooks/useArchiveObservations';
import { ArchiveObservationsPanel } from './components/ArchiveObservationsPanel';
import { DEFAULT_ARCHIVE, isArchiveBrowse, type ArchiveSelection } from './services/archiveObservationsApi';
import { useSpherexPlayer } from './hooks/useSpherexPlayer';
import { startPeriodicVerificationSync } from './services/verificationService';
import { TopNav } from './components/TopNav';
import { LeftControlPanel } from './components/LeftControlPanel';
import { CanvasViewport } from './components/CanvasViewport';
import { MoviePlayerControls } from './components/MoviePlayerControls';
import { RightDrawer } from './components/RightDrawer';
import { EmbedModal } from './components/EmbedModal';
import { HomePage } from './components/HomePage';
import { DiscoveryReportPage } from './components/DiscoveryReportPage';
import { ChooseYourViewModal } from './components/ChooseYourViewModal';
import { VerifyScientistPanel } from './components/VerifyScientistPanel';
import { CatalogueDashboard } from './components/CatalogueDashboard';
import { CandidateDetailPage } from './components/CandidateDetailPage';
import { GuidedTutorialOverlay } from './components/GuidedTutorialOverlay';
import { ReactBitsLoader } from './components/common/ReactBitsLoader';
import { SpherexBlinkLogo } from './components/common/SpherexBlinkLogo';
import {
  Compass,
  Home,
  UserCheck,
  Sliders,
  Sparkles,
  Menu,
  X,
  Share2,
  Database,
  HelpCircle,
} from 'lucide-react';
import { InferencePage } from '../../ml/pvusatov/frontend/src/components/InferencePage';

function initialArchiveSelection(): ArchiveSelection {
  const params = new URLSearchParams(window.location.search);
  return { provider: params.get('archive') || DEFAULT_ARCHIVE.provider, from: params.get('observed_from') || '', through: params.get('observed_through') || '' };
}
function fullViewerUrl() {
  const url = new URL(window.location.href);
  url.searchParams.delete('embed'); url.searchParams.set('tab', 'viewer');
  return url.toString();
}

export function App() {
  // Check if loaded inside an iframe (?embed=true)
  const isEmbedMode =
    typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).get('embed') === 'true';
  const [activeTab, setActiveTab] = useState<'home' | 'viewer' | 'feed' | 'report' | 'inference' | 'catalogue'>(() => {
    if (isEmbedMode) return 'viewer';
    if (typeof window !== 'undefined') {
      const searchParams = new URLSearchParams(window.location.search);
      const requestedTab = searchParams.get('tab');
      if (
        requestedTab === 'viewer' ||
        requestedTab === 'catalogue' ||
        requestedTab === 'feed' ||
        requestedTab === 'report' ||
        requestedTab === 'home' ||
        requestedTab === 'inference'
      ) {
        return requestedTab;
      }
      if (searchParams.has('candidate')) {
        return 'catalogue';
      }
      if (searchParams.has('ra') && searchParams.has('dec')) {
        return 'viewer';
      }
      if (searchParams.has('analysis')) {
        return 'inference';
      }
      if (window.location.hash === '#motion-review') {
        return 'viewer';
      }
    }
    return 'home';
  });

  const [selectedCatalogueCandidateId, setSelectedCatalogueCandidateId] = useState<string | null>(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      return params.get('candidate') || null;
    }
    return null;
  });
  const [mobileViewerPane, setMobileViewerPane] = useState<'canvas' | 'controls' | 'telemetry'>(
    'canvas'
  );
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState<boolean>(false);

  const [viewMode, setViewMode] = useState<'volunteer' | 'scientist'>(() => {
    try {
      const saved = localStorage.getItem('spherex_view_mode');
      if (saved === 'volunteer' || saved === 'scientist') return saved;
    } catch {
      // sandboxed
    }
    return 'volunteer';
  });

  // "Choose your view" pop-up: shown the first time the Sky Viewer is opened on each page load (never on Home)
  const [isViewModalOpen, setIsViewModalOpen] = useState<boolean>(false);
  const hasPromptedViewRef = useRef(false);

  const handleSetViewMode = (mode: 'volunteer' | 'scientist') => {
    setViewMode(mode);
    try {
      localStorage.setItem('spherex_view_mode', mode);
    } catch {
      // sandboxed
    }
  };

  // Interactive Guided Tutorial state (triggered exclusively from Home page)
  const [isTutorialActive, setIsTutorialActive] = useState<boolean>(false);
  const [tutorialStep, setTutorialStep] = useState<number>(0);

  const handleStartTutorial = () => {
    setActiveTab('viewer');
    setIsTutorialActive(true);
    setTutorialStep(0);
    if (typeof window !== 'undefined' && window.innerWidth < 1024) {
      setMobileViewerPane('controls');
    } else {
      setMobileViewerPane('canvas');
    }
  };

  const [initialViewerCandidate] = useState(() => {
    if (isArchiveBrowse(initialArchiveSelection())) return null;
    const params = new URLSearchParams(window.location.search);
    const candidate = params.get('candidate');
    return candidate && params.get('tab') === 'viewer' && !params.has('preset') && !params.has('ra') && !params.has('dec')
      ? { id: candidate, detector: params.get('detector') } : null;
  });
  const initialCandidateResolved = useRef(false);

  const [currentPresetId, setCurrentPresetId] = useState<string | null>(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      if ((params.get('archive') && params.get('archive') !== 'irsa-spherex') || params.has('observed_from') || params.has('observed_through')) return null;
      if (params.has('preset')) return params.get('preset');
      if (params.has('ra') && params.has('dec')) return null;
      const candParam = params.get('candidate');
      if (candParam) {
        const found = findCandidateAcrossAllPresets(candParam);
        return found?.presetId ?? null;
      }
    }
    return '3i-atlas';
  });
  const [archiveSelection, setArchiveSelection] = useState<ArchiveSelection>(initialArchiveSelection);
  const archive = useArchiveObservations();
  const archiveBrowsing = !currentPresetId && isArchiveBrowse(archiveSelection);
  const [ra, setRa] = useState<number>(166.790000);
  const [dec, setDec] = useState<number>(5.290000);
  const [fov, setFov] = useState<FOVOption>("5'");
  const [selectedArray, setSelectedArray] = useState<DetectorArrayId | 'all'>(() => {
    const params = new URLSearchParams(window.location.search);
    const detector = params.get('detector');
    if (detector === 'all') return 'all';
    if (detector && /^[1-6]$/.test(detector)) return Number(detector) as DetectorArrayId;
    if (params.get('preset') === '3i-atlas-d2') return 2;
    if (params.get('preset') === 'vesta-d3') return 3;
    return NASA_TEST_PRESETS.find(preset => preset.id === params.get('preset'))?.recommendedArray ?? 6;
  });
  const [subtractionMode, setSubtractionMode] = useState<SubtractionMode>('raw_calibrated');
  const [activeFrameIndex, setActiveFrameIndex] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [fps, setFps] = useState<number>(3);
  const [blinkMode, setBlinkMode] = useState<boolean>(false);

  // Track when precomputed motion review.json finishes loading
  const [motionReviewsRevision, setMotionReviewsRevision] = useState<number>(0);

  // All known-catalog overlays are on by default; users can untick them
  const ALL_OVERLAYS_ON: CatalogOverlayState = {
    gaiaDr3: true,
    wise: true,
    solarSystemEphemeris: true,
  };
  const [overlays, setOverlays] = useState<CatalogOverlayState>(ALL_OVERLAYS_ON);

  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(() => {
    if (isArchiveBrowse(initialArchiveSelection())) return null;
    if (typeof window !== 'undefined') {
      const cand = new URLSearchParams(window.location.search).get('candidate');
      if (cand) return cand;
    }
    return '3I/ATLAS';
  });
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isEmbedModalOpen, setIsEmbedModalOpen] = useState<boolean>(false);
  const [drawerControlledTab, setDrawerControlledTab] = useState<
    'ai' | 'triage' | 'chat' | 'spectrum' | null
  >(null);

  useEffect(() => {
    if (activeTab !== 'viewer') return;
    // Entering the Sky Viewer: re-enable every catalog overlay
    setOverlays({ gaiaDr3: true, wise: true, solarSystemEphemeris: true });
    if (!hasPromptedViewRef.current) {
      hasPromptedViewRef.current = true;
      setIsViewModalOpen(true);
    }
  }, [activeTab]);

  // Dynamically sync verifications & triage stream for active embeds and browser tabs
  useEffect(() => {
    const cancelSync = startPeriodicVerificationSync(45000);
    return () => cancelSync();
  }, []);

  const [customFrames, setCustomFrames] = useState<SpherexEpochFrame[] | null>(null);
  const [searchStatus, setSearchStatus] = useState<ObservationLoadStatus>(() => {
    if (isArchiveBrowse(initialArchiveSelection())) return { source: 'idle', message: 'Choose the source and observation period, then Update Field.' };
    const preset = new URLSearchParams(window.location.search).get('preset');
    return preset && !STORED_PRESET_IDS.has(preset)
      ? { source: 'error', message: 'No verified stored image sequence is available for this preset.' }
      : { source: 'preset', message: 'Stored benchmark sequence' };
  });

  const [mlAnalysisStatus, setMlAnalysisStatus] = useState<MLAnalysisStatus>({
    state: 'completed',
    stage: 'Stored benchmark · no new inference',
    progress: 100,
    stepIndex: 3,
    resultSource: 'stored',
  });
  const mlRunIdRef = useRef(0);
  const liveRequestRef = useRef<AbortController | null>(null);
  useEffect(() => () => liveRequestRef.current?.abort(), []);

  const frames = useMemo(() => {
    void motionReviewsRevision;
    if (currentPresetId) {
      const arrayId = selectedArray;
      return getMockEpochFrames(currentPresetId, arrayId);
    }
    return selectedArray === 'all' ? [] : (customFrames ?? []).filter(frame => frame.detectorArray === selectedArray);
  }, [currentPresetId, customFrames, selectedArray, motionReviewsRevision]);

  const [candidatesList, setCandidatesList] = useState<CandidateObject[]>(() => {
    if (isArchiveBrowse(initialArchiveSelection())) return [];
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const candParam = params.get('candidate');
      if (candParam) {
        const found = findCandidateAcrossAllPresets(candParam);
        if (found) {
          return getMockCandidates(found.presetId, found.recommendedArray);
        }
        return [];
      }
      const presetParam = params.get('preset');
      if (presetParam) {
        return getMockCandidates(presetParam, 6);
      }
    }
    return getMockCandidates('3i-atlas', 6);
  });

  // Change pixels and tracks together; an unsupported detector is an empty view.
  useEffect(() => subscribeMotionReviews(() => {
    setMotionReviewsRevision(revision => revision + 1);
    if (initialViewerCandidate && !initialCandidateResolved.current) {
      initialCandidateResolved.current = true;
      const found = findCandidateAcrossAllPresets(initialViewerCandidate.id);
      if (found) {
        const detector = initialViewerCandidate.detector === 'all' ? 'all'
          : initialViewerCandidate.detector && /^[1-6]$/.test(initialViewerCandidate.detector)
          ? Number(initialViewerCandidate.detector) as DetectorArrayId : found.recommendedArray as DetectorArrayId;
        const updated = getMockCandidates(found.presetId, detector);
        setCurrentPresetId(found.presetId); setSelectedArray(detector);
        setRa(found.candidate.ra); setDec(found.candidate.dec);
        setCandidatesList(updated);
        setSelectedCandidateId(updated.some(candidate => candidate.id === found.candidate.id) ? found.candidate.id : updated[0]?.id ?? null);
      } else {
        setCandidatesList([]); setCustomFrames([]); setCurrentPresetId(null);
        setSearchStatus({ source: 'error', message: 'The requested candidate has no verified stored sequence.' });
      }
      return;
    }
    if (!currentPresetId) return;
    const updated = getMockCandidates(currentPresetId, selectedArray);
    setCandidatesList(updated);
    setSelectedCandidateId(previous => updated.some(candidate => candidate.id === previous) ? previous : updated[0]?.id ?? null);
  }), [currentPresetId, selectedArray, initialViewerCandidate]);

  const handleSelectDetectorArray = (newArray: DetectorArrayId | 'all') => {
    initialCandidateResolved.current = true;
    setSelectedArray(newArray);
    setActiveFrameIndex(0);
    setIsPlaying(false);
    setOverlays({ gaiaDr3: true, wise: true, solarSystemEphemeris: true });
    if (currentPresetId) {
      const updated = getMockCandidates(currentPresetId, newArray);
      setCandidatesList(updated);
      setSelectedCandidateId(updated[0]?.id ?? null);
    } else {
      void handleSearchCoordinates(ra, dec, { fov, detector: newArray, frameIndex: 0, candidateId: '' });
    }
  };

  const activeCandidate = useMemo(() => {
    if (selectedCandidateId) {
      const match = candidatesList.find((c) => c.id === selectedCandidateId);
      if (match) return match;
    }
    return candidatesList[0] || null;
  }, [candidatesList, selectedCandidateId]);

  const [liveCatalog, setLiveCatalog] = useState<LiveCatalogResponse | null>(null);
  const [isCatalogLoading, setIsCatalogLoading] = useState<boolean>(false);
  const [catalogRefreshCounter, setCatalogRefreshCounter] = useState<number>(0);

  // Automatically query space-agency catalogs (ESA Gaia DR3, NASA AllWISE, CDS SIMBAD, JPL Horizons)
  // whenever the field coordinate (ra, dec), FOV, or selected candidate object changes
  useEffect(() => {
    let cancelled = false;
    const queryRa = activeCandidate?.ra ?? ra;
    const queryDec = activeCandidate?.dec ?? dec;
    const fovArcmin = parseFloat(fov) || 5;

    setIsCatalogLoading(true);
    setLiveCatalog(null);
    fetchLiveCatalogForCoordinate({
      queryRa,
      queryDec,
      centerRa: ra,
      centerDec: dec,
      fovArcmin,
      candidateId: activeCandidate ? `${activeCandidate.id}-${catalogRefreshCounter}` : `${catalogRefreshCounter}`,
    })
      .then((res) => {
        if (!cancelled) {
          setLiveCatalog(res);
          setIsCatalogLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setIsCatalogLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [ra, dec, fov, activeCandidate?.id, activeCandidate?.ra, activeCandidate?.dec, catalogRefreshCounter]);

  const spectrumData = useMemo(() => {
    return getMock102BandSpectrum(activeCandidate?.id || 'default', activeCandidate?.ra ?? ra, activeCandidate?.dec ?? dec);
  }, [activeCandidate, ra, dec]);

  useUrlSync(
    {
      ra,
      dec,
      fov,
      selectedArray,
      subtractionMode,
      activeFrameIndex,
      candidateId: activeTab === 'catalogue' ? selectedCatalogueCandidateId : selectedCandidateId,
      tab: activeTab,
      presetId: currentPresetId,
      archive: archiveSelection.provider, observedFrom: archiveSelection.from, observedThrough: archiveSelection.through,
    },
    (partial) => {
      if (partial.ra !== undefined) setRa(partial.ra);
      if (partial.dec !== undefined) setDec(partial.dec);
      if (partial.fov !== undefined) setFov(partial.fov);
      if (partial.selectedArray !== undefined) setSelectedArray(partial.selectedArray);
      if (partial.subtractionMode !== undefined) setSubtractionMode(partial.subtractionMode);
      if (partial.activeFrameIndex !== undefined) setActiveFrameIndex(partial.activeFrameIndex);
      if (partial.candidateId !== undefined) {
        if (activeTab === 'catalogue' || partial.tab === 'catalogue') {
          setSelectedCatalogueCandidateId(partial.candidateId);
        }
        setSelectedCandidateId(partial.candidateId);
      }
      if (partial.tab !== undefined) setActiveTab(partial.tab);
      if (partial.presetId !== undefined) setCurrentPresetId(partial.presetId);
      if (partial.archive !== undefined || partial.observedFrom !== undefined || partial.observedThrough !== undefined) {
        setArchiveSelection(value => ({ provider: partial.archive ?? value.provider, from: partial.observedFrom ?? value.from, through: partial.observedThrough ?? value.through }));
      }
    }
  );

  const { skippedNotice, clearSkippedNotice, stepForward, stepBackward } = useSpherexPlayer({
    frames,
    fps,
    isPlaying,
    blinkMode,
    currentIndex: activeFrameIndex,
    onFrameChange: setActiveFrameIndex,
  });



  // Handler when user searches custom coordinates on Home page or LeftControlPanel
  const handleSearchCoordinates = async (newRa: number, newDec: number, request?: { fov: FOVOption; detector: DetectorArrayId | 'all'; frameIndex: number; candidateId: string }, selectionOverride?: ArchiveSelection) => {
    initialCandidateResolved.current = true;
    liveRequestRef.current?.abort();
    const runId = ++mlRunIdRef.current;
    const startTime = performance.now();
    const selection = selectionOverride ?? (request ? DEFAULT_ARCHIVE : archiveSelection);
    const browse = isArchiveBrowse(selection);
    setArchiveSelection(selection);
    archive.reset();
    const array = request?.detector ?? selectedArray;
    if (!browse && array === 'all') {
      setCurrentPresetId(null); setCustomFrames([]); setCandidatesList([]); setSelectedCandidateId(null);
      setSearchStatus({ source: 'error', message: 'Multi-detector composite unavailable. Select an individual detector.' });
      setMlAnalysisStatus({ state: 'idle', stage: 'No composite data', progress: 0, stepIndex: 1 });
      return;
    }
    const detNum = array as DetectorArrayId;

    if (!browse) {
      const matchedPreset = NASA_TEST_PRESETS.find(p => Math.hypot(p.raDeg - newRa, p.decDeg - newDec) < 0.2);
      if (matchedPreset) {
        handleSelectPreset(matchedPreset);
        if (request?.detector && request.detector !== 'all') {
          setSelectedArray(request.detector);
          const cands = getMockCandidates(matchedPreset.id, request.detector);
          setCandidatesList(cands);
          if (request.candidateId && cands.some(c => c.id === request.candidateId)) {
            setSelectedCandidateId(request.candidateId);
          }
        }
        return;
      }
      if (Math.hypot(223.025 - newRa, -11.992 - newDec) < 0.3) {
        const vestaPreset: TargetPreset = {
          id: (request?.detector ?? selectedArray) === 3 ? 'vesta-d3' : 'vesta-d6',
          name: '(4) Vesta',
          subtitle: 'Main-Belt Asteroid (DR1 BLOOM Mask)',
          raHms: '14h 52m 06s',
          decDms: '-11° 59\' 31"',
          raDeg: 223.025,
          decDeg: -11.992,
          description: 'Bright asteroid saturated core recovered via BLOOM bitmask centroids across DR1 visits.',
          recommendedArray: (request?.detector ?? selectedArray) === 3 ? 3 : 6,
          expectedClass: 'moving_object',
        };
        handleSelectPreset(vestaPreset);
        if (request?.candidateId) {
          setSelectedCandidateId(request.candidateId);
        }
        return;
      }
    }

    setRa(newRa);
    setDec(newDec);
    setCurrentPresetId(null);
    setSelectedCandidateId(null);
    setCandidatesList([]);
    setCustomFrames([]);
    setActiveFrameIndex(0);
    setIsPlaying(false);
    setBlinkMode(false);
    setIsLoading(false);
    setCatalogRefreshCounter(c => c + 1);
    setActiveTab('viewer');

    const controller = new AbortController();
    liveRequestRef.current = controller;
    setSearchStatus({ source: 'loading', message: browse ? `Searching ${selection.provider} observation metadata` : 'Loading observations from NASA IRSA' });
    setMlAnalysisStatus({ state: 'running', stage: 'Waiting for archive observations', progress: 0, stepIndex: 1 });
    try {
      if (browse) {
        const found = await archive.search({ ...selection, ra: newRa, dec: newDec, fovArcmin: parseFloat(request?.fov ?? fov) || 5 }, controller.signal);
        if (controller.signal.aborted || mlRunIdRef.current !== runId) return;
        setSearchStatus({ source: 'archive', message: `${found.returned_count} metadata records; inspect each provider outcome and select IDs to download.` });
        setMlAnalysisStatus({ state: 'idle', stage: 'Archive discovery only; no ML analysis was requested', progress: 0, stepIndex: 1 });
        return;
      }
      const result = await fetchLiveBackendCutoutAnalysis({
        ra: newRa, dec: newDec, fovArcmin: parseFloat(request?.fov ?? fov) || 5, detector: detNum, signal: controller.signal,
        onProgress: progress => {
          if (controller.signal.aborted || mlRunIdRef.current !== runId) return;
          setSearchStatus({ source: 'loading', message: progress.message });
          setMlAnalysisStatus({ state: 'running', stage: progress.message,
            progress: progress.total > 0 ? Math.round(100 * progress.ready / progress.total) : 0,
            stepIndex: progress.phase === 'downloading' ? 1 : 2 });
        },
      });
      if (controller.signal.aborted || mlRunIdRef.current !== runId) return;
      setCustomFrames(result.frames);
      setCandidatesList(result.candidates);
      const selected = result.candidates.find(candidate => candidate.id === request?.candidateId) ?? result.candidates[0];
      setSelectedCandidateId(selected?.id ?? null);
      setActiveFrameIndex(Math.max(0, Math.min(request?.frameIndex ?? 0, result.frames.length - 1)));
      setSearchStatus({ source: 'live', message: `${result.frames.length} downloaded observations; analysis completed` });
      setMlAnalysisStatus({ state: 'completed', stage: 'Difference-image analysis completed', progress: 100, stepIndex: 3,
        tracksDetected: result.candidates.length, modelName: result.modelName,
        resultSource: 'live', modelFamily: result.model.model_family, modelSha256: result.model.sha256,
        scoreKind: result.model.score_kind, scoreDescription: result.model.score_description, latencyMs: Math.round(performance.now() - startTime),
        topSpeedArcsecHr: result.candidates[0]?.speedArcsecPerHour, topFitRmsPx: result.candidates[0]?.fitRmsPx });
    } catch (error) {
      if (controller.signal.aborted || mlRunIdRef.current !== runId) return;
      const message = error instanceof Error ? error.message : 'Observation request failed';
      setCustomFrames([]);
      setCandidatesList([]);
      setSelectedCandidateId(null);
      setSearchStatus({ source: 'error', message });
      setMlAnalysisStatus({ state: 'failed', stage: message, progress: 0, stepIndex: 1 });
    }
  };

  // Handler when user clicks a benchmark preset on Home page
  const handleSelectPreset = (preset: TargetPreset) => {
    initialCandidateResolved.current = true;
    liveRequestRef.current?.abort();
    ++mlRunIdRef.current;

    archive.reset();
    setArchiveSelection(DEFAULT_ARCHIVE);
    setCurrentPresetId(preset.id);
    setCustomFrames(null);
    setOverlays({ gaiaDr3: true, wise: true, solarSystemEphemeris: true });
    setSearchStatus({
      source: 'preset',
      message: `NASA Benchmark Preset: ${preset.name}`,
    });
    setRa(preset.raDeg);
    setDec(preset.decDeg);
    setSelectedArray(preset.recommendedArray);
    setActiveFrameIndex(0);

    // Automatically select the most informative layer for Vesta (BLOOM mask) or 3I/ATLAS (Aligned/Diff)
    if (preset.id.startsWith('vesta')) {
      setSubtractionMode('bloom_mask');
    } else {
      setSubtractionMode('raw_calibrated');
    }

    const newCands = getMockCandidates(preset.id, preset.recommendedArray);
    setCandidatesList(newCands);
    if (newCands.length > 0) {
      setSelectedCandidateId(newCands[0].id);
    }
    setActiveTab('viewer');
    setIsLoading(true);
    setTimeout(() => setIsLoading(false), 200);

    setMlAnalysisStatus({ state: 'completed', stage: 'Stored benchmark · no new inference',
      progress: 100, stepIndex: 3, resultSource: 'stored', tracksDetected: newCands.length });
  };

  const handleRefreshCutout = () => {
    void handleSearchCoordinates(ra, dec);
  };

  // Deep-link jump from a verification comment or panel directly into Sky Viewer
  const handleSelectVerificationTarget = (setting: VerificationSetting) => {
    initialCandidateResolved.current = true;
    setFov(setting.fov);
    setSelectedArray(setting.selectedArray);
    setSubtractionMode(setting.subtractionMode);
    setDrawerControlledTab('chat');
    const preset = NASA_TEST_PRESETS.find(item => item.id === setting.targetPresetId);
    if (!preset) {
      void handleSearchCoordinates(setting.ra, setting.dec, {
        fov: setting.fov, detector: setting.selectedArray, frameIndex: setting.activeFrameIndex, candidateId: setting.candidateId,
      });
      return;
    }
    liveRequestRef.current?.abort();
    ++mlRunIdRef.current;
    const detector = setting.selectedArray;
    const frames = getMockEpochFrames(preset.id, detector);
    const candidates = getMockCandidates(preset.id, detector);
    archive.reset();
    setArchiveSelection(DEFAULT_ARCHIVE);
    setCurrentPresetId(preset.id);
    setCustomFrames(null);
    setCandidatesList(candidates);
    setSelectedCandidateId(candidates.find(candidate => candidate.id === setting.candidateId)?.id ?? candidates[0]?.id ?? null);
    setRa(preset.raDeg);
    setDec(preset.decDeg);
    setActiveFrameIndex(Math.max(0, Math.min(setting.activeFrameIndex, frames.length - 1)));
    setIsPlaying(false);
    setBlinkMode(false);
    setIsLoading(false);
    setSearchStatus({ source: 'preset', message: `Precomputed benchmark: ${preset.name}` });
    setMlAnalysisStatus({ state: 'completed', stage: 'Stored benchmark · no new inference', progress: 100, stepIndex: 3, resultSource: 'stored', tracksDetected: candidates.length });
    setActiveTab('viewer');
  };

  const handleToggleOverlay = (key: keyof CatalogOverlayState) => {
    setOverlays((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleUpdateCandidateClassification = (
    candidateId: string,
    classification: CandidateClassification,
    confidence: ConfidenceLevel,
    notes: string
  ) => {
    setCandidatesList((prev) =>
      prev.map((c) =>
        c.id === candidateId
          ? {
              ...c,
              classification,
              confidence,
              volunteerNotes: notes,
            }
          : c
      )
    );
  };

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-paper-950 text-paper-100">
      {isLoading && (
        <ReactBitsLoader
          label="Fetching SPHEREx Cutout Stream"
          sublabel={`RA ${ra.toFixed(4)}°, Dec ${dec.toFixed(4)}° (FOV: ${fov})`}
        />
      )}

      {/* Top Header: Seamless Responsive Navigation Bar */}
      {!isEmbedMode && (
        <header className="h-12 shrink-0 bg-paper-900 border-b border-paper-800 px-2 sm:px-4 flex items-center justify-between text-xs select-none z-30 gap-2">
          {/* Left: Hamburger (Mobile) + Logo & Direct Tab Navigation */}
          <div className="flex items-center space-x-1.5 sm:space-x-3 min-w-0">
          <button
            onClick={() => setIsMobileMenuOpen(true)}
            className="md:hidden btn-tactile-sm p-1 rounded-lg border-2 border-black bg-paper-950 text-paper-300 hover:text-emerald-400 cursor-pointer flex items-center justify-center shrink-0"
            title="Open Navigation Menu"
          >
            <Menu className="w-4 h-4" />
          </button>

          <div
            onClick={() => setActiveTab('home')}
            className="flex items-center space-x-2 cursor-pointer group shrink-0"
            title="SPHEREx Blink Homepage"
          >
            <SpherexBlinkLogo size={22} />
            <span className="font-bold text-white tracking-wide text-xs font-sans group-hover:text-emerald-400 transition-colors hidden xl:inline">
              SPHEREx <span className="text-emerald-400">Blink</span>
            </span>
          </div>

          {/* Core Tab Navigation: Always Visible Across All Screen Sizes */}
          <nav className="flex items-center space-x-1 font-mono text-[11px] overflow-x-auto no-scrollbar py-0.5">
            <button
              type="button"
              onClick={() => setActiveTab('home')}
              className={`btn-tactile-sm px-2.5 py-1 sm:py-1.5 rounded-lg flex items-center gap-1.5 transition-all border-2 border-black cursor-pointer shrink-0 ${
                activeTab === 'home'
                  ? 'bg-emerald-400 text-gray-950 font-bold'
                  : 'bg-paper-950 text-paper-300 hover:text-white'
              }`}
              title="Homepage & Coordinate Search"
            >
              <Home className="w-3.5 h-3.5 text-emerald-400 group-hover:text-gray-950" />
              <span className="font-semibold">Home</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('viewer')}
              className={`btn-tactile-sm px-2.5 py-1 sm:py-1.5 rounded-lg flex items-center gap-1.5 transition-all border-2 border-black cursor-pointer shrink-0 ${
                activeTab === 'viewer'
                  ? 'bg-emerald-400 text-gray-950 font-bold'
                  : 'bg-paper-950 text-paper-300 hover:text-white'
              }`}
              title="Interactive Sky Viewer"
            >
              <Compass className="w-3.5 h-3.5 text-emerald-400" />
              <span className="font-semibold">Sky Viewer</span>
            </button>

            {/* Verification Feed Button */}
            <button
              type="button"
              onClick={() => setActiveTab('feed')}
              className={`btn-tactile-sm px-2.5 py-1 sm:py-1.5 rounded-lg flex items-center gap-1.5 transition-all border-2 border-black cursor-pointer shrink-0 ${
                activeTab === 'feed'
                  ? 'bg-sky-400 text-gray-950 font-bold shadow-[0_0_12px_rgba(56,189,248,0.4)]'
                  : 'bg-paper-950 text-sky-300 hover:text-white border-sky-500/40'
              }`}
              title="Community Verification Feed & Peer-Review Discussions"
            >
              <UserCheck className="w-3.5 h-3.5 text-sky-400" />
              <span className="font-semibold">Verification Feed</span>
            </button>

            {/* Candidate Catalog Button - directly beside Verification Feed */}
            <button
              type="button"
              onClick={() => {
                setSelectedCatalogueCandidateId(null);
                setActiveTab('catalogue');
              }}
              className={`btn-tactile-sm px-2.5 py-1 sm:py-1.5 rounded-lg flex items-center gap-1.5 transition-all border-2 border-black cursor-pointer shrink-0 ${
                activeTab === 'catalogue'
                  ? 'bg-emerald-400 text-gray-950 font-bold shadow-[0_0_12px_rgba(16,185,129,0.3)]'
                  : 'bg-paper-950 text-emerald-300 hover:text-white border-emerald-500/40'
              }`}
              title="PlanetX Persistent Candidate Catalog & External Submissions"
            >
              <Database className="w-3.5 h-3.5 text-emerald-400" />
              <span className="font-semibold">Candidate Catalog</span>
            </button>
          </nav>
        </div>

        {/* Right Controls: Volunteer/Scientist Toggle & Toolbar */}
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          {/* Tutorial Button (Available ONLY on Home page directly beside the Vol/Sci toggle) */}
          {activeTab === 'home' && (
            <button
              onClick={handleStartTutorial}
              className="btn-tactile-sm px-2.5 sm:px-3 py-1 sm:py-1.5 rounded-lg border-2 border-black bg-gradient-to-r from-emerald-400 to-teal-400 hover:from-emerald-300 hover:to-teal-300 text-gray-950 font-bold font-mono text-xs flex items-center gap-1.5 shadow-[0_0_12px_rgba(16,185,129,0.35)] cursor-pointer transition-all shrink-0"
              title="Launch Guided Sky Viewer Tutorial"
            >
              <HelpCircle className="w-3.5 h-3.5 stroke-[2.5]" />
              <span>Tutorial</span>
            </button>
          )}

          <div className="flex items-center rounded-lg border-2 border-black bg-paper-950 p-0.5 btn-tactile-sm">
            <button
              onClick={() => handleSetViewMode('volunteer')}
              className={`px-2 sm:px-2.5 py-0.5 sm:py-1 rounded text-[10px] sm:text-[11px] font-mono font-bold transition-all cursor-pointer ${
                viewMode === 'volunteer'
                  ? 'bg-emerald-400 text-gray-950'
                  : 'text-paper-400 hover:text-paper-100'
              }`}
              title="Volunteer View"
            >
              Vol
            </button>
            <button
              onClick={() => handleSetViewMode('scientist')}
              className={`px-2 sm:px-2.5 py-0.5 sm:py-1 rounded text-[10px] sm:text-[11px] font-mono font-bold transition-all cursor-pointer ${
                viewMode === 'scientist'
                  ? 'bg-emerald-400 text-gray-950'
                  : 'text-paper-400 hover:text-paper-100'
              }`}
              title="Scientist View"
            >
              Sci
            </button>
          </div>

          {/* Global Toolbar (Only active when in Sky Viewer) */}
          <TopNav
            ra={ra}
            dec={dec}
            fov={fov}
            selectedArray={selectedArray}
            subtractionMode={subtractionMode}
            activeFrameIndex={activeFrameIndex}
            candidateId={selectedCandidateId}
            presetId={currentPresetId}
            onOpenEmbedModal={() => setIsEmbedModalOpen(true)}
            onOpenFeed={() => setActiveTab('feed')}
            onOpenCatalogue={() => {
              setSelectedCatalogueCandidateId(null);
              setActiveTab('catalogue');
            }}
            isViewerActive={activeTab === 'viewer'}
            isScientistMode={viewMode === 'scientist'}
          />
        </div>
      </header>
      )}

      {/* Mobile Left Sidebar Drawer (Opened by 3 lines / Hamburger button) */}
      {isMobileMenuOpen && (
        <div className="fixed inset-0 z-50 flex md:hidden">
          {/* Backdrop blur overlay */}
          <div
            onClick={() => setIsMobileMenuOpen(false)}
            className="fixed inset-0 bg-black/80 backdrop-blur-sm transition-opacity"
          />

          {/* Sidebar Drawer Container */}
          <div className="relative w-72 max-w-[85vw] bg-paper-950 border-r-2 border-paper-800 h-full flex flex-col p-5 shadow-2xl z-10 anim-fall">
            {/* Drawer Header */}
            <div className="flex items-center justify-between pb-4 border-b border-paper-800">
              <div className="flex items-center space-x-2.5">
                <SpherexBlinkLogo size={24} />
                <div>
                  <span className="font-bold text-white tracking-wide text-sm font-sans block">
                    SPHEREx <span className="text-emerald-400">Blink</span>
                  </span>
                  <span className="text-[10px] font-mono text-paper-400">
                    NASA Infrared Astrometry
                  </span>
                </div>
              </div>
              <button
                onClick={() => setIsMobileMenuOpen(false)}
                className="btn-tactile-sm p-1.5 rounded-lg border-2 border-black bg-paper-900 text-paper-400 hover:text-white cursor-pointer"
                aria-label="Close menu"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Navigation Options */}
            <div className="mt-5 space-y-2 flex-1 overflow-y-auto">
              <span className="text-[10px] font-mono uppercase tracking-wider text-paper-500 font-bold px-1 block mb-1">
                Navigation
              </span>

              <button
                onClick={() => {
                  setActiveTab('home');
                  setIsMobileMenuOpen(false);
                }}
                className={`w-full btn-tactile p-3 rounded-xl border-2 border-black flex items-center gap-3 text-xs font-mono font-bold cursor-pointer transition-all ${
                  activeTab === 'home'
                    ? 'bg-emerald-400 text-gray-950 shadow-[0_0_15px_rgba(16,185,129,0.3)]'
                    : 'bg-paper-900 text-paper-200 hover:bg-paper-850'
                }`}
              >
                <Home
                  className={`w-4 h-4 ${
                    activeTab === 'home' ? 'text-gray-950' : 'text-emerald-400'
                  }`}
                />
                <span>Homepage</span>
              </button>

              <button
                onClick={() => {
                  setActiveTab('viewer');
                  setIsMobileMenuOpen(false);
                }}
                className={`w-full btn-tactile p-3 rounded-xl border-2 border-black flex items-center gap-3 text-xs font-mono font-bold cursor-pointer transition-all ${
                  activeTab === 'viewer'
                    ? 'bg-emerald-400 text-gray-950 shadow-[0_0_15px_rgba(16,185,129,0.3)]'
                    : 'bg-paper-900 text-paper-200 hover:bg-paper-850'
                }`}
              >
                <Compass
                  className={`w-4 h-4 ${
                    activeTab === 'viewer' ? 'text-gray-950' : 'text-emerald-400'
                  }`}
                />
                <span>Sky Viewer</span>
              </button>

              <button
                onClick={() => {
                  setActiveTab('feed');
                  setIsMobileMenuOpen(false);
                }}
                className={`w-full btn-tactile p-3 rounded-xl border-2 border-black flex items-center gap-3 text-xs font-mono font-bold cursor-pointer transition-all ${
                  activeTab === 'feed'
                    ? 'bg-sky-400 text-gray-950 shadow-[0_0_15px_rgba(56,189,248,0.4)]'
                    : 'bg-paper-900 text-sky-300 hover:bg-paper-850'
                }`}
              >
                <UserCheck
                  className={`w-4 h-4 ${activeTab === 'feed' ? 'text-gray-950' : 'text-sky-400'}`}
                />
                <span>Verification Feed</span>
              </button>

              <button
                onClick={() => {
                  setSelectedCatalogueCandidateId(null);
                  setActiveTab('catalogue');
                  setIsMobileMenuOpen(false);
                }}
                className={`w-full btn-tactile p-3 rounded-xl border-2 border-black flex items-center gap-3 text-xs font-mono font-bold cursor-pointer transition-all ${
                  activeTab === 'catalogue'
                    ? 'bg-emerald-400 text-gray-950 shadow-[0_0_15px_rgba(16,185,129,0.3)]'
                    : 'bg-paper-900 text-emerald-400 hover:bg-paper-850'
                }`}
              >
                <Database
                  className={`w-4 h-4 ${activeTab === 'catalogue' ? 'text-gray-950' : 'text-emerald-400'}`}
                />
                <span>Candidate Catalog</span>
              </button>

              {/* View Mode Switcher in Mobile Drawer */}
              <div className="pt-4 border-t border-paper-800 space-y-2">
                <span className="text-[10px] font-mono uppercase tracking-wider text-paper-500 font-bold px-1 block">
                  Experience Mode
                </span>

                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => handleSetViewMode('volunteer')}
                    className={`p-2.5 rounded-xl border-2 border-black font-mono text-xs font-bold flex flex-col items-center gap-1 cursor-pointer transition-all ${
                      viewMode === 'volunteer'
                        ? 'bg-emerald-400 text-gray-950 shadow-[0_0_12px_rgba(16,185,129,0.3)]'
                        : 'bg-paper-900 text-paper-400 hover:text-white'
                    }`}
                  >
                    <span>Volunteer</span>
                    <span className="text-[9px] font-normal opacity-80">Citizen Science</span>
                  </button>

                  <button
                    onClick={() => handleSetViewMode('scientist')}
                    className={`p-2.5 rounded-xl border-2 border-black font-mono text-xs font-bold flex flex-col items-center gap-1 cursor-pointer transition-all ${
                      viewMode === 'scientist'
                        ? 'bg-emerald-400 text-gray-950 shadow-[0_0_12px_rgba(16,185,129,0.3)]'
                        : 'bg-paper-900 text-paper-400 hover:text-white'
                    }`}
                  >
                    <span>Scientist</span>
                    <span className="text-[9px] font-normal opacity-80">Research HUD</span>
                  </button>
                </div>

                {/* Tutorial trigger button on mobile drawer - available ONLY on Home page */}
                {activeTab === 'home' && (
                  <button
                    onClick={() => {
                      setIsMobileMenuOpen(false);
                      handleStartTutorial();
                    }}
                    className="w-full mt-2 py-2 px-3 rounded-xl border-2 border-black bg-gradient-to-r from-emerald-400 to-teal-400 text-gray-950 font-mono font-bold text-xs flex items-center justify-center gap-2 shadow-[0_0_12px_rgba(16,185,129,0.3)] cursor-pointer"
                  >
                    <HelpCircle className="w-3.5 h-3.5 stroke-[2.5]" />
                    <span>Launch Sky Viewer Tutorial</span>
                  </button>
                )}
              </div>

              {/* Quick Actions (Share & Embed) */}
              {activeTab === 'viewer' && (
                <div className="pt-4 border-t border-paper-800 space-y-2">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-paper-500 font-bold px-1 block">
                    Current Coordinates
                  </span>
                  <div className="p-2.5 rounded-lg bg-paper-900 border border-paper-800 font-mono text-[11px] text-paper-300">
                    <div>
                      RA: <span className="text-ochre-300 font-bold">{ra.toFixed(4)}°</span>
                    </div>
                    <div>
                      Dec: <span className="text-ochre-300 font-bold">{dec.toFixed(4)}°</span>
                    </div>
                  </div>

                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(window.location.href);
                      setIsMobileMenuOpen(false);
                    }}
                    className="w-full py-2 px-3 rounded-lg border-2 border-black bg-paper-900 text-paper-200 hover:text-emerald-300 font-mono text-xs flex items-center justify-center gap-2 cursor-pointer"
                  >
                    <Share2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Copy Share Link</span>
                  </button>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="pt-3 border-t border-paper-800 text-[10px] font-mono text-paper-500 text-center">
              NASA SPHEREx • Caltech / IPAC
            </div>
          </div>
        </div>
      )}

      {/* -1. Raw Inference View (when requested) */}
      {activeTab === 'inference' && <InferencePage />}


      {/* 1. Clean Home Page: Starts with big name, coordinate search & presets */}
      {activeTab === 'home' && (
        <HomePage
          onSearchCoordinates={handleSearchCoordinates}
          onSelectPreset={handleSelectPreset}
          onOpenFeed={() => setActiveTab('feed')}
          onOpenCatalogue={() => {
            setSelectedCatalogueCandidateId(null);
            setActiveTab('catalogue');
          }}
          onLaunchViewer={() => setActiveTab('viewer')}
        />
      )}

      {/* 2. Dedicated Community Verification Feed View */}
      {activeTab === 'feed' && (
        <div className="relative flex-1 overflow-y-auto bg-paper-950 p-3 sm:p-6 md:p-10 anim-fall select-none pb-20 sm:pb-10">
          {/* Subtle cosmic space hero backdrop */}
          <div
            aria-hidden
            className="absolute inset-0 bg-cover bg-center pointer-events-none opacity-20"
            style={{ backgroundImage: "url('/space-hero.jpg')" }}
          />
          <div aria-hidden className="absolute inset-0 bg-gradient-to-b from-black/60 via-paper-950/80 to-paper-950 pointer-events-none" />
          <div className="relative max-w-5xl mx-auto space-y-4 sm:space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-paper-800 gap-4">
              <div className="flex items-center gap-3">
                <div className="p-2 sm:p-2.5 rounded-xl bg-sky-400/10 border-2 border-sky-400/40 text-sky-400 shadow-[0_0_15px_rgba(56,189,248,0.2)] shrink-0">
                  <UserCheck className="w-5 h-5 sm:w-6 sm:h-6 stroke-[2.5]" />
                </div>
                <div>
                  <h1 className="text-lg sm:text-xl md:text-2xl font-bold font-mono text-white tracking-wide">
                    NASA Scientist & Community Verification Feed
                  </h1>
                  <p className="text-[11px] sm:text-xs text-paper-400 mt-0.5">
                    Peer-review flagged moving objects, inspect exact observation settings, and verify astrometric tracks.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setActiveTab('viewer')}
                className="btn-tactile w-full sm:w-auto px-4 py-2 rounded-xl border-2 border-black bg-emerald-400 hover:bg-emerald-300 text-gray-950 font-mono text-xs font-bold flex items-center justify-center gap-2 cursor-pointer self-start sm:self-auto shrink-0 shadow-[0_0_15px_rgba(16,185,129,0.3)]"
              >
                <Compass className="w-4 h-4 stroke-[2.5]" />
                <span>Open Sky Viewer</span>
              </button>
            </div>

            <VerifyScientistPanel
              onSelectVerificationTarget={handleSelectVerificationTarget}
              isCompact={false}
            />
          </div>
        </div>
      )}

      {/* 2.5 PlanetX Persistent Scientific Catalogue & Candidate Detail */}
      {activeTab === 'catalogue' && (
        selectedCatalogueCandidateId ? (
          <CandidateDetailPage
            candidateId={selectedCatalogueCandidateId}
            onBack={() => setSelectedCatalogueCandidateId(null)}
            onOpenSkyViewer={(nRa, nDec, candId) => {
              void handleSearchCoordinates(nRa, nDec);
              if (candId) setSelectedCandidateId(candId);
              setActiveTab('viewer');
            }}
            onOpenFeed={() => setActiveTab('feed')}
          />
        ) : (
          <CatalogueDashboard
            onSelectCandidate={(candId) => setSelectedCatalogueCandidateId(candId)}
            onOpenSkyViewer={(nRa, nDec, candId) => {
              void handleSearchCoordinates(nRa, nDec);
              if (candId) setSelectedCandidateId(candId);
              setActiveTab('viewer');
            }}
            onOpenFeed={() => setActiveTab('feed')}
          />
        )
      )}

      {/* 3. Dossier Report Page */}
      {activeTab === 'report' && (
        <DiscoveryReportPage
          candidate={activeCandidate}
          spectrumData={spectrumData}
          onBackToViewer={() => setActiveTab('viewer')}
        />
      )}

      {/* 4. Sky Viewport: Edge-to-Edge Celestial Canvas */}
      {activeTab === 'viewer' && (
        <div className={`flex flex-1 overflow-hidden relative anim-fall flex-col md:flex-row ${isEmbedMode ? 'h-screen' : 'h-[calc(100vh-3rem)]'}`}>
          {/* Left Control Panel: Desktop side-column, Mobile full-pane overlay */}
          {!isEmbedMode && (
          <div
            className={`${
              mobileViewerPane === 'controls'
                ? 'fixed inset-x-0 top-12 bottom-12 z-40 flex flex-col bg-paper-950 overflow-hidden anim-fall'
                : 'hidden md:flex'
            }`}
          >
            {/* Mobile Header Bar for Settings */}
            <div className="flex md:hidden items-center justify-between px-3.5 py-2.5 bg-paper-900 border-b border-paper-800 shrink-0">
              <div className="flex items-center gap-2 font-mono text-xs font-bold text-emerald-400">
                <Sliders className="w-4 h-4" />
                <span>Sky Viewer Settings & Calibration</span>
              </div>
              <button
                onClick={() => setMobileViewerPane('canvas')}
                className="btn-tactile px-3 py-1 rounded-lg border-2 border-black bg-emerald-400 text-gray-950 font-mono text-xs font-bold flex items-center gap-1 cursor-pointer"
              >
                <span>✕ Close & Return</span>
              </button>
            </div>

            <LeftControlPanel
              ra={ra}
              dec={dec}
              fov={fov}
              archiveSelection={archiveSelection}
              archiveInventory={archive.inventory}
              archiveInventoryError={archive.inventoryError}
              onUpdateCoords={(nRa, nDec, selection) => {
                void handleSearchCoordinates(nRa, nDec, undefined, selection);
                setMobileViewerPane('canvas');
              }}
              onUpdateFov={setFov}
              selectedArray={selectedArray}
              onSelectArray={handleSelectDetectorArray}
              subtractionMode={subtractionMode}
              onChangeSubtractionMode={setSubtractionMode}
              availableModes={availableImageModes(frames[activeFrameIndex])}
              overlays={overlays}
              onToggleOverlay={handleToggleOverlay}
              onRefreshCutout={handleRefreshCutout}
              viewMode={viewMode}
              searchStatus={searchStatus}
              activeCandidate={activeCandidate}
              liveCatalog={liveCatalog}
              isCatalogLoading={isCatalogLoading}
              onRefreshCatalog={() => setCatalogRefreshCounter((c) => c + 1)}
              currentPresetId={currentPresetId}
              frames={frames}
              className="h-full w-full"
            />
          </div>
          )}

          {/* Main Viewport: Canvas & Playback */}
          <main
            className={`flex-1 flex flex-col ${
              isEmbedMode
                ? 'h-screen'
                : 'h-[calc(100vh-6rem)] md:h-[calc(100vh-3rem)] pb-12 md:pb-0'
            } overflow-hidden relative ${
              mobileViewerPane === 'canvas' ? 'flex' : 'hidden md:flex'
            }`}
          >
            {isEmbedMode && (
              <div className="absolute top-2 left-2 z-30 bg-paper-950/90 border border-paper-800 rounded-lg px-2.5 py-1 text-[11px] font-mono text-paper-200 flex items-center gap-2 shadow-lg backdrop-blur-sm pointer-events-auto select-none">
                <span className="font-bold text-white">SPHEREx Sky Explorer</span>
                <span className="text-paper-500">•</span>
                <span className="text-emerald-400 font-semibold">{ra.toFixed(4)}°, {dec.toFixed(4)}°</span>
                <a
                  href={fullViewerUrl()}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-ochre-400 hover:text-ochre-300 underline font-bold ml-1 cursor-pointer"
                >
                  Open Full App ↗
                </a>
              </div>
            )}
            {archiveBrowsing ? <ArchiveObservationsPanel archive={archive} /> : <CanvasViewport
              frames={frames}
              activeFrameIndex={activeFrameIndex}
              candidates={candidatesList}
              selectedCandidateId={selectedCandidateId}
              onSelectCandidate={setSelectedCandidateId}
              overlays={overlays}
              subtractionMode={subtractionMode}
              onChangeSubtractionMode={setSubtractionMode}
              centerRa={ra}
              centerDec={dec}
              fov={fov}
              selectedArray={selectedArray}
              skippedNotice={skippedNotice}
              onClearSkippedNotice={clearSkippedNotice}
              isScientistMode={viewMode === 'scientist'}
              mlAnalysisStatus={mlAnalysisStatus}
              loadStatus={searchStatus}
              liveCatalog={liveCatalog}
              onOpenMlInsights={() => {
                setDrawerControlledTab('ai');
                if (typeof window !== 'undefined' && window.innerWidth < 1024) {
                  setMobileViewerPane('telemetry');
                }
              }}
            />}

            {!archiveBrowsing && <MoviePlayerControls
              frames={frames}
              activeFrameIndex={activeFrameIndex}
              onSelectFrame={setActiveFrameIndex}
              isPlaying={isPlaying}
              onTogglePlay={() => setIsPlaying((p) => !p)}
              fps={fps}
              onChangeFps={setFps}
              blinkMode={blinkMode}
              onToggleBlinkMode={() => setBlinkMode((b) => !b)}
              onStepForward={stepForward}
              onStepBackward={stepBackward}
            />}
          </main>

          {/* Right Drawer: Desktop expandable column, Mobile full-pane overlay */}
          {!isEmbedMode && !archiveBrowsing && (
          <div
            className={`h-full ${
              mobileViewerPane === 'telemetry'
                ? 'fixed inset-x-0 top-12 bottom-12 z-40 flex flex-col bg-paper-950 overflow-hidden anim-fall lg:static lg:inset-auto lg:top-auto lg:bottom-auto lg:z-20 lg:flex'
                : 'hidden lg:flex'
            }`}
          >
            {/* Mobile Header Bar for Triage */}
            <div className="flex md:hidden items-center justify-between px-3.5 py-2.5 bg-paper-900 border-b border-paper-800 shrink-0">
              <div className="flex items-center gap-2 font-mono text-xs font-bold text-emerald-400">
                <Sparkles className="w-4 h-4" />
                <span>Candidate Triage & AI Telemetry</span>
              </div>
              <button
                onClick={() => setMobileViewerPane('canvas')}
                className="btn-tactile px-3 py-1 rounded-lg border-2 border-black bg-emerald-400 text-gray-950 font-mono text-xs font-bold flex items-center gap-1 cursor-pointer"
              >
                <span>✕ Close & Return</span>
              </button>
            </div>

            <RightDrawer
              frames={frames}
              activeFrameIndex={activeFrameIndex}
              onSelectFrame={setActiveFrameIndex}
              candidates={candidatesList}
              selectedCandidateId={activeCandidate?.id ?? null}
              onSelectCandidate={setSelectedCandidateId}
              candidate={activeCandidate}
              spectrumData={spectrumData}
              onUpdateCandidateClassification={handleUpdateCandidateClassification}
              onOpenDiscoveryReport={() => setActiveTab('report')}
              onOpenFeed={() => setActiveTab('feed')}
              onOpenCatalogue={(candId) => {
                if (candId) {
                  const norm = candId.toLowerCase();
                  if (norm.startsWith('px-')) setSelectedCatalogueCandidateId(candId.toUpperCase());
                  else if (norm.includes('atlas') || norm.includes('3i')) setSelectedCatalogueCandidateId('PX-000001');
                  else if (norm.includes('vesta') || norm.includes('4')) setSelectedCatalogueCandidateId('PX-000002');
                  else if (norm.includes('barnard')) setSelectedCatalogueCandidateId('PX-000003');
                  else if (norm.includes('wise') || norm.includes('0855')) setSelectedCatalogueCandidateId('PX-000004');
                  else setSelectedCatalogueCandidateId(candId);
                } else {
                  setSelectedCatalogueCandidateId(null);
                }
                setActiveTab('catalogue');
              }}
              isScientistMode={viewMode === 'scientist'}
              ra={ra}
              dec={dec}
              fov={fov}
              selectedArray={selectedArray}
              subtractionMode={subtractionMode}
              controlledTab={drawerControlledTab}
              onTabChange={setDrawerControlledTab}
              mlAnalysisStatus={mlAnalysisStatus}
              currentPresetId={currentPresetId}
              className="h-full w-full"
            />
          </div>
          )}

          {/* Mobile Bottom Dock (< md screens) */}
          {!isEmbedMode && (
          <nav className="md:hidden fixed bottom-0 inset-x-0 h-12 bg-paper-950/95 backdrop-blur border-t border-paper-800 z-40 flex items-center justify-around px-2">
            <button
              onClick={() => setMobileViewerPane('canvas')}
              className={`flex flex-col items-center justify-center flex-1 py-1 text-[10px] font-mono transition-colors ${
                mobileViewerPane === 'canvas'
                  ? 'text-emerald-400 font-bold'
                  : 'text-paper-400 hover:text-paper-200'
              }`}
            >
              <Compass className="w-4 h-4 mb-0.5" />
              <span>Sky View</span>
            </button>
            <button
              onClick={() => setMobileViewerPane(archiveBrowsing ? 'canvas' : 'telemetry')}
              className={`flex flex-col items-center justify-center flex-1 py-1 text-[10px] font-mono transition-colors ${
                mobileViewerPane === 'telemetry'
                  ? 'text-emerald-400 font-bold'
                  : 'text-paper-400 hover:text-paper-200'
              }`}
            >
              <Sparkles className="w-4 h-4 mb-0.5" />
              <span>{archiveBrowsing ? 'Archive results' : 'Triage & AI'}</span>
            </button>
            <button
              onClick={() => setMobileViewerPane('controls')}
              className={`flex flex-col items-center justify-center flex-1 py-1 text-[10px] font-mono transition-colors ${
                mobileViewerPane === 'controls'
                  ? 'text-emerald-400 font-bold'
                  : 'text-paper-400 hover:text-paper-200'
              }`}
            >
              <Sliders className="w-4 h-4 mb-0.5" />
              <span>Controls</span>
            </button>
          </nav>
          )}
        </div>
      )}

      {/* Embed Modal */}
      <EmbedModal
        isOpen={isEmbedModalOpen}
        onClose={() => setIsEmbedModalOpen(false)}
        ra={ra}
        dec={dec}
        fov={fov}
        selectedArray={selectedArray}
        subtractionMode={subtractionMode}
        activeFrameIndex={activeFrameIndex}
        candidateId={selectedCandidateId}
        presetId={currentPresetId}
        archiveSelection={archiveSelection}
      />

      {/* Choose Your View Assessment Pop-up Modal */}
      <ChooseYourViewModal
        isOpen={isViewModalOpen}
        onClose={() => setIsViewModalOpen(false)}
        currentMode={viewMode}
        onSelectMode={handleSetViewMode}
      />

      {/* Guided Beginner Sky Viewer Tutorial */}
      <GuidedTutorialOverlay
        isOpen={isTutorialActive && activeTab === 'viewer'}
        step={tutorialStep}
        onNext={() => setTutorialStep((s) => Math.min(s + 1, 6))}
        onPrev={() => setTutorialStep((s) => Math.max(s - 1, 0))}
        onClose={() => {
          setIsTutorialActive(false);
          setDrawerControlledTab(null);
          setTutorialStep(0);
        }}
        onChangeMobilePane={(pane) => setMobileViewerPane(pane)}
        onSelectDrawerTab={(tab) => setDrawerControlledTab(tab)}
      />
    </div>
  );
}

export default App;
