import React, { useState, useMemo } from 'react';
import type { CandidateRecord, SubmissionDestination, ExternalSubmissionRecord } from '../types/catalogue';
import {
  routeCandidateDestination,
  getFormattedPayload,
  dispatchExternalSubmission,
} from '../services/externalSubmissionService';
import {
  X,
  ExternalLink,
  Copy,
  Check,
  Send,
  FileCode,
  ShieldCheck,
  Globe,
} from 'lucide-react';

interface ExternalSubmissionModalProps {
  isOpen: boolean;
  onClose: () => void;
  candidate: CandidateRecord | null;
  onSubmissionSuccess?: (submission: ExternalSubmissionRecord) => void;
}

export const ExternalSubmissionModal: React.FC<ExternalSubmissionModalProps> = ({
  isOpen,
  onClose,
  candidate,
  onSubmissionSuccess,
}) => {
  const [selectedDestination, setSelectedDestination] = useState<SubmissionDestination>('MPC');
  const [adesFormat, setAdesFormat] = useState<'xml' | 'psv'>('xml');
  const [copiedPayload, setCopiedPayload] = useState(false);
  const [isDispatching, setIsDispatching] = useState(false);
  const [dispatchResult, setDispatchResult] = useState<string | null>(null);

  // Manual status tracking state
  const [externalRefId, setExternalRefId] = useState('');
  const [manualStatus, setManualStatus] = useState<'submitted' | 'accepted' | 'rejected'>('submitted');

  // Recommendation engine
  const recommendation = useMemo(() => {
    if (!candidate) return null;
    return routeCandidateDestination(candidate);
  }, [candidate]);

  // Sync default selection to recommendation on open
  React.useEffect(() => {
    if (recommendation) {
      setSelectedDestination(recommendation.destination);
    }
    setDispatchResult(null);
  }, [recommendation, isOpen]);

  if (!isOpen || !candidate) return null;

  const currentPayload = getFormattedPayload(
    selectedDestination,
    candidate,
    selectedDestination === 'MPC' ? adesFormat : 'xml'
  );

  const handleCopyPayload = () => {
    navigator.clipboard.writeText(currentPayload).then(() => {
      setCopiedPayload(true);
      setTimeout(() => setCopiedPayload(false), 2000);
    });
  };

  const handleDispatch = async () => {
    setIsDispatching(true);
    setDispatchResult(null);
    try {
      const record = await dispatchExternalSubmission(
        candidate.id,
        selectedDestination,
        currentPayload,
        externalRefId.trim() || undefined,
        manualStatus
      );
      setDispatchResult(`✓ Submission recorded successfully. Status: ${manualStatus.toUpperCase()} (Reference: ${record.external_reference_id})`);
      if (onSubmissionSuccess) {
        onSubmissionSuccess(record);
      }
    } catch (err: any) {
      setDispatchResult(`Error during dispatch: ${err.message || 'Transmission failed'}`);
    } finally {
      setIsDispatching(false);
    }
  };

  const portalUrls: Record<SubmissionDestination, string> = {
    MPC: 'https://www.minorplanetcenter.net/iau/NEO/SubmitObs.html',
    TNS: 'https://www.wis-tns.org/submit',
    VSX: 'https://www.aavso.org/vsx/index.php?view=submit.top',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm anim-fall select-none">
      <div className="relative w-full max-w-3xl bg-paper-950 border-2 border-paper-800 rounded-2xl shadow-2xl flex flex-col max-h-[92vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-paper-800 bg-paper-900/60 shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-emerald-400/10 border-2 border-emerald-400/40 text-emerald-400">
              <Globe className="w-5 h-5 stroke-[2.5]" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs px-2 py-0.5 rounded bg-paper-800 text-emerald-300 font-bold border border-paper-700">
                  {candidate.id}
                </span>
                <h2 className="text-base sm:text-lg font-bold font-mono text-white">
                  Scientific Database Dispatch Pipeline
                </h2>
              </div>
              <p className="text-[11px] text-paper-400 font-mono mt-0.5">
                Target: {candidate.name} • RA {candidate.ra.toFixed(4)}°, Dec {candidate.dec.toFixed(4)}°
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="btn-tactile-sm p-1.5 rounded-lg border-2 border-black bg-paper-900 text-paper-400 hover:text-white cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5 text-xs font-mono">
          {/* Automated Recommendation Banner */}
          {recommendation && (
            <div className="p-3.5 rounded-xl bg-emerald-950/30 border-2 border-emerald-500/40 space-y-1.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-emerald-400 font-bold text-xs">
                  <ShieldCheck className="w-4 h-4" />
                  <span>Target Router Recommendation: {recommendation.destinationFullName}</span>
                </div>
                <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-400/20 text-emerald-300 border border-emerald-400/40">
                  {recommendation.eligibilityStatus.toUpperCase()}
                </span>
              </div>
              <p className="text-[11px] text-paper-300 leading-relaxed">
                {recommendation.reason}
              </p>
              <div className="text-[10px] text-paper-500 pt-1 border-t border-emerald-900/40">
                Governing Clearinghouse: <span className="text-paper-400">{recommendation.agency}</span>
              </div>
            </div>
          )}

          {/* Destination Selector Tabs */}
          <div className="space-y-1.5">
            <span className="text-[11px] font-bold text-paper-300 uppercase tracking-wider block">
              1. Select Scientific Clearinghouse Destination:
            </span>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => setSelectedDestination('MPC')}
                className={`p-3 rounded-xl border-2 text-left transition-all cursor-pointer ${
                  selectedDestination === 'MPC'
                    ? 'border-emerald-400 bg-emerald-400/10 text-white shadow-[0_0_12px_rgba(16,185,129,0.2)]'
                    : 'border-paper-800 bg-paper-900 text-paper-400 hover:border-paper-700 hover:text-paper-200'
                }`}
              >
                <div className="flex items-center justify-between font-bold text-xs">
                  <span>Minor Planet Center</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-paper-800 text-ochre-300">MPC</span>
                </div>
                <div className="text-[10px] text-paper-500 mt-1">
                  Moving Objects & Spaceborne Astrometry (ADES)
                </div>
              </button>

              <button
                type="button"
                onClick={() => setSelectedDestination('TNS')}
                className={`p-3 rounded-xl border-2 text-left transition-all cursor-pointer ${
                  selectedDestination === 'TNS'
                    ? 'border-sky-400 bg-sky-400/10 text-white shadow-[0_0_12px_rgba(56,189,248,0.2)]'
                    : 'border-paper-800 bg-paper-900 text-paper-400 hover:border-paper-700 hover:text-paper-200'
                }`}
              >
                <div className="flex items-center justify-between font-bold text-xs">
                  <span>Transient Name Server</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-paper-800 text-sky-300">IAU TNS</span>
                </div>
                <div className="text-[10px] text-paper-500 mt-1">
                  Optical/NIR Flares & New Transients
                </div>
              </button>

              <button
                type="button"
                onClick={() => setSelectedDestination('VSX')}
                className={`p-3 rounded-xl border-2 text-left transition-all cursor-pointer ${
                  selectedDestination === 'VSX'
                    ? 'border-purple-400 bg-purple-400/10 text-white shadow-[0_0_12px_rgba(192,132,252,0.2)]'
                    : 'border-paper-800 bg-paper-900 text-paper-400 hover:border-paper-700 hover:text-paper-200'
                }`}
              >
                <div className="flex items-center justify-between font-bold text-xs">
                  <span>Variable Star Index</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-paper-800 text-purple-300">AAVSO</span>
                </div>
                <div className="text-[10px] text-paper-500 mt-1">
                  Periodic Flux Variance & Stellar Light Curves
                </div>
              </button>
            </div>
          </div>

          {/* Subformat switch for MPC */}
          {selectedDestination === 'MPC' && (
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-paper-400">ADES Output Syntax:</span>
              <div className="flex items-center bg-paper-900 rounded-lg p-0.5 border border-paper-800">
                <button
                  type="button"
                  onClick={() => setAdesFormat('xml')}
                  className={`px-2.5 py-1 rounded text-[10px] font-bold cursor-pointer ${
                    adesFormat === 'xml' ? 'bg-emerald-400 text-gray-950' : 'text-paper-400 hover:text-white'
                  }`}
                >
                  ADES XML
                </button>
                <button
                  type="button"
                  onClick={() => setAdesFormat('psv')}
                  className={`px-2.5 py-1 rounded text-[10px] font-bold cursor-pointer ${
                    adesFormat === 'psv' ? 'bg-emerald-400 text-gray-950' : 'text-paper-400 hover:text-white'
                  }`}
                >
                  ADES PSV (80-col)
                </button>
              </div>
            </div>
          )}

          {/* Machine-Readable Payload Box */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-paper-300 uppercase tracking-wider flex items-center gap-1.5">
                <FileCode className="w-3.5 h-3.5 text-emerald-400" />
                <span>
                  2. Standardized Astrometric Payload ({selectedDestination} Formatter):
                </span>
              </span>
              <button
                type="button"
                onClick={handleCopyPayload}
                className="btn-tactile-sm px-2.5 py-1 rounded-lg bg-paper-900 border border-paper-700 text-paper-200 hover:text-white flex items-center gap-1 text-[11px] cursor-pointer"
              >
                {copiedPayload ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedPayload ? 'Copied to Clipboard!' : 'Copy Payload'}</span>
              </button>
            </div>

            <pre className="p-3.5 rounded-xl bg-paper-900/90 border-2 border-paper-800 text-[11px] font-mono text-emerald-300 overflow-x-auto max-h-48 leading-relaxed whitespace-pre selection:bg-emerald-400 selection:text-gray-950">
              {currentPayload}
            </pre>
          </div>

          {/* External Submission & Tracking Actions */}
          <div className="p-4 rounded-xl bg-paper-900/40 border border-paper-800 space-y-3">
            <span className="text-[11px] font-bold text-paper-300 uppercase tracking-wider block">
              3. Clearinghouse Dispatch & Status Audit:
            </span>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] text-paper-400 block mb-1">
                  External Reference ID (e.g. MPC-NEOCP-PX01 / TNS-2026abc):
                </label>
                <input
                  type="text"
                  value={externalRefId}
                  onChange={(e) => setExternalRefId(e.target.value)}
                  placeholder={`e.g. ${selectedDestination}-2026-${candidate.id.replace('-', '')}`}
                  className="w-full px-3 py-1.5 rounded-lg bg-paper-950 border border-paper-800 text-paper-200 focus:outline-none focus:border-emerald-400 text-xs font-mono"
                />
              </div>

              <div>
                <label className="text-[10px] text-paper-400 block mb-1">
                  Clearinghouse Submission Status:
                </label>
                <select
                  value={manualStatus}
                  onChange={(e) => setManualStatus(e.target.value as any)}
                  className="w-full px-3 py-1.5 rounded-lg bg-paper-950 border border-paper-800 text-paper-200 focus:outline-none focus:border-emerald-400 text-xs font-mono"
                >
                  <option value="submitted">Submitted (Awaiting Observatory Ingest)</option>
                  <option value="accepted">Accepted / Externally Confirmed</option>
                  <option value="rejected">Rejected by Clearinghouse</option>
                </select>
              </div>
            </div>

            {dispatchResult && (
              <div
                className={`p-2.5 rounded-lg text-[11px] flex items-center gap-2 ${
                  dispatchResult.startsWith('✓')
                    ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-500/50'
                    : 'bg-red-950/60 text-red-300 border border-red-500/50'
                }`}
              >
                <Check className="w-4 h-4 shrink-0" />
                <span>{dispatchResult}</span>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex flex-col sm:flex-row items-center justify-between px-5 py-3.5 border-t border-paper-800 bg-paper-900/60 gap-3 shrink-0">
          <a
            href={portalUrls[selectedDestination]}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-tactile-sm px-3.5 py-1.5 rounded-xl border border-paper-700 bg-paper-900 text-paper-300 hover:text-white flex items-center gap-1.5 text-xs font-mono cursor-pointer"
          >
            <ExternalLink className="w-3.5 h-3.5 text-ochre-400" />
            <span>Launch Official {selectedDestination} Portal</span>
          </a>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <button
              type="button"
              onClick={onClose}
              className="btn-tactile-sm px-4 py-1.5 rounded-xl border border-paper-800 text-paper-400 hover:text-white text-xs font-mono cursor-pointer flex-1 sm:flex-initial"
            >
              Close
            </button>
            <button
              type="button"
              onClick={handleDispatch}
              disabled={isDispatching}
              className="btn-tactile px-5 py-1.5 rounded-xl border-2 border-black bg-emerald-400 hover:bg-emerald-300 text-gray-950 font-bold text-xs font-mono flex items-center justify-center gap-2 cursor-pointer shadow-[0_0_15px_rgba(16,185,129,0.3)] flex-1 sm:flex-initial"
            >
              <Send className="w-3.5 h-3.5 stroke-[2.5]" />
              <span>{isDispatching ? 'Transmitting...' : 'Transmit & Record Submission'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
