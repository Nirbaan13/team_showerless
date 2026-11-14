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
import { CheckCircle, Radio, Activity, HelpCircle, MessageSquare } from 'lucide-react';

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
}

export const RightDrawer: React.FC<RightDrawerProps> = ({
  frames,
  activeFrameIndex,
  onSelectFrame,
  candidate,
  spectrumData,
  onUpdateCandidateClassification,
}) => {
  const [activeTab, setActiveTab] = useState<'triage' | 'spectrum' | 'health' | 'community'>('triage');
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
    <aside className="w-80 bg-paper-900 border-l border-paper-800 flex flex-col h-[calc(100vh-3rem)] text-xs select-none z-20">
      {/* Tab Navigation */}
      <div className="flex border-b border-paper-800 bg-paper-950">
        <button
          onClick={() => setActiveTab('triage')}
          className={`flex-1 py-2 font-mono text-[10px] font-medium border-b-2 flex items-center justify-center gap-1 transition-colors ${
            activeTab === 'triage'
              ? 'border-ochre-400 text-paper-100 bg-paper-900'
              : 'border-transparent text-paper-400 hover:text-paper-200'
          }`}
        >
          <CheckCircle className="w-3 h-3" />
          <span>Triage</span>
        </button>

        <button
          onClick={() => setActiveTab('spectrum')}
          className={`flex-1 py-2 font-mono text-[10px] font-medium border-b-2 flex items-center justify-center gap-1 transition-colors ${
            activeTab === 'spectrum'
              ? 'border-ochre-400 text-paper-100 bg-paper-900'
              : 'border-transparent text-paper-400 hover:text-paper-200'
          }`}
        >
          <Radio className="w-3 h-3" />
          <span>102 Bands</span>
        </button>

        <button
          onClick={() => setActiveTab('community')}
          className={`flex-1 py-2 font-mono text-[10px] font-medium border-b-2 flex items-center justify-center gap-1 transition-colors ${
            activeTab === 'community'
              ? 'border-ochre-400 text-paper-100 bg-paper-900'
              : 'border-transparent text-paper-400 hover:text-paper-200'
          }`}
        >
          <MessageSquare className="w-3 h-3 text-ochre-400" />
          <span>Chat (3)</span>
        </button>

        <button
          onClick={() => setActiveTab('health')}
          className={`flex-1 py-2 font-mono text-[10px] font-medium border-b-2 flex items-center justify-center gap-1 transition-colors ${
            activeTab === 'health'
              ? 'border-ochre-400 text-paper-100 bg-paper-900'
              : 'border-transparent text-paper-400 hover:text-paper-200'
          }`}
        >
          <Activity className="w-3 h-3" />
          <span>FITS</span>
        </button>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto">
        {/* TAB: COMMUNITY PEER CHAT */}
        {activeTab === 'community' && (
          <CommunityVerificationStream activeCandidateId={candidate?.id || null} />
        )}

        {/* TAB: TRIAGE */}
        {activeTab === 'triage' && (
          <div className="p-3.5 space-y-3">
            <div>
              <div className="flex items-center justify-between mb-0.5">
                <span className="font-semibold text-paper-100 uppercase tracking-wider text-[11px]">
                  Object Inspection
                </span>
                <span className="text-[10px] font-mono text-ochre-400">
                  {candidate ? candidate.id : 'None'}
                </span>
              </div>
              <p className="text-[11px] text-paper-400 leading-normal">
                Classify candidate motion between observation epochs.
              </p>
            </div>

            {candidate ? (
              <div className="space-y-2.5">
                {candidate.isKnownCatalogMatch && (
                  <div className="p-2 rounded bg-paper-950 border border-paper-800">
                    <div className="font-mono text-[11px] text-emerald-400 font-medium">
                      Matched: {candidate.matchedCatalog}
                    </div>
                    <div className="text-[10px] font-mono text-paper-400">
                      {candidate.catalogId || 'N/A'}
                    </div>
                  </div>
                )}

                <div>
                  <label className="text-[10px] font-mono text-paper-400 block mb-1 uppercase">
                    Classification
                  </label>
                  <div className="grid grid-cols-2 gap-1">
                    {[
                      { id: 'moving_object', label: 'Moving Object', desc: 'Proper motion' },
                      { id: 'transient', label: 'Transient', desc: 'Single burst' },
                      { id: 'already_known', label: 'Catalog Known', desc: 'Verified match' },
                      { id: 'artifact', label: 'Artifact', desc: 'Bad pixel/CR' },
                    ].map((item) => {
                      const isSelected = selectedClass === item.id;
                      return (
                        <button
                          key={item.id}
                          onClick={() => setSelectedClass(item.id as CandidateClassification)}
                          className={`p-1.5 rounded border text-left transition-colors ${
                            isSelected
                              ? 'bg-paper-800 border-ochre-400 text-paper-100 font-medium'
                              : 'bg-paper-950 border-paper-800 text-paper-400 hover:text-paper-200'
                          }`}
                        >
                          <div className="font-mono text-[11px]">{item.label}</div>
                          <div className="text-[9px] text-paper-500">{item.desc}</div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div>
                  <label className="text-[10px] font-mono text-paper-400 block mb-1 uppercase">
                    Confidence
                  </label>
                  <div className="grid grid-cols-3 gap-1">
                    {(['low', 'medium', 'high'] as ConfidenceLevel[]).map((lvl) => (
                      <button
                        key={lvl}
                        onClick={() => setSelectedConfidence(lvl)}
                        className={`py-1 rounded font-mono text-[10px] uppercase border transition-colors ${
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

                <div>
                  <label className="text-[10px] font-mono text-paper-400 block mb-1 uppercase">
                    Observation Notes
                  </label>
                  <textarea
                    rows={2}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Enter observation notes..."
                    className="w-full bg-paper-950 border border-paper-800 rounded p-1.5 font-mono text-[11px] text-paper-100 focus:outline-none focus:border-ochre-400 resize-none"
                  />
                </div>

                <button
                  onClick={handleSaveTriage}
                  className="w-full py-1.5 bg-paper-800 hover:bg-paper-700 text-paper-100 rounded font-mono text-xs font-medium transition-colors flex items-center justify-center gap-1.5 border border-paper-700"
                >
                  <CheckCircle className="w-3.5 h-3.5 text-ochre-400" />
                  <span>{isSaved ? 'Recorded ✓' : 'Save Classification'}</span>
                </button>
              </div>
            ) : (
              <div className="p-4 rounded border border-dashed border-paper-800 text-center space-y-1">
                <HelpCircle className="w-6 h-6 text-paper-600 mx-auto" />
                <div className="font-mono text-xs text-paper-400">No Target Selected</div>
              </div>
            )}
          </div>
        )}

        {/* TAB: SPECTRUM */}
        {activeTab === 'spectrum' && (
          <div className="p-3.5 space-y-3">
            <span className="font-semibold text-paper-100 uppercase tracking-wider text-[11px] block">
              102-Band Spectrophotometry
            </span>
            <SpectrumPlot
              data={spectrumData}
              objectLabel={candidate?.matchedCatalog || candidate?.id || "Target"}
            />
          </div>
        )}

        {/* TAB: FITS HEALTH */}
        {activeTab === 'health' && (
          <div className="p-3.5 space-y-2">
            <span className="font-semibold text-paper-100 uppercase tracking-wider text-[11px] block">
              FITS Frame Telemetry
            </span>
            <div className="space-y-1">
              {frames.map((f, idx) => (
                <div
                  key={f.frameId}
                  onClick={() => f.isAvailable && onSelectFrame(idx)}
                  className={`p-2 rounded border text-[10px] font-mono transition-colors ${
                    !f.isAvailable
                      ? 'bg-rose-950/20 border-rose-900/50 text-rose-300'
                      : idx === activeFrameIndex
                      ? 'bg-paper-800 border-ochre-400 text-paper-100'
                      : 'bg-paper-950 border-paper-800 text-paper-400 hover:text-paper-200 cursor-pointer'
                  }`}
                >
                  <div className="flex justify-between">
                    <span>Epoch {f.epochIndex + 1} ({f.observationDate.split('T')[0]})</span>
                    <span>Band {f.detectorArray}</span>
                  </div>
                  <div>Flagged: {f.flaggedPixelPercentage}% • CR: {f.cosmicRayHits}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
