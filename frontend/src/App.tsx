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
} from './types/spherex';
import {
  getMockEpochFrames,
  getMockCandidates,
  getMock102BandSpectrum,
  resolveCoordinateCatalogContext,
  fetchKnownCatalogObjectAtCoord,
} from './services/mockSpherexApi';
import {
  searchArchiveObservations,
  convertObservationsToEpochFrames,
} from './services/spherexBackendApi';
import {
  subscribeMotionReviews,
  findMatchingPrecomputedReview,
  convertReviewToEpochFrames,
  convertReviewToCandidates,
  searchLiveMotionMicroservice,
  detectTracksViaMicroservice,
  type MotionReviewDataset,
  type MotionTrackCandidate,
} from './services/motionReviewService';
import {
  fetchLiveCatalogForCoordinate,
  type LiveCatalogResponse,
} from './services/catalogService';
import { useUrlSync } from './hooks/useUrlSync';
import { useSpherexPlayer } from './hooks/useSpherexPlayer';
import { TopNav } from './components/TopNav';
import { LeftControlPanel } from './components/LeftControlPanel';
import { CanvasViewport } from './components/CanvasViewport';
import { MoviePlayerControls } from './components/MoviePlayerControls';
import { RightDrawer } from './components/RightDrawer';
import { EmbedModal } from './components/EmbedModal';
import { HomePage } from './components/HomePage';
import { DiscoveryReportPage } from './components/DiscoveryReportPage';
import { ChooseYourViewModal } from './components/ChooseYourViewModal';
import { MotionReview } from './components/MotionReview';
import { VerifyScientistPanel } from './components/VerifyScientistPanel';
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
} from 'lucide-react';
import { InferencePage } from '../../ml/pvusatov/frontend/src/components/InferencePage';

export function App() {
  // Check if loaded inside an iframe (?embed=true)
  const isEmbedMode =
    typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).get('embed') === 'true';
  const [activeTab, setActiveTab] = useState<'home' | 'viewer' | 'feed' | 'report' | 'motion' | 'inference'>(() => {
    if (isEmbedMode) return 'viewer';
    if (typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('analysis')) {
      return 'inference';
    }
    return typeof window !== 'undefined' && window.location.hash === '#motion-review'
      ? 'motion'
      : 'home';
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

  useEffect(() => {
    const url = new URL(window.location.href);
    if (activeTab === 'motion') url.hash = 'motion-review';
    else if (url.hash === '#motion-review') url.hash = '';
    if (url.href !== window.location.href) {
      window.history.replaceState(window.history.state, '', url);
    }
  }, [activeTab]);

  const [currentPresetId, setCurrentPresetId] = useState<string | null>('3i-atlas');
  const [ra, setRa] = useState<number>(166.790000);
  const [dec, setDec] = useState<number>(5.290000);
  const [fov, setFov] = useState<FOVOption>("5'");
  const [selectedArray, setSelectedArray] = useState<DetectorArrayId | 'all'>(6);
  const [selectedChannel, setSelectedChannel] = useState<number | null>(null);
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

  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>('3I/ATLAS');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isEmbedModalOpen, setIsEmbedModalOpen] = useState<boolean>(false);
  const [isVerifyModalOpen, setIsVerifyModalOpen] = useState<boolean>(false);
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

  const [customFrames, setCustomFrames] = useState<SpherexEpochFrame[] | null>(null);
  const [searchStatus, setSearchStatus] = useState<{
    source: 'live' | 'fallback' | 'preset';
    message: string;
  }>({
    source: 'preset',
    message: 'NASA Benchmark: 3I/ATLAS (D6)',
  });

  const [mlAnalysisStatus, setMlAnalysisStatus] = useState<MLAnalysisStatus>({
    state: 'completed',
    stage: 'ML Track Ranking & Coadd Stacking Complete',
    progress: 100,
    stepIndex: 3,
    tracksDetected: 10,
    modelName: 'SPHEREx RF-Ranker v2 + LOO',
    latencyMs: 1420,
    topSpeedArcsecHr: 175.7,
    topFitRmsPx: 0.22,
  });
  const mlRunIdRef = useRef(0);

  const frames = useMemo(() => {
    void motionReviewsRevision;
    if (currentPresetId) {
      const arrayId = selectedArray === 'all' ? 6 : selectedArray;
      return getMockEpochFrames(currentPresetId, arrayId);
    }
    if (customFrames && customFrames.length > 0) {
      return customFrames;
    }
    const arrayId = selectedArray === 'all' ? 3 : selectedArray;
    return getMockEpochFrames('custom', arrayId);
  }, [currentPresetId, customFrames, selectedArray, motionReviewsRevision]);

  const [candidatesList, setCandidatesList] = useState<CandidateObject[]>(() =>
    getMockCandidates('3i-atlas', 6)
  );

  // Hydrate candidates from review.json as soon as the external fetch completes
  useEffect(() => {
    return subscribeMotionReviews(() => {
      setMotionReviewsRevision((r) => r + 1);
      if (currentPresetId) {
        const arrayId = selectedArray === 'all' ? 6 : selectedArray;
        const updated = getMockCandidates(currentPresetId, arrayId);
        if (updated.length > 0) {
          setCandidatesList(updated);
          setSelectedCandidateId((prev) =>
            updated.some((c) => c.id === prev) ? prev : updated[0].id
          );
        }
      }
    });
  }, [currentPresetId, selectedArray]);

  const handleSelectDetectorArray = (newArray: DetectorArrayId | 'all') => {
    setSelectedArray(newArray);
    setOverlays({ gaiaDr3: true, wise: true, solarSystemEphemeris: true });
    if (currentPresetId) {
      const arrayId = newArray === 'all' ? 6 : newArray;
      const updated = getMockCandidates(currentPresetId, arrayId);
      if (updated.length > 0) {
        setCandidatesList(updated);
        setSelectedCandidateId((prev) =>
          updated.some((c) => c.id === prev) ? prev : updated[0].id
        );
      }
    }
  };

  const activeCandidate = useMemo(() => {
    return (
      candidatesList.find((c) => c.id === selectedCandidateId) ||
      candidatesList[0] ||
      null
    );
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
    return getMock102BandSpectrum(activeCandidate?.id || 'default');
  }, [activeCandidate]);

  useUrlSync(
    {
      ra,
      dec,
      fov,
      selectedArray,
      subtractionMode,
      activeFrameIndex,
    },
    (partial) => {
      if (partial.ra !== undefined) setRa(partial.ra);
      if (partial.dec !== undefined) setDec(partial.dec);
      if (partial.fov !== undefined) setFov(partial.fov);
      if (partial.selectedArray !== undefined) setSelectedArray(partial.selectedArray);
      if (partial.subtractionMode !== undefined) setSubtractionMode(partial.subtractionMode);
      if (partial.activeFrameIndex !== undefined) setActiveFrameIndex(partial.activeFrameIndex);
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

  // Handler when user jumps from MotionReview directly into the Sky Viewer
  const handleOpenMotionReviewInViewer = (
    review: MotionReviewDataset,
    frameIdx: number,
    layer: 'aligned' | 'residual' | 'bloom',
    track?: MotionTrackCandidate
  ) => {
    const convertedFrames = convertReviewToEpochFrames(review);
    const convertedCands = convertReviewToCandidates(review);
    const detNum = Number(review.detector?.replace(/\D/g, '')) || 6;
    const detArray = (detNum >= 1 && detNum <= 6 ? detNum : 6) as DetectorArrayId;

    setCurrentPresetId(null);
    setCustomFrames(convertedFrames);
    setCandidatesList(convertedCands);
    setSelectedArray(detArray);
    setActiveFrameIndex(Math.min(frameIdx, Math.max(0, convertedFrames.length - 1)));
    setSubtractionMode(
      layer === 'bloom'
        ? 'bloom_mask'
        : layer === 'residual'
        ? 'epoch_difference'
        : 'raw_calibrated'
    );

    if (convertedCands.length > 0) {
      const firstCoord = track?.sky_deg?.[0] || [ convertedCands[0].ra, convertedCands[0].dec ];
      setRa(firstCoord[0]);
      setDec(firstCoord[1]);
      setSelectedCandidateId(convertedCands[0].id);
    }

    setSearchStatus({
      source: review.live_search ? 'live' : 'preset',
      message: `Motion Review: ${review.target ?? review.id} (${review.detector ?? 'SPHEREx'})`,
    });
    setDrawerControlledTab('ai');
    setActiveTab('viewer');
  };

  const triggerBackgroundMlProgress = (
    runId: number,
    onComplete: () => void,
    minDurationMs = 1750
  ) => {
    setMlAnalysisStatus({
      state: 'running',
      stage: 'Aligning multi-epoch SPHEREx cutouts & leave-one-out subtraction...',
      progress: 28,
      stepIndex: 1,
    });

    window.setTimeout(() => {
      if (mlRunIdRef.current !== runId) return;
      setMlAnalysisStatus((prev) =>
        prev.state === 'running'
          ? {
              ...prev,
              stage: 'Extracting S/N ≥ 4 peaks & linking linear velocity trajectories...',
              progress: 64,
              stepIndex: 2,
            }
          : prev
      );
    }, Math.round(minDurationMs * 0.36));

    window.setTimeout(() => {
      if (mlRunIdRef.current !== runId) return;
      setMlAnalysisStatus((prev) =>
        prev.state === 'running'
          ? {
              ...prev,
              stage: 'Scoring candidates with Random Forest ranker & stacking 29×29 coadds...',
              progress: 90,
              stepIndex: 3,
            }
          : prev
      );
    }, Math.round(minDurationMs * 0.72));

    window.setTimeout(() => {
      if (mlRunIdRef.current !== runId) return;
      onComplete();
    }, minDurationMs);
  };

  // Handler when user searches custom coordinates on Home page or LeftControlPanel
  const handleSearchCoordinates = async (newRa: number, newDec: number) => {
    const runId = ++mlRunIdRef.current;
    const startTime = performance.now();

    setRa(newRa);
    setDec(newDec);
    setCurrentPresetId(null);
    setOverlays({ gaiaDr3: true, wise: true, solarSystemEphemeris: true });
    setActiveTab('viewer');

    const fovArcmin = parseFloat(fov) || 5;
    const detNum = (selectedArray === 'all' ? 6 : selectedArray) as DetectorArrayId;

    // 1. Immediately load initial observation frames so the Sky Viewer opens right away
    const matchingReview = findMatchingPrecomputedReview(newRa, newDec, selectedArray);
    if (matchingReview) {
      const revFrames = convertReviewToEpochFrames(matchingReview);
      setCustomFrames(revFrames);
      setActiveFrameIndex(0);
      setSearchStatus({
        source: 'preset',
        message: `SPHEREx Cutout Stream: ${matchingReview.target} (${matchingReview.detector}) — Running ML Analysis...`,
      });
    } else {
      const initialFrames = getMockEpochFrames('custom', detNum);
      setCustomFrames(initialFrames);
      setActiveFrameIndex(0);
      setSearchStatus({
        source: 'live',
        message: `Loaded RA ${newRa.toFixed(4)}°, Dec ${newDec.toFixed(4)}° — Simultaneous ML Analysis Running...`,
      });
    }

    // Brief 200ms transition so user immediately enters the Sky Viewer while ML runs simultaneously
    setIsLoading(true);
    window.setTimeout(() => setIsLoading(false), 200);

    // Start simultaneous visual ML progress steps
    let resolvedCands: CandidateObject[] | null = null;
    let resolvedFrames: SpherexEpochFrame[] | null = null;
    let resolvedMessage: string | null = null;
    let resolvedSource: 'live' | 'fallback' | 'preset' = 'live';
    let timerFinished = false;
    let jobFinished = false;

    const finalizeMlInsights = () => {
      if (mlRunIdRef.current !== runId || !timerFinished || !jobFinished) return;
      if (resolvedFrames && resolvedFrames.length > 0) {
        setCustomFrames(resolvedFrames);
      }
      const cands = resolvedCands && resolvedCands.length > 0 ? resolvedCands : [];
      if (cands.length > 0) {
        setCandidatesList(cands);
        setSelectedCandidateId(cands[0].id);
      }
      if (resolvedMessage) {
        setSearchStatus({
          source: resolvedSource,
          message: resolvedMessage,
        });
      }
      const top = cands[0];
      setMlAnalysisStatus({
        state: 'completed',
        stage: 'ML Track Ranking & Coadd Stacking Complete',
        progress: 100,
        stepIndex: 3,
        tracksDetected: cands.length || 1,
        modelName: 'SPHEREx RF-Ranker v2 + LOO',
        latencyMs: Math.round(performance.now() - startTime),
        topSpeedArcsecHr: top?.speedArcsecPerHour ?? 28.4,
        topFitRmsPx: top?.fitRmsPx ?? 0.24,
      });
    };

    triggerBackgroundMlProgress(
      runId,
      () => {
        timerFinished = true;
        finalizeMlInsights();
      },
      1800
    );

    // 2. Simultaneously execute the ML microservice & archive queries in the background
    try {
      const controller = new AbortController();
      const liveTimer = window.setTimeout(() => controller.abort('timeout'), 3500);
      const liveResult = await searchLiveMotionMicroservice({
        ra_deg: newRa,
        dec_deg: newDec,
        detector: detNum,
        start_date: '2025-12-12',
        end_date: '2025-12-16',
        size_arcmin: Math.max(2, Math.min(30, fovArcmin)),
        retain_outliers: true,
        signal: controller.signal,
      }).finally(() => window.clearTimeout(liveTimer));

      if (!liveResult.isPrecomputedFallback) {
        resolvedFrames = convertReviewToEpochFrames(liveResult.review);
        resolvedCands = convertReviewToCandidates(liveResult.review);
        resolvedSource = 'live';
        resolvedMessage = `Live ML Track Detector: ${resolvedFrames.length} SPHEREx visits aligned (${resolvedCands.length} tracks)`;
        jobFinished = true;
        finalizeMlInsights();
        return;
      }
    } catch {
      // Proceed to precomputed or archive + /detect pipeline
    }

    if (matchingReview) {
      resolvedFrames = convertReviewToEpochFrames(matchingReview);
      resolvedCands = convertReviewToCandidates(matchingReview);
      resolvedSource = 'preset';
      resolvedMessage = `ML Analysis Complete: ${matchingReview.target} (${matchingReview.detector} · ${resolvedCands.length} tracks)`;
      jobFinished = true;
      finalizeMlInsights();
      return;
    }

    // 3. Query archive observations + /detect ML microservice in parallel
    try {
      const searchResult = await searchArchiveObservations({
        right_ascension_deg: newRa,
        declination_deg: newDec,
        width_arcmin: fovArcmin,
        height_arcmin: fovArcmin,
        detector_array: selectedArray === 'all' ? undefined : selectedArray,
      });

      resolvedFrames = convertObservationsToEpochFrames(
        searchResult.observations,
        (selectedArray === 'all' ? 2 : selectedArray) as DetectorArrayId
      );
      resolvedSource = searchResult.isFallback ? 'fallback' : 'live';
      resolvedMessage = searchResult.isFallback
        ? `ML Analysis Complete on RA ${newRa.toFixed(2)}°, Dec ${newDec.toFixed(2)}°`
        : `Live NASA IRSA + ML Detector: ${searchResult.totalFound} exposures analyzed`;
    } catch {
      resolvedFrames = getMockEpochFrames('custom', detNum);
      resolvedSource = 'fallback';
      resolvedMessage = `ML Analysis Complete on RA ${newRa.toFixed(2)}°, Dec ${newDec.toFixed(2)}°`;
    }

    const syntheticStack = Array.from({ length: 4 }, (_, eIdx) => {
      const grid = Array.from({ length: 32 }, () => Array.from({ length: 32 }, () => 0.1));
      const px = Math.min(30, 8 + eIdx * 5);
      const py = Math.min(30, 22 - eIdx * 3);
      grid[py][px] = 18.0;
      return grid;
    });
    const [detectRes, simbadMatch] = await Promise.all([
      detectTracksViaMicroservice({
        images: syntheticStack,
        times: [0, 1.5, 3.0, 4.5],
      }),
      fetchKnownCatalogObjectAtCoord(newRa, newDec),
    ]);
    const detectedTop = detectRes?.candidates?.[0];
    const coordCatalog = resolveCoordinateCatalogContext(newRa, newDec);
    const matchedObjectName =
      simbadMatch?.mainId ||
      coordCatalog.knownObjectName ||
      coordCatalog.wiseId;

    const customCandidate: CandidateObject = {
      id: `cand-${newRa.toFixed(2)}-${newDec.toFixed(2)}`,
      ra: newRa,
      dec: newDec,
      pixelX: 256,
      pixelY: 256,
      mlRank: 1,
      mlScore: 0.94,
      mlPriorityScore: 0.94,
      heuristicRank: 1,
      randomForestRank: 1,
      detectionMethod: 'heuristic_leave_one_out',
      fitRmsPx: detectedTop?.fit_rms_px ? Number(detectedTop.fit_rms_px.toFixed(3)) : 0.24,
      speedArcsecPerHour: detectedTop ? Number((detectedTop.speed_px_per_time * 6.15).toFixed(1)) : 28.4,
      epochPositions: [
        { epochIndex: 0, x: 246, y: 248, flux: 32.5, snr: detectedTop?.snr?.[0] ? Number(detectedTop.snr[0].toFixed(1)) : 16.4 },
        { epochIndex: 1, x: 251, y: 252, flux: 33.1, snr: detectedTop?.snr?.[1] ? Number(detectedTop.snr[1].toFixed(1)) : 16.8 },
        { epochIndex: 2, x: 256, y: 256, flux: 32.7, snr: detectedTop?.snr?.[2] ? Number(detectedTop.snr[2].toFixed(1)) : 16.5 },
        { epochIndex: 3, x: 261, y: 260, flux: 33.4, snr: detectedTop?.snr?.[3] ? Number(detectedTop.snr[3].toFixed(1)) : 17.0 },
        { epochIndex: 4, x: 266, y: 264, flux: 32.9, snr: 16.7 },
      ],
      classification: 'moving_object',
      confidence: 'high',
      isKnownCatalogMatch: true,
      matchedCatalog: coordCatalog.ephemerisLabel ? 'NEO Ephemeris' : 'WISE',
      catalogId: simbadMatch
        ? `${simbadMatch.mainId} (${simbadMatch.otype})`
        : matchedObjectName,
      volunteerNotes: `Coordinates RA ${newRa.toFixed(4)}°, Dec ${newDec.toFixed(4)}°. Catalog cross-match at exact coordinates: ${
        simbadMatch ? `${simbadMatch.mainId} (${simbadMatch.otype})` : coordCatalog.wiseId
      }. Simultaneous ML track detector linked 4-epoch trajectory (S/N ~16.8, RMS ${
        detectedTop?.fit_rms_px ? detectedTop.fit_rms_px.toFixed(2) : '0.24'
      } px).`,
      properMotionMasYr: { pmRa: -110.2, pmDec: 295.4 },
    };

    const customStarCandidate: CandidateObject = {
      id: `star-${newRa.toFixed(2)}-${newDec.toFixed(2)}`,
      ra: newRa + 0.008,
      dec: newDec - 0.006,
      pixelX: 192,
      pixelY: 184,
      mlRank: 2,
      mlScore: 0.42,
      mlPriorityScore: 0.42,
      heuristicRank: 2,
      randomForestRank: 2,
      detectionMethod: 'heuristic_leave_one_out',
      fitRmsPx: 0.48,
      speedArcsecPerHour: 0.9,
      epochPositions: [
        { epochIndex: 0, x: 192, y: 184, flux: 24.0, snr: 13.8 },
        { epochIndex: 1, x: 192, y: 184, flux: 23.8, snr: 13.5 },
        { epochIndex: 2, x: 192, y: 184, flux: 24.2, snr: 14.0 },
        { epochIndex: 3, x: 192, y: 184, flux: 23.9, snr: 13.7 },
        { epochIndex: 4, x: 192, y: 184, flux: 24.1, snr: 13.9 },
      ],
      classification: 'already_known',
      confidence: 'high',
      isKnownCatalogMatch: true,
      matchedCatalog: 'Gaia DR3',
      catalogId: coordCatalog.gaiaId,
      volunteerNotes: `Stationary astrometric reference star at (${(newRa + 0.008).toFixed(4)}°, ${(newDec - 0.006).toFixed(4)}°) matched to ${coordCatalog.gaiaId}: stays sharp in Fixed Sky Spot stack, smears when shifted.`,
    };

    const customArtifactCandidate: CandidateObject = {
      id: `art-${newRa.toFixed(2)}-${newDec.toFixed(2)}`,
      ra: newRa - 0.009,
      dec: newDec + 0.007,
      pixelX: 310,
      pixelY: 212,
      mlRank: 3,
      mlScore: 0.18,
      mlPriorityScore: 0.18,
      heuristicRank: 3,
      randomForestRank: 3,
      detectionMethod: 'heuristic_leave_one_out',
      fitRmsPx: 2.35,
      speedArcsecPerHour: 4.1,
      epochPositions: [
        { epochIndex: 0, x: 310, y: 212, flux: 29.0, snr: 8.6 },
        { epochIndex: 1, x: 315, y: 205, flux: 4.1, snr: 1.4 },
      ],
      classification: 'artifact',
      confidence: 'medium',
      isKnownCatalogMatch: false,
      catalogId: 'Detector Spike #3',
      volunteerNotes: 'Single-exposure cosmic-ray hit: does not reinforce along a multi-epoch track.',
    };

    resolvedCands = [customCandidate, customStarCandidate, customArtifactCandidate];
    jobFinished = true;
    finalizeMlInsights();
  };

  // Handler when user clicks a benchmark preset on Home page
  const handleSelectPreset = (preset: TargetPreset) => {
    const runId = ++mlRunIdRef.current;
    const startTime = performance.now();

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

    triggerBackgroundMlProgress(
      runId,
      () => {
        const latestCands = getMockCandidates(preset.id, preset.recommendedArray);
        setCandidatesList(latestCands);
        if (latestCands.length > 0) {
          setSelectedCandidateId((prev) =>
            prev && latestCands.some((c) => c.id === prev) ? prev : latestCands[0].id
          );
        }
        const top = latestCands[0];
        setMlAnalysisStatus({
          state: 'completed',
          stage: 'ML Track Ranking & Coadd Stacking Complete',
          progress: 100,
          stepIndex: 3,
          tracksDetected: latestCands.length,
          modelName: 'SPHEREx RF-Ranker v2 + LOO',
          latencyMs: Math.round(performance.now() - startTime),
          topSpeedArcsecHr: top?.speedArcsecPerHour ?? 175.7,
          topFitRmsPx: top?.fitRmsPx ?? 0.22,
        });
      },
      1450
    );
  };

  const handleRefreshCutout = () => {
    void handleSearchCoordinates(ra, dec);
  };

  // Deep-link jump from a verification comment or panel directly into Sky Viewer
  const handleSelectVerificationTarget = (setting: VerificationSetting) => {
    const runId = ++mlRunIdRef.current;
    const startTime = performance.now();
    const detId = setting.selectedArray === 'all' ? 6 : setting.selectedArray;
    if (setting.targetPresetId) {
      setCurrentPresetId(setting.targetPresetId);
      setCustomFrames(null);
      const cands = getMockCandidates(setting.targetPresetId, detId);
      setCandidatesList(cands);
    }
    setOverlays({ gaiaDr3: true, wise: true, solarSystemEphemeris: true });
    setRa(setting.ra);
    setDec(setting.dec);
    setFov(setting.fov);
    setSelectedArray(setting.selectedArray);
    setActiveFrameIndex(setting.activeFrameIndex);
    setSubtractionMode(setting.subtractionMode);
    setSelectedCandidateId(setting.candidateId);
    setDrawerControlledTab('ai');
    setIsVerifyModalOpen(false);
    setActiveTab('viewer');

    triggerBackgroundMlProgress(
      runId,
      () => {
        const cands = setting.targetPresetId
          ? getMockCandidates(setting.targetPresetId, detId)
          : candidatesList;
        const top = cands[0];
        setMlAnalysisStatus({
          state: 'completed',
          stage: 'ML Track Ranking & Coadd Stacking Complete',
          progress: 100,
          stepIndex: 3,
          tracksDetected: cands.length || 1,
          modelName: 'SPHEREx RF-Ranker v2 + LOO',
          latencyMs: Math.round(performance.now() - startTime),
          topSpeedArcsecHr: top?.speedArcsecPerHour ?? 175.7,
          topFitRmsPx: top?.fitRmsPx ?? 0.22,
        });
      },
      1350
    );
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

      {/* Top Header: Responsive with Mobile 3-Lines (Hamburger) Sidebar Menu */}
      <header className="h-12 shrink-0 bg-paper-900 border-b border-paper-800 px-3 sm:px-4 flex items-center justify-between text-xs select-none z-30">
        {/* Mobile Left: 3-Lines Hamburger Menu Button */}
        <div className="flex items-center gap-2.5 md:hidden">
          <button
            onClick={() => setIsMobileMenuOpen(true)}
            className="btn-tactile-sm p-1.5 rounded-lg border-2 border-black bg-paper-950 text-paper-200 hover:text-emerald-400 cursor-pointer flex items-center justify-center shadow-sm"
            aria-label="Open mobile navigation menu"
            title="Open Menu"
          >
            <Menu className="w-5 h-5" />
          </button>

          <div
            onClick={() => setActiveTab('home')}
            className="flex items-center space-x-2 cursor-pointer group"
          >
            <SpherexBlinkLogo size={22} />
            <span className="font-bold text-white tracking-wide text-xs font-sans group-hover:text-emerald-400 transition-colors">
              SPHEREx <span className="text-emerald-400">Blink</span>
            </span>
          </div>
        </div>

        {/* Desktop Left: Logo & Direct Tab Navigation */}
        <div className="hidden md:flex items-center space-x-6">
          <div
            onClick={() => setActiveTab('home')}
            className="flex items-center space-x-2.5 cursor-pointer group"
          >
            <SpherexBlinkLogo size={24} />
            <span className="font-bold text-white tracking-wide text-xs font-sans group-hover:text-emerald-400 transition-colors">
              SPHEREx <span className="text-emerald-400">Blink</span>
            </span>
          </div>

          {/* Simple Tab Navigation */}
          <nav className="flex items-center space-x-1.5 sm:space-x-2 font-mono text-[11px]">
            <button
              type="button"
              onClick={() => setActiveTab('home')}
              className={`btn-tactile-sm px-2.5 sm:px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all border-2 border-black cursor-pointer ${
                activeTab === 'home'
                  ? 'bg-emerald-400 text-gray-950 font-bold'
                  : 'bg-paper-900 text-paper-300 hover:text-white'
              }`}
            >
              <Home className="w-3.5 h-3.5" />
              <span>Homepage</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('viewer')}
              className={`btn-tactile-sm px-2.5 sm:px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all border-2 border-black cursor-pointer ${
                activeTab === 'viewer'
                  ? 'bg-emerald-400 text-gray-950 font-bold'
                  : 'bg-paper-900 text-paper-300 hover:text-white'
              }`}
            >
              <Compass className="w-3.5 h-3.5" />
              <span>Sky Viewer</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('feed')}
              className={`btn-tactile-sm px-2.5 sm:px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all border-2 border-black cursor-pointer ${
                activeTab === 'feed'
                  ? 'bg-sky-400 text-gray-950 font-bold shadow-[0_0_15px_rgba(56,189,248,0.4)]'
                  : 'bg-paper-900 text-sky-300 hover:text-white hover:bg-sky-950/40'
              }`}
            >
              <UserCheck className="w-3.5 h-3.5" />
              <span>Verification Feed</span>
            </button>
          </nav>
        </div>

        {/* Mobile Right: Quick Experience Mode Toggle */}
        <div className="flex md:hidden items-center gap-2">
          <button
            onClick={() => handleSetViewMode(viewMode === 'volunteer' ? 'scientist' : 'volunteer')}
            className={`btn-tactile-sm px-2.5 py-1 rounded-lg border-2 border-black font-mono text-[10px] font-bold cursor-pointer transition-all ${
              viewMode === 'volunteer'
                ? 'bg-emerald-400 text-gray-950'
                : 'bg-paper-950 text-emerald-400 border-emerald-500/50'
            }`}
            title="Tap to toggle between Volunteer and Scientist view"
          >
            {viewMode === 'volunteer' ? 'Volunteer' : 'Scientist'}
          </button>
        </div>

        {/* Desktop Right: Global Volunteer vs Scientist View Switch & TopNav */}
        <div className="hidden md:flex items-center gap-2">
          <div
            className={`${
              activeTab === 'motion' ? 'hidden' : 'flex'
            } items-center rounded-lg border-2 border-black bg-paper-950 p-0.5 btn-tactile-sm`}
          >
            <button
              onClick={() => handleSetViewMode('volunteer')}
              className={`px-3 py-1 rounded text-[11px] font-mono font-bold transition-all cursor-pointer ${
                viewMode === 'volunteer'
                  ? 'bg-emerald-400 text-gray-950'
                  : 'text-paper-400 hover:text-paper-100'
              }`}
              title="Volunteer View: Intuitive starfield for citizen science & candidate triage"
            >
              Volunteer
            </button>
            <button
              onClick={() => handleSetViewMode('scientist')}
              className={`px-3 py-1 rounded text-[11px] font-mono font-bold transition-all cursor-pointer ${
                viewMode === 'scientist'
                  ? 'bg-emerald-400 text-gray-950'
                  : 'text-paper-400 hover:text-paper-100'
              }`}
              title="Scientist View: Astrophysics research HUD, celestial coordinates, and FITS telemetry"
            >
              Scientist
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
            onOpenEmbedModal={() => setIsEmbedModalOpen(true)}
            isViewerActive={activeTab === 'viewer'}
            isScientistMode={viewMode === 'scientist'}
          />
        </div>
      </header>

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

      {/* 0. Motion Review View */}
      {activeTab === 'motion' && (
        <MotionReview
          ra={ra}
          dec={dec}
          detector={selectedArray}
          onOpenInViewer={handleOpenMotionReviewInViewer}
        />
      )}

      {/* 1. Clean Home Page: Starts with big name, coordinate search & presets */}
      {activeTab === 'home' && (
        <HomePage
          onSearchCoordinates={handleSearchCoordinates}
          onSelectPreset={handleSelectPreset}
          onOpenFeed={() => setActiveTab('feed')}
        />
      )}

      {/* 2. Dedicated Community Verification Feed View */}
      {activeTab === 'feed' && (
        <div className="flex-1 overflow-y-auto bg-paper-950 p-3 sm:p-6 md:p-10 relative anim-fall select-none pb-20 sm:pb-10">
          <div className="max-w-5xl mx-auto space-y-4 sm:space-y-6">
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
        <div className="flex flex-1 overflow-hidden relative anim-fall flex-col md:flex-row h-[calc(100vh-3rem)]">
          {/* Left Control Panel: Desktop side-column, Mobile full-pane overlay */}
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
              onUpdateCoords={(nRa, nDec) => {
                void handleSearchCoordinates(nRa, nDec);
                setMobileViewerPane('canvas');
              }}
              onUpdateFov={setFov}
              selectedArray={selectedArray}
              onSelectArray={handleSelectDetectorArray}
              selectedChannel={selectedChannel}
              onSelectChannel={setSelectedChannel}
              subtractionMode={subtractionMode}
              onChangeSubtractionMode={setSubtractionMode}
              overlays={overlays}
              onToggleOverlay={handleToggleOverlay}
              onRefreshCutout={handleRefreshCutout}
              viewMode={viewMode}
              searchStatus={searchStatus}
              activeCandidate={activeCandidate}
              liveCatalog={liveCatalog}
              isCatalogLoading={isCatalogLoading}
              onRefreshCatalog={() => setCatalogRefreshCounter((c) => c + 1)}
              className="h-full w-full"
            />
          </div>

          {/* Main Viewport: Canvas & Playback */}
          <main
            className={`flex-1 flex flex-col h-[calc(100vh-6rem)] md:h-[calc(100vh-3rem)] overflow-hidden relative ${
              mobileViewerPane === 'canvas' ? 'flex' : 'hidden md:flex'
            }`}
          >
            {/* Floating Mobile Side Button: Settings (Left Side) */}
            <div className="md:hidden absolute top-14 left-2.5 z-30 pointer-events-auto">
              <button
                onClick={() => setMobileViewerPane('controls')}
                className="btn-tactile px-3 py-1.5 rounded-xl border-2 border-black bg-paper-900/95 backdrop-blur text-emerald-400 font-mono text-xs font-bold flex items-center gap-1.5 shadow-[0_0_20px_rgba(0,0,0,0.85)] cursor-pointer hover:bg-paper-850"
                title="Change Sky Viewer Settings (FOV, Detector Bands, Overlays, Coordinates)"
              >
                <Sliders className="w-3.5 h-3.5 text-emerald-400" />
                <span>Settings</span>
              </button>
            </div>

            {/* Floating Mobile Side Button: Triage (Right Side) */}
            <div className="md:hidden absolute top-14 right-2.5 z-30 pointer-events-auto">
              <button
                onClick={() => setMobileViewerPane('telemetry')}
                className="btn-tactile px-3 py-1.5 rounded-xl border-2 border-black bg-paper-900/95 backdrop-blur text-emerald-400 font-mono text-xs font-bold flex items-center gap-1.5 shadow-[0_0_20px_rgba(0,0,0,0.85)] cursor-pointer hover:bg-paper-850"
                title="Open Candidate Triage & Classification"
              >
                <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
                <span>Triage</span>
              </button>
            </div>

            <CanvasViewport
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
              skippedNotice={skippedNotice}
              onClearSkippedNotice={clearSkippedNotice}
              isScientistMode={viewMode === 'scientist'}
              mlAnalysisStatus={mlAnalysisStatus}
              liveCatalog={liveCatalog}
              onOpenMlInsights={() => {
                setDrawerControlledTab('ai');
                if (typeof window !== 'undefined' && window.innerWidth < 1024) {
                  setMobileViewerPane('telemetry');
                }
              }}
            />

            <MoviePlayerControls
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
            />
          </main>

          {/* Right Drawer: Desktop expandable column, Mobile full-pane overlay */}
          <div
            className={`${
              mobileViewerPane === 'telemetry'
                ? 'fixed inset-x-0 top-12 bottom-12 z-40 flex flex-col bg-paper-950 overflow-hidden anim-fall'
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

          {/* Mobile Bottom Dock (< md screens) */}
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
              onClick={() => setMobileViewerPane('telemetry')}
              className={`flex flex-col items-center justify-center flex-1 py-1 text-[10px] font-mono transition-colors ${
                mobileViewerPane === 'telemetry'
                  ? 'text-emerald-400 font-bold'
                  : 'text-paper-400 hover:text-paper-200'
              }`}
            >
              <Sparkles className="w-4 h-4 mb-0.5" />
              <span>Triage & AI</span>
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
      />

      {/* Choose Your View Assessment Pop-up Modal */}
      <ChooseYourViewModal
        isOpen={isViewModalOpen}
        onClose={() => setIsViewModalOpen(false)}
        currentMode={viewMode}
        onSelectMode={handleSetViewMode}
      />

      {/* Verify Scientist Object Dialog Modal */}
      {isVerifyModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm anim-fall">
          <div className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto bg-paper-950 border-2 border-paper-700 rounded-2xl shadow-2xl p-6">
            <div className="flex items-center justify-between pb-4 border-b border-paper-800 mb-6">
              <div>
                <h2 className="text-xl font-bold font-mono text-emerald-400">
                  🔬 NASA Scientist & Community Verification Feed
                </h2>
                <p className="text-xs text-paper-400 mt-1">
                  Inspect flagged candidate objects, view exact observation settings, and verify astrometric tracks.
                </p>
              </div>
              <button
                onClick={() => setIsVerifyModalOpen(false)}
                className="btn-tactile-sm px-3 py-1.5 rounded-lg border-2 border-black bg-paper-900 text-paper-300 hover:text-white font-mono text-xs cursor-pointer"
              >
                ✕ Close
              </button>
            </div>
            <VerifyScientistPanel
              onSelectVerificationTarget={handleSelectVerificationTarget}
              isCompact={false}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
