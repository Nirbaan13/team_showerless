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
import { ReactBitsLoader } from './components/common/ReactBitsLoader';

export function App() {
  // 1. Initial State from Preset 1 (Barnard's Star)
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

  // Catalog Overlays
  const [overlays, setOverlays] = useState<CatalogOverlayState>({
    gaiaDr3: true,
    wise: false,
    solarSystemEphemeris: false,
  });

  // Candidate selection & micro-interactions
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>('cand-barnard-primary');
  const [simulateLatency, setSimulateLatency] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isEmbedModalOpen, setIsEmbedModalOpen] = useState<boolean>(false);

  // 2. Data Synthesis
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

  // 3. Bi-directional URL synchronization
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

  // 4. Player hook for blink movie and missing detector frame skipping
  const { skippedNotice, clearSkippedNotice, stepForward, stepBackward } = useSpherexPlayer({
    frames,
    fps,
    isPlaying,
    currentIndex: activeFrameIndex,
    onFrameChange: setActiveFrameIndex,
  });

  // Handlers
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

    // Trigger brief loader for visual polish
    setIsLoading(true);
    setTimeout(() => setIsLoading(false), 600);
  };

  const handleRefreshCutout = () => {
    setIsLoading(true);
    setTimeout(() => setIsLoading(false), simulateLatency ? 2200 : 700);
  };

  const handleToggleSimulateLatency = () => {
    setSimulateLatency((prev) => !prev);
    setIsLoading(true);
    setTimeout(() => setIsLoading(false), 2400);
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
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-space-950 text-space-200">
      {/* ReactBits animated loading state */}
      {isLoading && (
        <ReactBitsLoader
          label="Synthesizing SPHEREx Cutout Cube"
          sublabel={`Querying Level-3 Data: RA ${ra.toFixed(4)}°, Dec ${dec.toFixed(4)}° (FOV: ${fov})`}
        />
      )}

      {/* Top Navigation */}
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

      {/* Center Work Area */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* Left Control Panel */}
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

        {/* Center Stage: Viewport + Blink Movie Scrubber */}
        <main className="flex-1 flex flex-col h-[calc(100vh-3.5rem)] overflow-hidden relative">
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

        {/* Right Drawer: Data Health, 102 Spectra & Triage */}
        <RightDrawer
          frames={frames}
          activeFrameIndex={activeFrameIndex}
          onSelectFrame={setActiveFrameIndex}
          candidate={activeCandidate}
          spectrumData={spectrumData}
          onUpdateCandidateClassification={handleUpdateCandidateClassification}
        />
      </div>

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
    </div>
  );
}

export default App;
