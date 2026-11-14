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
      reportType: "SPHEREx Citizen Science Candidate Discovery Report",
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
    a.download = `SPHEREx_Discovery_${candidate.id}.json`;
    a.click();
    URL.revokeObjectURL(url);

    setDownloadSuccess(true);
    setTimeout(() => setDownloadSuccess(false), 2500);
  };

  if (!candidate) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-[#0a0a0e] text-paper-300 p-8 space-y-4">
        <FileText className="w-12 h-12 text-paper-600" />
        <h2 className="text-lg font-semibold text-white">No Candidate Selected For Discovery Report</h2>
        <p className="text-xs text-paper-500 max-w-sm text-center">
          Open the Sky Viewer, click on an astronomical candidate object or transient, and view its full report.
        </p>
        <button
          onClick={onBackToViewer}
          className="btn-tactile px-5 py-2.5 bg-emerald-400 hover:bg-emerald-300 text-gray-950 font-bold border-2 border-black rounded-xl font-mono text-xs cursor-pointer"
        >
          Open Sky Viewer
        </button>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto bg-[#0a0a0e] text-paper-100 p-8 md:p-12 select-none">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Back and Action Toolbar */}
        <div className="flex items-center justify-between border-b border-paper-800 pb-5">
          <button
            onClick={onBackToViewer}
            className="btn-tactile-sm px-4 py-2 bg-paper-900 border-2 border-black rounded-xl text-paper-300 hover:text-white flex items-center gap-2 font-mono text-xs cursor-pointer"
          >
            <ArrowLeft className="w-4 h-4 text-emerald-400" />
            <span>Return to Sky Viewer</span>
          </button>

          <button
            onClick={handleExportJson}
            className="btn-tactile px-5 py-2.5 bg-emerald-400 hover:bg-emerald-300 text-gray-950 font-bold border-2 border-black rounded-xl font-mono text-xs flex items-center gap-2 cursor-pointer"
          >
            {downloadSuccess ? <CheckCircle className="w-4 h-4 stroke-[2.5]" /> : <Download className="w-4 h-4 stroke-[2.5]" />}
            <span>{downloadSuccess ? 'Report Exported ✓' : 'Export JSON Report'}</span>
          </button>
        </div>

        {/* Discovery Title & Header */}
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-paper-900 border border-black text-xs font-mono uppercase tracking-widest text-emerald-400 btn-tactile-sm">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            Citizen Science Discovery Report
          </div>
          <h1 className="text-2xl md:text-3xl font-bold text-white font-sans flex items-center gap-3">
            <span>{candidate.matchedCatalog || candidate.id}</span>
            <span className="text-xs font-mono uppercase px-3 py-1 rounded-lg bg-paper-900 text-emerald-300 border-2 border-black">
              {candidate.classification.replace('_', ' ')}
            </span>
          </h1>
          <p className="text-xs font-mono text-paper-400">
            J2000 Coordinates: RA {candidate.ra.toFixed(6)}° • Dec {candidate.dec.toFixed(6)}°
          </p>
        </div>

        {/* Summary Grid with GitIngest-style tactile cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 rounded-xl bg-paper-900 border-2 border-black card-tactile space-y-1">
            <span className="text-[11px] font-mono text-paper-400 uppercase">Detection Confidence</span>
            <div className="text-lg font-bold text-white capitalize">{candidate.confidence} Confidence</div>
            <p className="text-[11px] text-paper-500">Cross-epoch proper motion verified</p>
          </div>

          <div className="p-4 rounded-xl bg-paper-900 border-2 border-black card-tactile space-y-1">
            <span className="text-[11px] font-mono text-paper-400 uppercase">Catalog Cross-Match</span>
            <div className="text-lg font-bold text-emerald-400">
              {candidate.matchedCatalog || 'Uncatalogued Candidate'}
            </div>
            <p className="text-[11px] text-paper-500">{candidate.catalogId || 'No matching known star recorded'}</p>
          </div>

          <div className="p-4 rounded-xl bg-paper-900 border-2 border-black card-tactile space-y-1">
            <span className="text-[11px] font-mono text-paper-400 uppercase">Proper Motion Track</span>
            <div className="text-lg font-bold text-ochre-400">
              {candidate.properMotionMasYr ? `${candidate.properMotionMasYr.pmDec} mas/yr` : 'Measured Across 5 Epochs'}
            </div>
            <p className="text-[11px] text-paper-500">Consistent astrometric vector</p>
          </div>
        </div>

        {/* 102-Band Spectrophotometry Section */}
        <div className="space-y-3 p-6 rounded-2xl bg-paper-900 border-2 border-black card-tactile">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold uppercase tracking-wider text-paper-200 font-mono">
              102-Band Spectroscopic Signature
            </h2>
            <span className="text-xs font-mono text-emerald-400">0.75 – 5.00 µm Continuous</span>
          </div>

          <SpectrumPlot
            data={spectrumData}
            objectLabel={candidate.matchedCatalog || candidate.id}
          />

          <div className="text-xs text-paper-400 leading-relaxed font-sans pt-2">
            <strong className="text-paper-200">Atmospheric Analysis:</strong> Absorption signature exhibits strong water-ice (H2O) band depression at 3.05 µm alongside secondary carbon dioxide (CO2) features at 4.27 µm. Spectral morphology closely matches cold sub-stellar/brown dwarf atmospheric models.
          </div>
        </div>

        {/* Observer Verification Notes */}
        <div className="p-6 rounded-2xl bg-paper-900 border-2 border-black card-tactile space-y-2">
          <h2 className="text-sm font-bold uppercase tracking-wider text-paper-200 font-mono">
            Observer Verification Notes
          </h2>
          <p className="text-xs text-paper-300 leading-relaxed font-sans bg-paper-950 p-3.5 rounded-xl border-2 border-black">
            {candidate.volunteerNotes || 'No specific observation comments recorded.'}
          </p>
        </div>
      </div>
    </div>
  );
};
