import React, { useEffect, useState } from 'react';
import {
  ArrowRight,
  ArrowLeft,
  X,
  CheckCircle2,
  Sparkles,
} from 'lucide-react';

export interface GuidedTutorialOverlayProps {
  isOpen: boolean;
  step: number;
  onNext: () => void;
  onPrev: () => void;
  onClose: () => void;
  onChangeMobilePane?: (pane: 'controls' | 'canvas' | 'telemetry') => void;
  onSelectDrawerTab?: (tab: 'ai' | 'triage' | 'chat' | 'spectrum') => void;
}

interface StepConfig {
  targetId: string;
  stepNum: number;
  totalSteps: number;
  badge: string;
  title: string;
  description: string;
  bulletPoints: string[];
  arrowDirection: 'left' | 'top' | 'bottom' | 'right';
  targetLabel: string;
  mobilePane: 'controls' | 'canvas' | 'telemetry';
  drawerTab?: 'ai' | 'triage' | 'chat' | 'spectrum';
}

export const TUTORIAL_STEPS: StepConfig[] = [
  {
    targetId: 'tutorial-target-coords',
    stepNum: 1,
    totalSteps: 7,
    badge: 'Step 1 of 7 • Sky Coordinates',
    title: 'Astronomical Coordinates (RA & Dec)',
    description:
      'Celestial coordinates pinpoint an exact position in the cosmos, similar to latitude and longitude on Earth:',
    bulletPoints: [
      'Right Ascension (RA): Celestial longitude, measured in degrees (0° to 360°) or hours (0h to 24h).',
      'Declination (Dec): Celestial latitude, measured from -90° (South celestial pole) to +90° (North celestial pole).',
      'Quick Usage: Type RA and Dec here and click "Update Field", or pick NASA test targets (like Comet 3I/ATLAS, Asteroid 4 Vesta, or Barnard’s Star).',
      'Live Status: The telemetry pill shows whether you are receiving a live stream from NASA IRSA or precomputed benchmark data.',
    ],
    arrowDirection: 'left',
    targetLabel: 'RA & Dec Celestial Coordinate Inputs',
    mobilePane: 'controls',
  },
  {
    targetId: 'tutorial-target-fov',
    stepNum: 2,
    totalSteps: 7,
    badge: 'Step 2 of 7 • Angular Scale',
    title: 'Field of View (FOV)',
    description:
      'Field of View defines the angular diameter of the sky patch displayed on screen, measured in arcminutes (′), where 60′ = 1°:',
    bulletPoints: [
      "1′ to 3′ (High Magnification): Optimal for inspecting individual asteroid point-spread functions (PSF) and cometary coma centroids.",
      "5′ to 10′ (Wide Survey): Ideal for tracking fast-moving solar system targets across observation epochs with wide stellar context.",
      "Interactive Zoom: You can also use your mouse wheel or pinch-to-zoom directly inside the canvas.",
    ],
    arrowDirection: 'left',
    targetLabel: 'Field of View Selector (1′, 3′, 5′, 10′)',
    mobilePane: 'controls',
  },
  {
    targetId: 'tutorial-target-skyview',
    stepNum: 3,
    totalSteps: 7,
    badge: 'Step 3 of 7 • Multi-Epoch Inspection',
    title: 'Sky View Panel & Blink Comparator',
    description:
      'This is your primary visual laboratory for spotting transient and moving objects across time:',
    bulletPoints: [
      'Leave-One-Out Blink Differencing: The comparator median-combines alternate epochs. Static background stars cancel out, causing moving asteroids or variable stars to stand out as distinct bright dipoles.',
      'Movie Playback Controls: Play time-lapses at 1 to 30 FPS, step frame-by-frame, and toggle ZScale automatic contrast stretching.',
      'Interactive Canvas Reticles: Click any candidate reticle on the canvas to inspect its astrometric trajectory and spectral signature.',
    ],
    arrowDirection: 'bottom',
    targetLabel: 'Multi-Epoch Canvas & Playback Bar',
    mobilePane: 'canvas',
  },
  {
    targetId: 'tutorial-target-filters',
    stepNum: 4,
    totalSteps: 7,
    badge: 'Step 4 of 7 • Background Subtraction',
    title: 'Image Filters & Subtraction Algorithms',
    description:
      'SPHEREx observes through diffuse interplanetary dust and stellar glare. Use image filters to isolate true celestial motion:',
    bulletPoints: [
      'Level 2/3 Aligned Sky (Raw): Standard calibrated telescope exposures with raw flux and quality bitmasks.',
      'Zodiacal Subtraction (Clean): Subtracts diffuse interplanetary dust glow (img - zodi) for crystal-clear stellar backgrounds.',
      'Leave-One-Out Difference Image (Motion): Subtracts median baseline across epochs to leave only moving bodies as bright dipoles.',
      'BLOOM Mask (Bright Cores): Special saturation recovery algorithm for tracking bright saturated asteroids (e.g. Asteroid 4 Vesta).',
    ],
    arrowDirection: 'left',
    targetLabel: 'Image Filters & Subtraction Algorithms',
    mobilePane: 'controls',
  },
  {
    targetId: 'tutorial-target-catalogs',
    stepNum: 5,
    totalSteps: 7,
    badge: 'Step 5 of 7 • Catalog Cross-Matching',
    title: 'Known Catalogs vs Non-Catalog Candidates',
    description:
      'The engine automatically pulls live astronomical records across international space agencies per coordinate:',
    bulletPoints: [
      'Space Agency Feeds: Cross-matches against ESA Gaia DR3 (astrometric stars), NASA AllWISE (infrared stars), CDS SIMBAD, and JPL Horizons.',
      'Known Catalog Matches: If a moving or stationary source matches an ephemeris or catalog star, it is clearly tagged with its official ID.',
      'Non-Catalog Discoveries: If an object has NO catalog match, it is an uncatalogued anomaly! These non-catalog candidates represent high-priority new asteroids, comets, or Planet X candidates.',
    ],
    arrowDirection: 'left',
    targetLabel: 'Known Catalogs & Non-Catalog Discovery Feeds',
    mobilePane: 'controls',
  },
  {
    targetId: 'tutorial-target-ai',
    stepNum: 6,
    totalSteps: 7,
    badge: 'Step 6 of 7 • Machine Learning Trajectory Detection',
    title: 'AI & Neural Motion Detection',
    description:
      'Automated machine learning identifies and scores candidate motion vectors across telescope visits:',
    bulletPoints: [
      'Random Forest Reranking: AI models trained on synthetic infrared injection fields link candidate centroid positions across multiple visits.',
      'Astrometric Parameters: Evaluates trajectory linearity, speed (arcseconds per hour), and astrometric fit RMS (residual root-mean-square).',
      'Candidate Ranks: High-scoring candidates (#1, #2, etc.) are sorted by signal-to-noise ratio and detection likelihood.',
      'One-Click Focus: Click any candidate card in the AI panel to automatically center and focus it in the Sky View canvas.',
    ],
    arrowDirection: 'right',
    targetLabel: 'AI Detection Panel & Motion Ranking',
    mobilePane: 'telemetry',
    drawerTab: 'ai',
  },
  {
    targetId: 'tutorial-target-spectrum',
    stepNum: 7,
    totalSteps: 7,
    badge: 'Step 7 of 7 • Spectrophotometric Science & Clearinghouse',
    title: '102-Band Spectroscopy & Community Verification',
    description:
      'SPHEREx captures full spectrophotometry across 102 near-infrared channels (0.75 - 5.0 μm) across 6 detector arrays (D1 - D6):',
    bulletPoints: [
      'Chemical Diagnostics: Measure flux density (F_λ) across all 102 channels to identify water ice (1.5, 2.0, 3.05 μm), CO₂ ice (4.27 μm), and silicates.',
      'Community Triage & Peer Review: Discuss findings, post comments, and cast scientific consensus votes in the Verification stream.',
      'Automated Clearinghouse Dispatch: When 10 community confirmations are reached, the system auto-submits standardized ADES XML / TNS JSON payloads directly to the Minor Planet Center!',
    ],
    arrowDirection: 'right',
    targetLabel: '102-Band Spectrum Plot & Molecular Analysis',
    mobilePane: 'telemetry',
    drawerTab: 'spectrum',
  },
];

export const GuidedTutorialOverlay: React.FC<GuidedTutorialOverlayProps> = ({
  isOpen,
  step,
  onNext,
  onPrev,
  onClose,
  onChangeMobilePane,
  onSelectDrawerTab,
}) => {
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);

  const currentStepConfig = TUTORIAL_STEPS[Math.min(step, TUTORIAL_STEPS.length - 1)];

  // Inject dynamic styles for bright pop-up highlighting
  useEffect(() => {
    const styleId = 'tutorial-dynamic-highlight-style';
    let styleTag = document.getElementById(styleId) as HTMLStyleElement | null;
    if (!styleTag) {
      styleTag = document.createElement('style');
      styleTag.id = styleId;
      styleTag.textContent = `
        .tutorial-active-target-glow {
          position: relative !important;
          z-index: 45 !important;
          box-shadow: 0 0 35px rgba(16, 185, 129, 0.85), inset 0 0 20px rgba(16, 185, 129, 0.25) !important;
          border-color: #34d399 !important;
          background-color: rgba(6, 78, 59, 0.45) !important;
          border-radius: 0.75rem !important;
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1) !important;
        }
        .tutorial-coords-extra-bright {
          position: relative !important;
          z-index: 45 !important;
          box-shadow: 0 0 50px rgba(52, 211, 153, 0.95), 0 0 30px rgba(251, 191, 36, 0.75), inset 0 0 20px rgba(52, 211, 153, 0.35) !important;
          border: 2px solid #6ee7b7 !important;
          background-color: rgba(16, 185, 129, 0.30) !important;
          border-radius: 0.75rem !important;
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1) !important;
        }
      `;
      document.head.appendChild(styleTag);
    }
    return () => {
      const existing = document.getElementById(styleId);
      if (existing) existing.remove();
    };
  }, []);

  // Update target bounding box, scroll element into view, and apply bright pop-up classes
  useEffect(() => {
    if (!isOpen || !currentStepConfig) return;

    // ONLY change mobile pane on mobile screens (< 1024px)
    if (onChangeMobilePane && typeof window !== 'undefined' && window.innerWidth < 1024) {
      onChangeMobilePane(currentStepConfig.mobilePane);
    }

    if (currentStepConfig.drawerTab && onSelectDrawerTab) {
      onSelectDrawerTab(currentStepConfig.drawerTab);
    }

    const updateBoundingRect = () => {
      // Clear any previous highlights
      document.querySelectorAll('.tutorial-active-target-glow, .tutorial-coords-extra-bright').forEach((node) => {
        node.classList.remove('tutorial-active-target-glow', 'tutorial-coords-extra-bright');
      });

      let el = document.getElementById(currentStepConfig.targetId);
      if (!el && (currentStepConfig.targetId === 'tutorial-target-ai' || currentStepConfig.targetId === 'tutorial-target-spectrum')) {
        el = document.getElementById('tutorial-target-right-panel');
      }

      if (el) {
        setTargetRect(el.getBoundingClientRect());

        if (currentStepConfig.targetId === 'tutorial-target-coords') {
          el.classList.add('tutorial-coords-extra-bright');
        } else {
          el.classList.add('tutorial-active-target-glow');
        }
      } else {
        setTargetRect(null);
      }
    };

    // Give layout and tab transitions a moment to stabilize
    const timer = setTimeout(updateBoundingRect, 200);
    window.addEventListener('resize', updateBoundingRect);

    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', updateBoundingRect);
      document.querySelectorAll('.tutorial-active-target-glow, .tutorial-coords-extra-bright').forEach((node) => {
        node.classList.remove('tutorial-active-target-glow', 'tutorial-coords-extra-bright');
      });
    };
  }, [isOpen, step, currentStepConfig, onChangeMobilePane, onSelectDrawerTab]);

  // Keyboard navigation: Escape closes, Left/Right navigates
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      } else if (e.key === 'ArrowRight') {
        if (step < TUTORIAL_STEPS.length - 1) onNext();
      } else if (e.key === 'ArrowLeft') {
        if (step > 0) onPrev();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, step, onNext, onPrev, onClose]);

  if (!isOpen || !currentStepConfig) return null;

  const isFirstStep = step === 0;
  const isLastStep = step === TUTORIAL_STEPS.length - 1;
  const isRightPanelTarget =
    currentStepConfig.targetId === 'tutorial-target-ai' ||
    currentStepConfig.targetId === 'tutorial-target-spectrum';

  return (
    <div className="fixed inset-0 z-50 pointer-events-auto select-none overflow-hidden anim-fall">
      {/* Semi-transparent Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-[2px] transition-opacity duration-300"
        onClick={onClose}
      />

      {/* Target Element Highlight Cutout / Glow Ring */}
      {targetRect && (
        <div
          className={`absolute pointer-events-none rounded-xl border-3 ${
            currentStepConfig.targetId === 'tutorial-target-coords'
              ? 'border-emerald-300 shadow-[0_0_55px_rgba(52,211,153,0.95),0_0_30px_rgba(251,191,36,0.7)] ring-8 ring-emerald-400/40 bg-emerald-400/15'
              : 'border-emerald-400 shadow-[0_0_35px_rgba(16,185,129,0.9)] ring-6 ring-emerald-400/30 bg-emerald-400/10'
          } transition-all duration-300 z-50 animate-pulse`}
          style={{
            top: Math.max(4, targetRect.top - 6),
            left: Math.max(4, targetRect.left - 6),
            width: targetRect.width + 12,
            height: targetRect.height + 12,
          }}
        >
          {/* Animated Pointing Arrow Indicator */}
          <div className="absolute -top-8 left-3 bg-gradient-to-r from-emerald-400 to-teal-300 text-gray-950 px-2.5 py-1 rounded-lg font-mono font-bold text-[11px] flex items-center gap-1.5 shadow-[0_0_15px_rgba(16,185,129,0.8)] border border-black/40">
            <span className="text-sm">👇</span>
            <span className="tracking-wide uppercase">{currentStepConfig.targetLabel}</span>
          </div>
        </div>
      )}

      {/* Floating Tutorial Callout Card - Moves to right beside right panel on steps 6 & 7 */}
      <div
        className={`absolute inset-x-3 bottom-3 sm:inset-x-auto ${
          isRightPanelTarget
            ? 'sm:bottom-6 sm:right-[380px] sm:left-auto sm:translate-x-0'
            : 'sm:bottom-6 sm:left-1/2 sm:-translate-x-1/2 sm:right-auto'
        } w-auto sm:w-[480px] max-w-[95vw] max-h-[82vh] overflow-y-auto bg-paper-950/95 border-2 border-emerald-400/80 rounded-2xl shadow-2xl p-4 sm:p-5 text-xs font-mono text-paper-200 z-50 space-y-3.5 backdrop-blur-md`}
      >
        {/* Header with Step Badge and Close */}
        <div className="flex items-center justify-between pb-2 border-b border-paper-800">
          <div className="flex items-center gap-2">
            <span className="p-1 rounded-lg bg-emerald-950 text-emerald-400 border border-emerald-500/40">
              <Sparkles className="w-3.5 h-3.5" />
            </span>
            <span className="text-[10px] font-bold text-emerald-400 tracking-wide uppercase">
              {currentStepConfig.badge}
            </span>
          </div>

          <button
            onClick={onClose}
            className="btn-tactile-sm p-1 rounded-lg border border-paper-800 text-paper-400 hover:text-white cursor-pointer"
            title="Close Tutorial (Esc)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Title */}
        <div>
          <h2 className="text-base sm:text-lg font-bold text-white tracking-tight flex items-center gap-2">
            <span>{currentStepConfig.title}</span>
          </h2>
          <p className="text-[11px] sm:text-xs text-paper-300 mt-1 leading-relaxed">
            {currentStepConfig.description}
          </p>
        </div>

        {/* Informative Bullet Points */}
        <div className="p-3 rounded-xl bg-paper-900 border border-paper-800 space-y-2 text-[11px] leading-relaxed">
          {currentStepConfig.bulletPoints.map((pt, idx) => (
            <div key={idx} className="flex items-start gap-2 text-paper-200">
              <span className="text-emerald-400 font-bold shrink-0 mt-0.5">•</span>
              <span>{pt}</span>
            </div>
          ))}
        </div>

        {/* Step Progression Indicators */}
        <div className="flex items-center justify-center gap-1.5 py-1">
          {TUTORIAL_STEPS.map((_, idx) => (
            <div
              key={idx}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                idx === step
                  ? 'w-6 bg-emerald-400 shadow-[0_0_8px_#10b981]'
                  : idx < step
                  ? 'w-2 bg-emerald-700'
                  : 'w-2 bg-paper-800'
              }`}
            />
          ))}
        </div>

        {/* Actions Bar */}
        <div className="flex items-center justify-between gap-2 pt-2 border-t border-paper-800">
          <button
            type="button"
            onClick={onClose}
            className="btn-tactile-sm px-3 py-1.5 rounded-xl border border-paper-800 text-paper-400 hover:text-white text-[11px] cursor-pointer"
          >
            Skip Tutorial
          </button>

          <div className="flex items-center gap-2">
            {!isFirstStep && (
              <button
                type="button"
                onClick={onPrev}
                className="btn-tactile px-3 py-1.5 rounded-xl bg-paper-900 hover:bg-paper-850 text-paper-200 border-2 border-black font-bold text-[11px] flex items-center gap-1 cursor-pointer"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Back</span>
              </button>
            )}

            <button
              type="button"
              onClick={isLastStep ? onClose : onNext}
              className="btn-tactile px-4 py-1.5 rounded-xl bg-emerald-400 hover:bg-emerald-300 text-gray-950 border-2 border-black font-bold text-[11px] flex items-center gap-1.5 cursor-pointer shadow-[0_0_15px_rgba(16,185,129,0.3)]"
            >
              {isLastStep ? (
                <>
                  <CheckCircle2 className="w-3.5 h-3.5 stroke-[2.5]" />
                  <span>Start Exploring</span>
                </>
              ) : (
                <>
                  <span>Next Step</span>
                  <ArrowRight className="w-3.5 h-3.5 stroke-[2.5]" />
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
