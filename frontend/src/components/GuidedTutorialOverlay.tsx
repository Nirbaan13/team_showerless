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
}

const TUTORIAL_STEPS: StepConfig[] = [
  {
    targetId: 'tutorial-target-coords',
    stepNum: 1,
    totalSteps: 4,
    badge: 'Step 1 of 4 • Sky Coordinates',
    title: 'Astronomical Coordinates (RA & Dec)',
    description:
      'Celestial coordinates pinpoint an exact position in the cosmos, similar to latitude and longitude on Earth:',
    bulletPoints: [
      'Right Ascension (RA): Celestial longitude, measured in degrees (0° to 360°) or hours (0h to 24h).',
      'Declination (Dec): Celestial latitude, measured from -90° (South celestial pole) to +90° (North celestial pole).',
      'Quick Usage: Type RA and Dec here and click "Update Field", or pick NASA test targets (like Comet 3I/ATLAS or Asteroid 4 Vesta).',
    ],
    arrowDirection: 'left',
    targetLabel: 'RA & Dec Coordinate Inputs',
    mobilePane: 'controls',
  },
  {
    targetId: 'tutorial-target-fov',
    stepNum: 2,
    totalSteps: 4,
    badge: 'Step 2 of 4 • Angular Scale',
    title: 'Field of View (FOV)',
    description:
      'Field of View defines the angular diameter of the sky patch displayed on screen, measured in arcminutes (′), where 60′ = 1°:',
    bulletPoints: [
      "1′ to 3′ (High Magnification): Optimal for inspecting individual asteroid point-spread functions and cometary coma centroids.",
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
    totalSteps: 4,
    badge: 'Step 3 of 4 • Multi-Epoch Inspection',
    title: 'Sky View Panel & Blink Comparator',
    description:
      'This is your primary visual laboratory for spotting transient and moving objects across time:',
    bulletPoints: [
      'Leave-One-Out Blink Differencing: The comparator median-combines alternate epochs. Static background stars cancel out, causing moving asteroids or variable stars to stand out as distinct bright dipoles.',
      'Movie Playback Controls: Play time-lapses at 1 to 30 FPS, step frame-by-frame, and toggle ZScale automatic contrast stretching.',
      'Adaptive Canvas: Click any candidate reticle on the canvas to inspect its astrometric trajectory and spectral signature.',
    ],
    arrowDirection: 'bottom',
    targetLabel: 'Multi-Epoch Canvas & Playback Bar',
    mobilePane: 'canvas',
  },
  {
    targetId: 'tutorial-target-bands',
    stepNum: 4,
    totalSteps: 4,
    badge: 'Step 4 of 4 • Scientific Discovery',
    title: '102 Spectral Channels & Community Verification',
    description:
      'SPHEREx observes the full sky across 6 detector arrays (D1 to D6) spanning 102 near-infrared spectrophotometric channels (0.75 - 5.0 μm):',
    bulletPoints: [
      'Chemical Diagnostics: Measure flux density (F_λ) across 102 bands to identify water ice (1.5, 2.0, 3.05 μm), CO₂ ice (4.27 μm), and silicates.',
      'AI Trajectory Detection: The built-in ML engine links candidate motion vectors and BLOOM saturated centroids across epochs.',
      'Community Consensus Pipeline: Click "Verify" to discuss discoveries in the Verification Feed. When 10 community members confirm a candidate, it auto-submits to the Minor Planet Center!',
    ],
    arrowDirection: 'left',
    targetLabel: 'Infrared Filter Arrays & Analysis Drawer',
    mobilePane: 'controls',
  },
];

export const GuidedTutorialOverlay: React.FC<GuidedTutorialOverlayProps> = ({
  isOpen,
  step,
  onNext,
  onPrev,
  onClose,
  onChangeMobilePane,
}) => {
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);

  const currentStepConfig = TUTORIAL_STEPS[Math.min(step, TUTORIAL_STEPS.length - 1)];

  // Update target bounding box and scroll element into view
  useEffect(() => {
    if (!isOpen || !currentStepConfig) return;

    if (onChangeMobilePane) {
      onChangeMobilePane(currentStepConfig.mobilePane);
    }

    const updateBoundingRect = () => {
      const el = document.getElementById(currentStepConfig.targetId);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        setTargetRect(el.getBoundingClientRect());
      } else {
        setTargetRect(null);
      }
    };

    // Give layout moment to stabilize
    const timer = setTimeout(updateBoundingRect, 150);
    window.addEventListener('resize', updateBoundingRect);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', updateBoundingRect);
    };
  }, [isOpen, step, currentStepConfig, onChangeMobilePane]);

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
          className="absolute pointer-events-none rounded-xl border-2 border-emerald-400 shadow-[0_0_25px_rgba(16,185,129,0.8)] ring-4 ring-emerald-400/30 transition-all duration-300 z-50 animate-pulse"
          style={{
            top: Math.max(8, targetRect.top - 4),
            left: Math.max(8, targetRect.left - 4),
            width: targetRect.width + 8,
            height: targetRect.height + 8,
          }}
        >
          {/* Animated Pointing Arrow Indicator */}
          <div className="absolute -top-7 left-3 bg-emerald-400 text-gray-950 px-2 py-0.5 rounded font-mono font-bold text-[10px] flex items-center gap-1 shadow-lg">
            <span>👇</span>
            <span>{currentStepConfig.targetLabel}</span>
          </div>
        </div>
      )}

      {/* Floating Tutorial Callout Card */}
      <div className="absolute inset-x-3 bottom-3 sm:inset-x-auto sm:bottom-auto sm:top-16 sm:right-6 md:right-8 w-auto sm:w-[440px] max-w-[95vw] max-h-[85vh] overflow-y-auto bg-paper-950/95 border-2 border-emerald-400/80 rounded-2xl shadow-2xl p-4 sm:p-5 text-xs font-mono text-paper-200 z-50 space-y-3.5 backdrop-blur-md">
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
