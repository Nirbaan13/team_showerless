import React, { useState } from 'react';
import type { CandidateObject, SpectralDataPoint } from '../types/spherex';
import { SpectrumPlot } from './SpectrumPlot';
import { FileText, Download, CheckCircle, ArrowLeft } from 'lucide-react';

interface DiscoveryReportPageProps {
  candidate: CandidateObject | null;
  spectrumData: SpectralDataPoint[];
  onBackToViewer: () => void;
}

export const DiscoveryReportPage: React.FC<DiscoveryReportPageProps> = ({
  candidate,
  spectrumData,
  onBackToViewer,
}) => {
  const [downloadSuccess, setDownloadSuccess] = useState(false);

  const handleExportJson = () => {
    if (!candidate) return;
    const reportData = {
      reportType: "SPHEREx Citizen Science Candidate Dossier",
      generatedAtUtc: new Date().toISOString(),
      candidateId: candidate.id,
      coordinates: {
        raDeg: candidate.ra,
        decDeg: candidate.dec,
      },
      classification: candidate.classification,
      confidence: candidate.confidence,
      volunteerNotes: candidate.volunteerNotes,
      catalogCrossMatch: candidate.matchedCatalog
        ? {
            catalog: candidate.matchedCatalog,
            id: candidate.catalogId,
            properMotion: candidate.properMotionMasYr,
          }
        : null,
      motionEpochs: candidate.epochPositions,
      spectralDataSummary: {
        channelsRecorded: spectrumData.length,
        wavelengthRangeUm: [0.75, 5.0],
      },
    };

    const blob = new Blob([JSON.stringify(reportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `SPHEREx_Dossier_${candidate.id}.json`;
    a.click();
    URL.revokeObjectURL(url);

    setDownloadSuccess(true);
    setTimeout(() => setDownloadSuccess(false), 2500);
  };

  if (!candidate) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-[#080c14] text-slate-300 p-8 space-y-4">
        <FileText className="w-12 h-12 text-slate-600" />
        <h2 className="text-lg font-semibold text-white">No Candidate Selected For Dossier</h2>
        <p className="text-xs text-slate-500 max-w-sm text-center">
          Open the Sky Viewport, click on an astronomical candidate object or transient, and return here to generate its full report.
        </p>
        <button
          onClick={onBackToViewer}
          className="px-4 py-2 bg-blue-600 text-white rounded font-mono text-xs font-medium hover:bg-blue-700 transition-colors"
        >
          Open Sky Viewport
        </button>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto bg-[#080c14] text-slate-100 p-8 md:p-12 select-none">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Back and Action Toolbar */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-5">
          <button
            onClick={onBackToViewer}
            className="flex items-center gap-2 text-xs font-mono text-slate-400 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Sky Viewport
          </button>

          <button
            onClick={handleExportJson}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-mono text-xs font-medium flex items-center gap-2 transition-colors shadow-sm"
          >
            {downloadSuccess ? <CheckCircle className="w-4 h-4 text-emerald-300" /> : <Download className="w-4 h-4" />}
            <span>{downloadSuccess ? 'Dossier Exported!' : 'Export JSON Report'}</span>
          </button>
        </div>

        {/* Dossier Title & Header */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-blue-400">
            Citizen Science Verification Dossier
          </div>
          <h1 className="text-2xl md:text-3xl font-semibold text-white font-sans flex items-center gap-3">
            <span>{candidate.matchedCatalog || candidate.id}</span>
            <span className="text-xs font-mono uppercase px-2.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
              {candidate.classification}
            </span>
          </h1>
          <p className="text-xs font-mono text-slate-400">
            J2000 Coordinates: RA {candidate.ra.toFixed(6)}° • Dec {candidate.dec.toFixed(6)}°
          </p>
        </div>

        {/* Summary Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 rounded-lg bg-[#0d131f] border border-slate-800 space-y-1">
            <span className="text-[11px] font-mono text-slate-400 uppercase">Detection Confidence</span>
            <div className="text-lg font-semibold text-white capitalize">{candidate.confidence} Confidence</div>
            <p className="text-[11px] text-slate-500">Based on cross-epoch proper motion</p>
          </div>

          <div className="p-4 rounded-lg bg-[#0d131f] border border-slate-800 space-y-1">
            <span className="text-[11px] font-mono text-slate-400 uppercase">Catalog Cross-Match</span>
            <div className="text-lg font-semibold text-emerald-400">
              {candidate.matchedCatalog || 'Uncatalogued Candidate'}
            </div>
            <p className="text-[11px] text-slate-500">{candidate.catalogId || 'No known astrometric match'}</p>
          </div>

          <div className="p-4 rounded-lg bg-[#0d131f] border border-slate-800 space-y-1">
            <span className="text-[11px] font-mono text-slate-400 uppercase">Proper Motion Track</span>
            <div className="text-lg font-semibold text-white">
              {candidate.properMotionMasYr ? `${candidate.properMotionMasYr.pmDec} mas/yr` : 'Measured Across 5 Epochs'}
            </div>
            <p className="text-[11px] text-slate-500">Consistent motion vector</p>
          </div>
        </div>

        {/* 102-Band Spectrophotometry Section */}
        <div className="space-y-3 p-6 rounded-lg bg-[#0d131f] border border-slate-800">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200 font-mono">
              102-Band Spectroscopic Signature
            </h2>
            <span className="text-xs font-mono text-blue-400">0.75 – 5.00 µm Continuous</span>
          </div>

          <SpectrumPlot
            data={spectrumData}
            objectLabel={candidate.matchedCatalog || candidate.id}
          />

          <div className="text-xs text-slate-400 leading-relaxed font-sans pt-2">
            <strong>Atmospheric Analysis:</strong> Absorption signature exhibits strong water-ice (H2O) band depression at 3.05 µm alongside secondary carbon dioxide (CO2) features at 4.27 µm. Spectral morphology closely matches cold sub-stellar/brown dwarf atmospheric models.
          </div>
        </div>

        {/* Volunteer Notes & Observations */}
        <div className="p-6 rounded-lg bg-[#0d131f] border border-slate-800 space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200 font-mono">
            Observer Verification Notes
          </h2>
          <p className="text-xs text-slate-300 leading-relaxed font-sans bg-[#080c14] p-3 rounded border border-slate-800">
            {candidate.volunteerNotes || 'No specific observation comments recorded.'}
          </p>
        </div>
      </div>
    </div>
  );
};
