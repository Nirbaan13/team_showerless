import { useState, useMemo } from 'react';
import type {
  TargetPreset,
  FOVOption,
  DetectorArrayId,
  SubtractionMode,
  CatalogOverlayState,
  CandidateClassification,
  ConfidenceLevel,
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
import { ReactBitsLoader } from './components/common/ReactBitsLoader';
import { Home, Compass, FileText } from 'lucide-react';

export function App() {
  const [activeTab, setActiveTab] = useState<'home' | 'viewer' | 'report'>('viewer');

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

  const [overlays, setOverlays] = useState<CatalogOverlayState>({
    gaiaDr3: true,
    wise: false,
    solarSystemEphemeris: false,
  });

  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>('cand-barnard-primary');
  const [simulateLatency, setSimulateLatency] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isEmbedModalOpen, setIsEmbedModalOpen] = useState<boolean>(false);

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
  };

  const handleRefreshCutout = () => {
    setIsLoading(true);
    setTimeout(() => setIsLoading(false), simulateLatency ? 2000 : 500);
  };

  const handleToggleSimulateLatency = () => {
    setSimulateLatency((prev) => !prev);
    setIsLoading(true);
    setTimeout(() => setIsLoading(false), 2000);
  };

  const handleUpdateCoords = (newRa: number, newDec: number) => {
    setRa(newRa);
    setDec(newDec);
    setCurrentPresetId(null);
    handleRefreshCutout();
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

      {/* Top Header */}
      <div className="h-12 bg-paper-900 border-b border-paper-800 px-4 flex items-center justify-between text-xs select-none z-30">
        <div className="flex items-center space-x-6">
          <div className="flex items-center space-x-2">
            <div className="w-5 h-5 rounded bg-paper-100 text-paper-950 flex items-center justify-center font-bold text-[10px]">
              SPX
            </div>
            <span className="font-medium text-paper-100 tracking-wide text-xs font-sans">
              SPHEREx Sky-Viewer
            </span>
          </div>

          <nav className="flex items-center space-x-1 font-mono text-[11px]">
            <button
              onClick={() => setActiveTab('home')}
              className={`px-3 py-1.5 rounded flex items-center gap-1.5 transition-colors ${
                activeTab === 'home'
                  ? 'bg-paper-800 text-paper-100 font-medium'
                  : 'text-paper-400 hover:text-paper-200'
              }`}
            >
              <Home className="w-3.5 h-3.5" />
              <span>1. Field</span>
            </button>

            <button
              onClick={() => setActiveTab('viewer')}
              className={`px-3 py-1.5 rounded flex items-center gap-1.5 transition-colors ${
                activeTab === 'viewer'
                  ? 'bg-paper-800 text-paper-100 font-medium'
                  : 'text-paper-400 hover:text-paper-200'
              }`}
            >
              <Compass className="w-3.5 h-3.5" />
              <span>2. Blink Player</span>
            </button>

            <button
              onClick={() => setActiveTab('report')}
              className={`px-3 py-1.5 rounded flex items-center gap-1.5 transition-colors ${
                activeTab === 'report'
                  ? 'bg-paper-800 text-paper-100 font-medium'
                  : 'text-paper-400 hover:text-paper-200'
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>3. Dossier Report</span>
            </button>
          </nav>
        </div>

        <TopNav
          currentPresetId={currentPresetId}
          onSelectPreset={handleSelectPreset}
          ra={ra}
          dec={dec}
          fov={fov}
          selectedArray={selectedArray}
          subtractionMode={subtractionMode}
          activeFrameIndex={activeFrameIndex}
          onOpenEmbedModal={() => setIsEmbedModalOpen(true)}
          simulateLatency={simulateLatency}
          onToggleSimulateLatency={handleToggleSimulateLatency}
        />
      </div>

      {activeTab === 'home' && (
        <HomePage
          onSelectTarget={handleSelectPreset}
          onEnterCustomCoords={() => setActiveTab('viewer')}
          onOpenStep={(step) => {
            if (step === 1 || step === 2) setActiveTab('viewer');
            else if (step === 4) setActiveTab('report');
            else setActiveTab('viewer');
          }}
        />
      )}

      {activeTab === 'report' && (
        <DiscoveryReportPage
          candidate={activeCandidate}
          spectrumData={spectrumData}
          onBackToViewer={() => setActiveTab('viewer')}
        />
      )}

      {activeTab === 'viewer' && (
        <div className="flex flex-1 overflow-hidden relative">
          <LeftControlPanel
            ra={ra}
            dec={dec}
            fov={fov}
            onUpdateCoords={handleUpdateCoords}
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

          <RightDrawer
            frames={frames}
            activeFrameIndex={activeFrameIndex}
            onSelectFrame={setActiveFrameIndex}
            candidate={activeCandidate}
            spectrumData={spectrumData}
            onUpdateCandidateClassification={handleUpdateCandidateClassification}
          />
        </div>
      )}

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
    </div>
  );
}

export default App;
