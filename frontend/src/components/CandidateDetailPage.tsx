import React, { useState, useEffect } from 'react';
import type { CandidateRecord, ClassificationVote, UserRole, ValidationStatus } from '../types/catalogue';
import {
  fetchCandidateById,
  evaluateConsensus,
  submitClassificationVote,
} from '../services/catalogueService';
import { SpectrumPlot } from './SpectrumPlot';
import { ExternalSubmissionModal } from './ExternalSubmissionModal';
import {
  ArrowLeft,
  Share2,
  Check,
  Compass,
  Download,
  Send,
  ShieldCheck,
  AlertTriangle,
  HelpCircle,
  XCircle,
  Eye,
  Activity,
  Layers,
  Sparkles,
  Users,
  CheckCircle2,
  Clock,
  Play,
  Pause,
  UserCheck,
} from 'lucide-react';

interface CandidateDetailPageProps {
  candidateId: string;
  onBack: () => void;
  onOpenSkyViewer: (ra: number, dec: number, candidateId: string) => void;
  onOpenFeed?: () => void;
}

export const CandidateDetailPage: React.FC<CandidateDetailPageProps> = ({
  candidateId,
  onBack,
  onOpenSkyViewer,
  onOpenFeed,
}) => {
  const [loadError, setLoadError] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<CandidateRecord | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [copiedLink, setCopiedLink] = useState(false);
  const [isSubmissionModalOpen, setIsSubmissionModalOpen] = useState(false);
  const [activeBlinkEpoch, setActiveBlinkEpoch] = useState<number>(0);
  const [isBlinking, setIsBlinking] = useState<boolean>(true);

  // Classification Form State
  const [userName, setUserName] = useState<string>('Citizen Volunteer (You)');
  const [userRole, setUserRole] = useState<UserRole>('Volunteer');
  const [userVote, setUserVote] = useState<ClassificationVote>('likely_real');
  const [suggestedType, setSuggestedType] = useState<string>('comet');
  const [observationNotes, setObservationNotes] = useState<string>('');
  const [isSubmittingVote, setIsSubmittingVote] = useState(false);
  const [voteMessage, setVoteMessage] = useState<{ text: string; isError?: boolean } | null>(null);

  // Load candidate detail
  const loadDetail = React.useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await fetchCandidateById(candidateId);
      setCandidate(data);
      setLoadError(null);
    } catch (err) {
      setCandidate(null);
      setLoadError(err instanceof Error ? err.message : 'Registry unavailable');
    } finally {
      setIsLoading(false);
    }
  }, [candidateId]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  // Blink comparator loop across epochs
  useEffect(() => {
    if (!isBlinking) return;
    const epochCount = candidate?.epoch_count || 3;
    const timer = setInterval(() => {
      setActiveBlinkEpoch((prev) => (prev + 1) % epochCount);
    }, 450);
    return () => clearInterval(timer);
  }, [isBlinking, candidate?.epoch_count]);

  const handleCopyPermalink = () => {
    const url = `${window.location.origin}${window.location.pathname}?tab=catalogue&candidate=${candidateId}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    });
  };

  const handleExportEvidencePackage = () => {
    if (!candidate) return;
    const reportData = {
      project: 'PlanetX Persistent Candidate Catalogue',
      repository: 'team_showerless (NASA Space Apps Challenge 2026)',
      exportedAtUtc: new Date().toISOString(),
      candidateId: candidate.id,
      candidateName: candidate.name,
      coordinates: {
        raJ2000Deg: candidate.ra,
        decJ2000Deg: candidate.dec,
      },
      astrometry: {
        speedArcsecHr: candidate.speed_arcsec_hr,
        trajectoryFitRmsPx: candidate.fit_rms_px,
        epochCount: candidate.epoch_count,
        detectionMethod: candidate.detection_method,
      },
      photometry: {
        snr: candidate.snr,
        spectralSummary: candidate.spectral_summary,
      },
      scientificValidationMatrix: candidate.validation_checks,
      consensusAudit: {
        status: candidate.status,
        metrics: candidate.consensus,
        reviewers: candidate.classifications,
      },
      externalSubmissions: candidate.external_submissions,
      metadata: candidate.metadata,
    };

    const blob = new Blob([JSON.stringify(reportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `PlanetX_Evidence_${candidate.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSubmitClassification = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!candidate) return;
    setIsSubmittingVote(true);
    setVoteMessage(null);

    const userId = `user-${userName.toLowerCase().replace(/[^a-z0-9]/g, '-') || 'anon'}`;
    const res = await submitClassificationVote(
      candidate.id,
      { id: userId, name: userName, role: userRole },
      userVote,
      observationNotes,
      suggestedType
    );

    setIsSubmittingVote(false);
    if (res.success) {
      setVoteMessage({ text: res.message || 'Vote recorded successfully!' });
      setObservationNotes('');
      // Reload candidate to get updated consensus metrics
      loadDetail();
    } else {
      setVoteMessage({ text: res.message || 'Vote failed.', isError: true });
    }
  };

  if (isLoading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 bg-paper-950 text-paper-300 font-mono text-xs">
        <Activity className="w-8 h-8 text-emerald-400 animate-spin mb-3" />
        <span>Loading PlanetX Candidate Dossier [{candidateId}]...</span>
      </div>
    );
  }

  if (!candidate) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 bg-paper-950 text-paper-300 font-mono text-xs space-y-4">
        <AlertTriangle className="w-10 h-10 text-ochre-400" />
        <h2 role="alert" className="text-base font-bold text-white">{loadError ?? `Candidate ${candidateId} Not Found`}</h2>
        <p className="text-paper-500 max-w-sm text-center">
          The requested candidate record could not be retrieved from the persistent catalog.
        </p>
        <button
          onClick={onBack}
          className="btn-tactile px-4 py-2 rounded-xl bg-emerald-400 text-gray-950 font-bold"
        >
          Return to Catalogue
        </button>
      </div>
    );
  }

  const consensus = candidate.consensus ?? evaluateConsensus(candidate, candidate.classifications ?? [], candidate.validation_checks ?? []).metrics;

  const getValidationBadge = (status?: ValidationStatus) => {
    switch (status) {
      case 'passed':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/80 text-emerald-400 border border-emerald-500/50">
            <CheckCircle2 className="w-3 h-3" /> Passed
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-red-950/80 text-red-400 border border-red-500/50">
            <XCircle className="w-3 h-3" /> Failed
          </span>
        );
      case 'inconclusive':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950/80 text-amber-300 border border-amber-500/50">
            <HelpCircle className="w-3 h-3" /> Inconclusive
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-paper-800 text-paper-400 border border-paper-700">
            <Clock className="w-3 h-3" /> Pending
          </span>
        );
    }
  };

  return (
    <div className="flex-1 overflow-y-auto bg-paper-950 text-paper-200 p-4 sm:p-6 md:p-8 anim-fall select-none pb-20">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Navigation & Action Toolbar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-paper-800 gap-3">
          <button
            onClick={onBack}
            className="btn-tactile-sm px-3.5 py-1.5 rounded-xl border-2 border-black bg-paper-900 text-paper-300 hover:text-white flex items-center gap-2 font-mono text-xs cursor-pointer self-start"
          >
            <ArrowLeft className="w-4 h-4 text-emerald-400" />
            <span>Catalogue Directory</span>
          </button>

          <div className="flex flex-wrap items-center gap-2">
            {/* Share Permalink */}
            <button
              onClick={handleCopyPermalink}
              className="btn-tactile-sm px-3 py-1.5 rounded-xl border-2 border-black bg-paper-900 text-paper-300 hover:text-emerald-300 flex items-center gap-1.5 font-mono text-xs cursor-pointer"
              title="Copy shareable deep-link URL"
            >
              {copiedLink ? <Check className="w-3.5 h-3.5 text-emerald-400 stroke-[2.5]" /> : <Share2 className="w-3.5 h-3.5" />}
              <span>{copiedLink ? 'Permalink Copied!' : 'Share Deep-Link'}</span>
            </button>

            {/* Open in Sky Viewer */}
            <button
              onClick={() => onOpenSkyViewer(candidate.ra, candidate.dec, candidate.id)}
              className="btn-tactile-sm px-3.5 py-1.5 rounded-xl border-2 border-black bg-paper-900 hover:bg-paper-850 text-emerald-300 flex items-center gap-1.5 font-mono text-xs cursor-pointer"
            >
              <Compass className="w-3.5 h-3.5 text-emerald-400" />
              <span>Open in Sky Viewer</span>
            </button>

            {/* Verification Feed Button */}
            {onOpenFeed && (
              <button
                onClick={onOpenFeed}
                className="btn-tactile-sm px-3.5 py-1.5 rounded-xl border-2 border-sky-500/50 bg-sky-950/80 hover:bg-sky-900 text-sky-300 hover:text-white flex items-center gap-1.5 font-mono text-xs cursor-pointer shadow-[0_0_12px_rgba(56,189,248,0.2)]"
                title="Open NASA Scientist & Community Verification Feed"
              >
                <UserCheck className="w-3.5 h-3.5 text-sky-400" />
                <span>Verification Feed</span>
              </button>
            )}

            {/* Export Evidence Package */}
            <button
              onClick={handleExportEvidencePackage}
              className="btn-tactile-sm px-3.5 py-1.5 rounded-xl border-2 border-black bg-paper-900 hover:bg-paper-850 text-ochre-300 flex items-center gap-1.5 font-mono text-xs cursor-pointer"
            >
              <Download className="w-3.5 h-3.5 text-ochre-400" />
              <span>Export Package</span>
            </button>

            {/* External Submission Portal Button */}
            <button
              onClick={() => setIsSubmissionModalOpen(true)}
              className="btn-tactile px-4 py-1.5 rounded-xl border-2 border-black bg-emerald-400 hover:bg-emerald-300 text-gray-950 font-mono text-xs font-bold flex items-center gap-1.5 cursor-pointer shadow-[0_0_15px_rgba(16,185,129,0.3)]"
            >
              <Send className="w-3.5 h-3.5 stroke-[2.5]" />
              <span>External Submission Portal</span>
            </button>
          </div>
        </div>

        {/* Candidate Dossier Header */}
        <div className="p-5 sm:p-6 rounded-2xl bg-paper-900 border-2 border-paper-800 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="px-3 py-1 rounded-xl bg-emerald-400 text-gray-950 font-mono font-bold text-sm tracking-wider shadow-[0_0_12px_rgba(16,185,129,0.4)]">
                {candidate.id}
              </span>
              <h1 className="text-xl sm:text-2xl md:text-3xl font-bold font-sans text-white tracking-wide">
                {candidate.name}
              </h1>
            </div>

            <div className="flex items-center gap-2 font-mono text-xs">
              <span
                className={`px-3 py-1 rounded-full font-bold uppercase tracking-wider border ${
                  candidate.status === 'community_verified' || candidate.status === 'externally_confirmed'
                    ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500/50'
                    : candidate.status === 'submitted_external'
                    ? 'bg-sky-950/80 text-sky-300 border-sky-500/50'
                    : 'bg-amber-950/80 text-amber-300 border-amber-500/50'
                }`}
              >
                {candidate.status.replace('_', ' ')}
              </span>
              <span className="px-2.5 py-1 rounded-lg bg-paper-950 text-paper-400 border border-paper-800">
                {candidate.candidate_type.replace('_', ' ')}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 border-t border-paper-800 text-xs font-mono">
            <div>
              <span className="text-paper-500 block text-[10px] uppercase">Astrometric Coordinates</span>
              <span className="text-paper-200 font-bold">
                RA {candidate.ra.toFixed(4)}° • Dec {candidate.dec.toFixed(4)}°
              </span>
            </div>
            <div>
              <span className="text-paper-500 block text-[10px] uppercase">Apparent Sky Speed</span>
              <span className="text-ochre-300 font-bold">
                {candidate.speed_arcsec_hr > 0 ? `${candidate.speed_arcsec_hr.toFixed(1)}″/hr` : 'Stationary (<0.5″/hr)'}
              </span>
            </div>
            <div>
              <span className="text-paper-500 block text-[10px] uppercase">Trajectory Fit RMS</span>
              <span className="text-emerald-400 font-bold">{candidate.fit_rms_px.toFixed(2)} px</span>
            </div>
            <div>
              <span className="text-paper-500 block text-[10px] uppercase">Detection Significance</span>
              <span className="text-sky-300 font-bold">{candidate.snr.toFixed(1)}σ SNR ({candidate.epoch_count} epochs)</span>
            </div>
          </div>
        </div>

        {/* Section 1: Visual Evidence Panel (Side-by-Side Shift & Stack + Blink Animation) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Shift & Stack Evidence */}
          <div className="p-5 rounded-2xl bg-paper-900 border-2 border-paper-800 space-y-4">
            <div className="flex items-center justify-between border-b border-paper-800 pb-3">
              <div className="flex items-center gap-2 font-mono text-sm font-bold text-white">
                <Layers className="w-4 h-4 text-emerald-400" />
                <span>Shift & Stack Coadd Telemetry (29×29 px)</span>
              </div>
              <span className="text-[10px] font-mono text-paper-400">
                ZScale Contrast Stretched
              </span>
            </div>

            <div className="grid grid-cols-2 gap-4">
              {/* Fixed Sky Coadd */}
              <div className="p-3 rounded-xl bg-paper-950 border border-paper-800 flex flex-col items-center space-y-2">
                <span className="text-[11px] font-mono text-paper-400 font-bold uppercase">
                  Fixed Sky Spot Stack
                </span>
                <div className="relative w-36 h-36 bg-black rounded-lg overflow-hidden border border-paper-800 flex items-center justify-center">
                  <img
                    src={`/api/motion/coadd/${candidate.id}/fixed.png`}
                    alt="Fixed Sky Coadd"
                    className="w-full h-full object-cover pixelated"
                    onError={(e) => {
                      (e.target as HTMLImageElement).src =
                        'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" fill="%23111"><rect width="100" height="100"/><circle cx="50" cy="50" r="15" fill="%23333"/><line x1="30" y1="50" x2="70" y2="50" stroke="%23555" stroke-width="2"/></svg>';
                    }}
                  />
                  {/* Reticle Ring */}
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="w-8 h-8 rounded-full border border-dashed border-ochre-400/80" />
                  </div>
                </div>
                <div className="text-[10px] font-mono text-paper-400 text-center">
                  Trailed / Smeared Signal
                </div>
              </div>

              {/* Follow Track Coadd */}
              <div className="p-3 rounded-xl bg-paper-950 border-2 border-emerald-500/40 flex flex-col items-center space-y-2">
                <div className="flex items-center gap-1 text-[11px] font-mono text-emerald-400 font-bold uppercase">
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Follow-Track Coadd</span>
                </div>
                <div className="relative w-36 h-36 bg-black rounded-lg overflow-hidden border border-emerald-500/50 flex items-center justify-center shadow-[0_0_15px_rgba(16,185,129,0.2)]">
                  <img
                    src={`/api/motion/coadd/${candidate.id}/motion.png`}
                    alt="Motion Follow Coadd"
                    className="w-full h-full object-cover pixelated"
                    onError={(e) => {
                      (e.target as HTMLImageElement).src =
                        'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" fill="%23111"><rect width="100" height="100"/><circle cx="50" cy="50" r="8" fill="%2310b981"/></svg>';
                    }}
                  />
                  {/* Concentric Target Reticle Ring */}
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="w-8 h-8 rounded-full border-2 border-emerald-400 animate-pulse" />
                    <div className="w-14 h-14 rounded-full border border-emerald-400/40 absolute" />
                  </div>
                </div>
                <div className="text-[10px] font-mono text-emerald-300 font-bold text-center">
                  Point-Source Coadded ({candidate.snr.toFixed(1)}σ)
                </div>
              </div>
            </div>

            <p className="text-[11px] font-mono text-paper-400 leading-relaxed bg-paper-950/60 p-3 rounded-xl border border-paper-800">
              When shifting exposures along the candidate trajectory ({candidate.speed_arcsec_hr.toFixed(1)}″/hr),
              the target coadds constructively into a concentrated central PSF with fit RMS of{' '}
              <span className="text-emerald-400 font-bold">{candidate.fit_rms_px.toFixed(2)} px</span>,
              distinguishing real celestial motion from static artifacts.
            </p>
          </div>

          {/* Interactive Multi-Epoch Blink Comparator */}
          <div className="p-5 rounded-2xl bg-paper-900 border-2 border-paper-800 space-y-4">
            <div className="flex items-center justify-between border-b border-paper-800 pb-3">
              <div className="flex items-center gap-2 font-mono text-sm font-bold text-white">
                <Eye className="w-4 h-4 text-sky-400" />
                <span>Multi-Epoch FITS Astrometric Blink</span>
              </div>
              <button
                onClick={() => setIsBlinking((b) => !b)}
                className={`btn-tactile-sm px-2.5 py-1 rounded-lg border text-[11px] font-mono flex items-center gap-1.5 cursor-pointer ${
                  isBlinking
                    ? 'bg-emerald-400 text-gray-950 font-bold border-black'
                    : 'bg-paper-950 text-paper-300 border-paper-800'
                }`}
              >
                {isBlinking ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                <span>{isBlinking ? 'Blinking' : 'Paused'}</span>
              </button>
            </div>

            <div className="flex flex-col items-center justify-center space-y-3">
              <div className="relative w-56 h-56 bg-black rounded-xl overflow-hidden border-2 border-paper-800 flex items-center justify-center">
                <img
                  src={`/api/motion/cutout/render?ra=${candidate.ra}&dec=${candidate.dec}&epoch=${activeBlinkEpoch}&width=256&height=256`}
                  alt={`FITS Epoch ${activeBlinkEpoch}`}
                  className="w-full h-full object-cover pixelated"
                  onError={(e) => {
                    (e.target as HTMLImageElement).src =
                      'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" fill="%2309090b"><rect width="200" height="200"/><circle cx="100" cy="100" r="10" fill="%2338bdf8"/></svg>';
                  }}
                />
                <div className="absolute top-2 left-2 px-2 py-0.5 rounded bg-black/80 font-mono text-[10px] text-sky-300 border border-sky-400/40">
                  Epoch {activeBlinkEpoch + 1} / {candidate.epoch_count}
                </div>
                {/* Target tracking cursor */}
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <div className="w-6 h-6 rounded-full border border-sky-400" />
                </div>
              </div>

              {/* Epoch Selector Pills */}
              <div className="flex items-center gap-1.5 font-mono text-xs">
                {Array.from({ length: candidate.epoch_count }).map((_, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      setIsBlinking(false);
                      setActiveBlinkEpoch(idx);
                    }}
                    className={`px-3 py-1 rounded-lg border text-[11px] font-bold cursor-pointer transition-all ${
                      activeBlinkEpoch === idx
                        ? 'bg-sky-400 text-gray-950 border-black shadow-[0_0_10px_rgba(56,189,248,0.4)]'
                        : 'bg-paper-950 text-paper-400 border-paper-800 hover:text-white'
                    }`}
                  >
                    Epoch {idx + 1}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Section 2: Spectral Dossier (102-Band Spectrophotometer) */}
        <div className="p-5 sm:p-6 rounded-2xl bg-paper-900 border-2 border-paper-800 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-paper-800 gap-2">
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-ochre-400" />
              <div>
                <h3 className="text-base font-bold font-mono text-white">
                  102-Band Spectrophotometric Dossier (0.75 – 5.00 µm)
                </h3>
                <p className="text-[11px] font-mono text-paper-400">
                  Calibrated across SPHEREx detector arrays D1–D6 with diagnostic molecular band identification
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-xs font-mono">
              <span className="px-2 py-0.5 rounded bg-paper-950 text-ochre-300 border border-paper-800">
                WCS-WAVE Calibrated
              </span>
            </div>
          </div>

          <SpectrumPlot
            ra={candidate.ra}
            dec={candidate.dec}
            objectLabel={candidate.name}
            candidateId={candidate.id}
            isScientistMode={true}
          />
        </div>

        {/* Section 3: Automated Scientific Validation Matrix */}
        <div className="p-5 sm:p-6 rounded-2xl bg-paper-900 border-2 border-paper-800 space-y-4">
          <div className="flex items-center justify-between border-b border-paper-800 pb-3">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
              <h3 className="text-base font-bold font-mono text-white">
                Automated Scientific Validation Matrix
              </h3>
            </div>
            <span className="text-xs font-mono text-paper-400">
              Quantitative Gatekeeper Evaluation
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* 1. Gaia DR3 Crossmatch */}
            <div className="p-4 rounded-xl bg-paper-950 border border-paper-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold text-white">Gaia DR3 Crossmatch</span>
                {getValidationBadge(consensus.validation_summary['gaia_crossmatch'] as any || 'pending')}
              </div>
              <p className="text-[11px] font-mono text-paper-400 leading-relaxed">
                Evaluates sidereal starfield catalog. Verified absence of static optical star confirms genuine non-sidereal object.
              </p>
              <div className="text-[10px] font-mono text-paper-500 pt-1 border-t border-paper-800">
                See recorded validation evidence; absent checks remain pending.
              </div>
            </div>

            {/* 2. Signal-to-Noise Ratio */}
            <div className="p-4 rounded-xl bg-paper-950 border border-paper-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold text-white">S/N Threshold Gate</span>
                {getValidationBadge(consensus.validation_summary['snr_threshold'] as any || 'pending')}
              </div>
              <p className="text-[11px] font-mono text-paper-400 leading-relaxed">
                Nominal criterion: SNR ≥ 5.0σ across primary spectral detection channels.
              </p>
              <div className="text-[10px] font-mono text-emerald-400 font-bold pt-1 border-t border-paper-800">
                Recorded SNR: {candidate.snr.toFixed(1)}σ
              </div>
            </div>

            {/* 3. Trajectory Fit RMS */}
            <div className="p-4 rounded-xl bg-paper-950 border border-paper-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold text-white">Motion Linear Fit</span>
                {getValidationBadge(consensus.validation_summary['multi_epoch_motion'] as any || 'pending')}
              </div>
              <p className="text-[11px] font-mono text-paper-400 leading-relaxed">
                Nominal criterion: Trajectory fit RMS &lt; 0.50 px across ≥3 epochs.
              </p>
              <div className="text-[10px] font-mono text-emerald-400 font-bold pt-1 border-t border-paper-800">
                Fit RMS: {candidate.fit_rms_px.toFixed(2)} px ({candidate.epoch_count} epochs)
              </div>
            </div>

            {/* 4. Artifact & Bitmask Flag */}
            <div className="p-4 rounded-xl bg-paper-950 border border-paper-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold text-white">Artifact Flag Check</span>
                {getValidationBadge(consensus.validation_summary['spectral_plausibility'] as any || 'pending')}
              </div>
              <p className="text-[11px] font-mono text-paper-400 leading-relaxed">
                Rejects cosmic ray hits, detector edge reflections, and uncorrected bad pixels.
              </p>
              <div className="text-[10px] font-mono text-paper-500 pt-1 border-t border-paper-800">
                See recorded spectral validation evidence.
              </div>
            </div>
          </div>
        </div>

        {/* Section 4: Community Classification & Consensus Engine */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Classification Form (Left 1 col) */}
          <div className="p-5 rounded-2xl bg-paper-900 border-2 border-paper-800 space-y-4">
            <div className="flex items-center justify-between border-b border-paper-800 pb-3">
              <div className="flex items-center gap-2 font-mono text-sm font-bold text-white">
                <Users className="w-4 h-4 text-emerald-400" />
                <span>Submit Classification</span>
              </div>
              <span className="text-[10px] font-mono text-paper-400">Double-Vote Protected</span>
            </div>

            <form onSubmit={handleSubmitClassification} className="space-y-3 font-mono text-xs">
              <div>
                <label className="text-[10px] text-paper-400 block mb-1">Your Name / Call-Sign:</label>
                <input
                  type="text"
                  value={userName}
                  onChange={(e) => setUserName(e.target.value)}
                  className="w-full px-3 py-1.5 rounded-lg bg-paper-950 border border-paper-800 text-paper-200 focus:outline-none focus:border-emerald-400 text-xs"
                  required
                />
              </div>

              <div>
                <label className="text-[10px] text-paper-400 block mb-1">Peer Role:</label>
                <select
                  value={userRole}
                  onChange={(e) => setUserRole(e.target.value as UserRole)}
                  className="w-full px-3 py-1.5 rounded-lg bg-paper-950 border border-paper-800 text-paper-200 focus:outline-none focus:border-emerald-400 text-xs"
                >
                  <option value="Volunteer">Citizen Volunteer</option>
                  <option value="Researcher">Astronomical Researcher</option>
                  <option value="Science Team">SPHEREx Science Team</option>
                </select>
              </div>

              <div>
                <label className="text-[10px] text-paper-400 block mb-1">Verification Vote:</label>
                <div className="grid grid-cols-2 gap-1.5">
                  <button
                    type="button"
                    onClick={() => setUserVote('likely_real')}
                    className={`py-2 px-2 rounded-lg border text-[11px] font-bold cursor-pointer transition-all ${
                      userVote === 'likely_real'
                        ? 'bg-emerald-400 text-gray-950 border-black shadow-[0_0_10px_rgba(16,185,129,0.3)]'
                        : 'bg-paper-950 text-paper-400 border-paper-800 hover:text-white'
                    }`}
                  >
                    Likely Real
                  </button>

                  <button
                    type="button"
                    onClick={() => setUserVote('likely_artifact')}
                    className={`py-2 px-2 rounded-lg border text-[11px] font-bold cursor-pointer transition-all ${
                      userVote === 'likely_artifact'
                        ? 'bg-red-400 text-gray-950 border-black'
                        : 'bg-paper-950 text-paper-400 border-paper-800 hover:text-white'
                    }`}
                  >
                    Imaging Artifact
                  </button>

                  <button
                    type="button"
                    onClick={() => setUserVote('uncertain')}
                    className={`py-2 px-2 rounded-lg border text-[11px] font-bold cursor-pointer transition-all ${
                      userVote === 'uncertain'
                        ? 'bg-amber-400 text-gray-950 border-black'
                        : 'bg-paper-950 text-paper-400 border-paper-800 hover:text-white'
                    }`}
                  >
                    Uncertain
                  </button>

                  <button
                    type="button"
                    onClick={() => setUserVote('already_known')}
                    className={`py-2 px-2 rounded-lg border text-[11px] font-bold cursor-pointer transition-all ${
                      userVote === 'already_known'
                        ? 'bg-sky-400 text-gray-950 border-black'
                        : 'bg-paper-950 text-paper-400 border-paper-800 hover:text-white'
                    }`}
                  >
                    Already Known
                  </button>
                </div>
              </div>

              <div>
                <label className="text-[10px] text-paper-400 block mb-1">Suggested Taxonomy:</label>
                <select
                  value={suggestedType}
                  onChange={(e) => setSuggestedType(e.target.value)}
                  className="w-full px-3 py-1.5 rounded-lg bg-paper-950 border border-paper-800 text-paper-200 focus:outline-none focus:border-emerald-400 text-xs"
                >
                  <option value="comet">Interstellar / Solar System Comet</option>
                  <option value="asteroid">Near-Earth / Main-Belt Asteroid</option>
                  <option value="supernova">Extragalactic Supernova / Transient</option>
                  <option value="variable">Variable Star / Proper Motion Dipole</option>
                  <option value="brown_dwarf">Sub-stellar Brown Dwarf</option>
                </select>
              </div>

              <div>
                <label className="text-[10px] text-paper-400 block mb-1">Observation Notes:</label>
                <textarea
                  value={observationNotes}
                  onChange={(e) => setObservationNotes(e.target.value)}
                  rows={3}
                  placeholder="Note astrometric blink behavior, PSF symmetry, or absorption traits..."
                  className="w-full px-3 py-1.5 rounded-lg bg-paper-950 border border-paper-800 text-paper-200 focus:outline-none focus:border-emerald-400 text-xs resize-none"
                />
              </div>

              {voteMessage && (
                <div
                  className={`p-2 rounded-lg text-[11px] ${
                    voteMessage.isError
                      ? 'bg-red-950/60 text-red-300 border border-red-500/50'
                      : 'bg-emerald-950/60 text-emerald-300 border border-emerald-500/50'
                  }`}
                >
                  {voteMessage.text}
                </div>
              )}

              <button
                type="submit"
                disabled={isSubmittingVote}
                className="w-full btn-tactile py-2 rounded-xl bg-emerald-400 hover:bg-emerald-300 text-gray-950 font-bold border-2 border-black cursor-pointer flex items-center justify-center gap-2 shadow-[0_0_12px_rgba(16,185,129,0.3)]"
              >
                <CheckCircle2 className="w-4 h-4 stroke-[2.5]" />
                <span>{isSubmittingVote ? 'Recording...' : 'Cast Verification Vote'}</span>
              </button>
            </form>
          </div>

          {/* Consensus Gauge & Audit History (Right 2 cols) */}
          <div className="lg:col-span-2 p-5 rounded-2xl bg-paper-900 border-2 border-paper-800 space-y-4">
            <div className="flex items-center justify-between border-b border-paper-800 pb-3">
              <div className="flex items-center gap-2 font-mono text-sm font-bold text-white">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span>Scientific Consensus Progress Engine</span>
              </div>
              <div className="text-xs font-mono">
                <span className="text-emerald-400 font-bold">
                  {Math.round(consensus.positive_ratio * 100)}% Positive
                </span>{' '}
                <span className="text-paper-400">({consensus.total_votes} independent reviews)</span>
              </div>
            </div>

            {/* Consensus Progress Bar & Milestones */}
            <div className="space-y-2">
              <div className="h-3 rounded-full bg-paper-950 border border-paper-800 overflow-hidden flex">
                <div
                  className="bg-emerald-400 h-full transition-all duration-500"
                  style={{ width: `${consensus.positive_ratio * 100}%` }}
                  title="Likely Real Object"
                />
                <div
                  className="bg-red-400 h-full transition-all duration-500"
                  style={{ width: `${consensus.artifact_ratio * 100}%` }}
                  title="Imaging Artifact"
                />
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs font-mono pt-1">
                <div
                  className={`p-3 rounded-xl border ${
                    consensus.level1_qualified
                      ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300'
                      : 'bg-paper-950 border-paper-800 text-paper-400'
                  }`}
                >
                  <div className="font-bold">Level 1: Under Review</div>
                  <div className="text-[10px] text-paper-400 mt-0.5">
                    Requires ≥3 votes with ≥66% positive votes ({consensus.total_votes}/3)
                  </div>
                </div>

                <div
                  className={`p-3 rounded-xl border ${
                    consensus.level2_qualified
                      ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300'
                      : 'bg-paper-950 border-paper-800 text-paper-400'
                  }`}
                >
                  <div className="font-bold">Level 2: Community Verified</div>
                  <div className="text-[10px] text-paper-400 mt-0.5">
                    Requires ≥10 votes with ≥80% positive &amp; passed automated checks ({consensus.total_votes}/10)
                  </div>
                </div>
              </div>
            </div>

            {/* Reviewer Audit Log */}
            <div className="space-y-2">
              <span className="text-xs font-mono font-bold text-paper-300 block">
                Verified Reviewer Audit History:
              </span>

              <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                {candidate.classifications && candidate.classifications.length > 0 ? (
                  candidate.classifications.map((cl) => (
                    <div
                      key={cl.id}
                      className="p-3 rounded-xl bg-paper-950 border border-paper-800 text-xs font-mono space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-white">{cl.user_name}</span>
                          <span className="px-1.5 py-0.2 rounded text-[9px] bg-paper-800 text-paper-400">
                            {cl.user_role}
                          </span>
                        </div>
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            cl.vote === 'likely_real'
                              ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/40'
                              : cl.vote === 'likely_artifact'
                              ? 'bg-red-950 text-red-400 border border-red-500/40'
                              : 'bg-paper-900 text-paper-300'
                          }`}
                        >
                          {cl.vote.replace('_', ' ')}
                        </span>
                      </div>
                      {cl.notes && <p className="text-[11px] text-paper-300 italic">{cl.notes}</p>}
                    </div>
                  ))
                ) : (
                  <div className="text-[11px] font-mono text-paper-500 italic p-3 text-center">
                    No community classifications recorded yet. Be the first to verify this candidate above!
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* External Submission Modal */}
      <ExternalSubmissionModal
        isOpen={isSubmissionModalOpen}
        onClose={() => setIsSubmissionModalOpen(false)}
        candidate={candidate}
        onSubmissionSuccess={() => {
          loadDetail();
        }}
      />
    </div>
  );
};
