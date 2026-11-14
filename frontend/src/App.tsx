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
} from './types/spherex';
import {
  getMockEpochFrames,
  getMockCandidates,
  getMock102BandSpectrum,
} from './services/mockSpherexApi';
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
import { ReactBitsLoader } from './components/common/ReactBitsLoader';
import { Compass, Home } from 'lucide-react';

export function App() {
  // Check if loaded inside an iframe (?embed=true)
  const isEmbedMode = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('embed') === 'true';
  const [activeTab, setActiveTab] = useState<'home' | 'viewer' | 'report'>(() => (isEmbedMode ? 'viewer' : 'home'));

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

  const [currentPresetId, setCurrentPresetId] = useState<string | null>('barnards-star');
  const [ra, setRa] = useState<number>(269.452075);
  const [dec, setDec] = useState<number>(4.693365);
  const [fov, setFov] = useState<FOVOption>("3'");
  const [selectedArray, setSelectedArray] = useState<DetectorArrayId | 'all'>(2);
  const [selectedChannel, setSelectedChannel] = useState<number | null>(null);
  const [subtractionMode, setSubtractionMode] = useState<SubtractionMode>('raw_calibrated');
  const [activeFrameIndex, setActiveFrameIndex] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [fps, setFps] = useState<number>(3);
  const [blinkMode, setBlinkMode] = useState<boolean>(false);

  // All known-catalog overlays are on by default; users can untick them
  const ALL_OVERLAYS_ON: CatalogOverlayState = { gaiaDr3: true, wise: true, solarSystemEphemeris: true };
  const [overlays, setOverlays] = useState<CatalogOverlayState>(ALL_OVERLAYS_ON);

  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>('cand-barnard-primary');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isEmbedModalOpen, setIsEmbedModalOpen] = useState<boolean>(false);

  useEffect(() => {
    if (activeTab !== 'viewer') return;
    // Entering the Sky Viewer: re-enable every catalog overlay
    setOverlays({ gaiaDr3: true, wise: true, solarSystemEphemeris: true });
    if (!hasPromptedViewRef.current) {
      hasPromptedViewRef.current = true;
      setIsViewModalOpen(true);
    }
  }, [activeTab]);

  const frames = useMemo(() => {
    const arrayId = selectedArray === 'all' ? 3 : selectedArray;
    return getMockEpochFrames(currentPresetId || 'custom', arrayId);
  }, [currentPresetId, selectedArray]);

  const [candidatesList, setCandidatesList] = useState(() =>
    getMockCandidates('barnards-star')
  );

  const activeCandidate = useMemo(() => {
    return candidatesList.find((c) => c.id === selectedCandidateId) || candidatesList[0] || null;
  }, [candidatesList, selectedCandidateId]);

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
    currentIndex: activeFrameIndex,
    onFrameChange: setActiveFrameIndex,
  });

  // Handler when user searches custom coordinates on Home page
  const handleSearchCoordinates = (newRa: number, newDec: number) => {
    setRa(newRa);
    setDec(newDec);
    setCurrentPresetId(null);
    setActiveTab('viewer');
    setIsLoading(true);

    // Dynamically instantiate candidate object for the entered coordinates
    const customCandidate: CandidateObject = {
      id: `cand-${newRa.toFixed(2)}-${newDec.toFixed(2)}`,
      ra: newRa,
      dec: newDec,
      pixelX: 256,
      pixelY: 256,
      epochPositions: [
        { epochIndex: 0, x: 246, y: 248, flux: 32.5, snr: 16.4 },
        { epochIndex: 1, x: 251, y: 252, flux: 33.1, snr: 16.8 },
        { epochIndex: 2, x: 256, y: 256, flux: 32.7, snr: 16.5 },
        { epochIndex: 3, x: 261, y: 260, flux: 33.4, snr: 17.0 },
        { epochIndex: 4, x: 266, y: 264, flux: 32.9, snr: 16.7 },
      ],
      classification: 'unreviewed',
      confidence: 'medium',
      volunteerNotes: `User entered coordinates RA ${newRa.toFixed(4)}°, Dec ${newDec.toFixed(4)}°. Detected proper motion candidate awaiting triage.`,
      isKnownCatalogMatch: false,
      properMotionMasYr: { pmRa: -110.2, pmDec: 295.4 },
    };

    setCandidatesList([customCandidate]);
    setSelectedCandidateId(customCandidate.id);
    setTimeout(() => setIsLoading(false), 500);
  };

  // Handler when user clicks a benchmark preset on Home page
  const handleSelectPreset = (preset: TargetPreset) => {
    setCurrentPresetId(preset.id);
    setRa(preset.raDeg);
    setDec(preset.decDeg);
    setSelectedArray(preset.recommendedArray);
    setActiveFrameIndex(0);
    const newCands = getMockCandidates(preset.id);
    setCandidatesList(newCands);
    if (newCands.length > 0) {
      setSelectedCandidateId(newCands[0].id);
    }
    setActiveTab('viewer');
    setIsLoading(true);
    setTimeout(() => setIsLoading(false), 500);
  };

  const handleRefreshCutout = () => {
    setIsLoading(true);
    setTimeout(() => setIsLoading(false), 500);
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

      {/* Top Header: Clean, Uncluttered, Minimal */}
      <header className="h-12 bg-paper-900 border-b border-paper-800 px-4 flex items-center justify-between text-xs select-none z-30">
        <div className="flex items-center space-x-6">
          <div
            onClick={() => setActiveTab('home')}
            className="flex items-center space-x-2 cursor-pointer group"
          >
            <div className="w-5 h-5 rounded bg-ochre-400 text-paper-950 flex items-center justify-center font-bold text-[10px]">
              SPX
            </div>
            <span className="font-medium text-paper-100 tracking-wide text-xs font-sans group-hover:text-ochre-300 transition-colors">
              SPHEREx Sky-Viewer
            </span>
          </div>

          {/* Simple Tab Navigation */}
          <nav className="flex items-center space-x-2 font-mono text-[11px]">
            <button
              onClick={() => setActiveTab('home')}
              className={`btn-tactile-sm px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all border-2 border-black cursor-pointer ${
                activeTab === 'home'
                  ? 'bg-emerald-400 text-gray-950 font-bold'
                  : 'bg-paper-900 text-paper-300 hover:text-white'
              }`}
            >
              <Home className="w-3.5 h-3.5" />
              <span>Homepage</span>
            </button>

            <button
              onClick={() => setActiveTab('viewer')}
              className={`btn-tactile-sm px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all border-2 border-black cursor-pointer ${
                activeTab === 'viewer'
                  ? 'bg-emerald-400 text-gray-950 font-bold'
                  : 'bg-paper-900 text-paper-300 hover:text-white'
              }`}
            >
              <Compass className="w-3.5 h-3.5" />
              <span>Sky Viewer</span>
            </button>
          </nav>
        </div>

        {/* Global Volunteer vs Scientist View Switch */}
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-lg border-2 border-black bg-paper-950 p-0.5 btn-tactile-sm">
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

      {/* 1. Clean Home Page: Starts with big name and coordinate search */}
      {activeTab === 'home' && (
        <HomePage
          onSearchCoordinates={handleSearchCoordinates}
          onSelectPreset={handleSelectPreset}
        />
      )}

      {/* 2. Dossier Report Page */}
      {activeTab === 'report' && (
        <DiscoveryReportPage
          candidate={activeCandidate}
          spectrumData={spectrumData}
          onBackToViewer={() => setActiveTab('viewer')}
        />
      )}

      {/* 3. Sky Viewport: Edge-to-Edge Celestial Canvas */}
      {activeTab === 'viewer' && (
        <div className="flex flex-1 overflow-hidden relative anim-fall">
          <LeftControlPanel
            ra={ra}
            dec={dec}
            fov={fov}
            onUpdateCoords={(nRa, nDec) => handleSearchCoordinates(nRa, nDec)}
            onUpdateFov={setFov}
            selectedArray={selectedArray}
            onSelectArray={setSelectedArray}
            selectedChannel={selectedChannel}
            onSelectChannel={setSelectedChannel}
            subtractionMode={subtractionMode}
            onChangeSubtractionMode={setSubtractionMode}
            overlays={overlays}
            onToggleOverlay={handleToggleOverlay}
            onRefreshCutout={handleRefreshCutout}
            viewMode={viewMode}
          />

          <main className="flex-1 flex flex-col h-[calc(100vh-3rem)] overflow-hidden relative">
            <CanvasViewport
              frames={frames}
              activeFrameIndex={activeFrameIndex}
              candidates={candidatesList}
              selectedCandidateId={selectedCandidateId}
              onSelectCandidate={setSelectedCandidateId}
              overlays={overlays}
              subtractionMode={subtractionMode}
              centerRa={ra}
              centerDec={dec}
              skippedNotice={skippedNotice}
              onClearSkippedNotice={clearSkippedNotice}
              isScientistMode={viewMode === 'scientist'}
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

          {/* Right Drawer: Resizable & Expandable Triage & Telemetry */}
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
          />
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
    </div>
  );
}

export default App;
