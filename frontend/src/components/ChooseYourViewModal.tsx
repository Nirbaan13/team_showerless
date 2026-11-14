import React from 'react';
import { Eye, Microscope, Check, Sparkles } from 'lucide-react';

interface ChooseYourViewModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentMode: 'volunteer' | 'scientist';
  onSelectMode: (mode: 'volunteer' | 'scientist') => void;
}

export const ChooseYourViewModal: React.FC<ChooseYourViewModalProps> = ({
  isOpen,
  onClose,
  currentMode,
  onSelectMode,
}) => {
  if (!isOpen) return null;

  const handleChoose = (mode: 'volunteer' | 'scientist') => {
    onSelectMode(mode);
    try {
      localStorage.setItem('spherex_view_mode', mode);
    } catch {
      // localStorage may fail in sandboxed iframes
    }
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200 select-none">
      <div className="w-full max-w-xl bg-paper-900 border-2 border-black rounded-2xl card-tactile shadow-2xl overflow-hidden text-paper-100 flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-paper-800 bg-paper-950 text-center space-y-2">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-paper-900 border border-paper-700 text-[11px] font-mono text-emerald-400">
            <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
            <span>NASA Space Apps Challenge</span>
          </div>
          <h2 className="text-2xl font-bold font-sans tracking-tight text-white">
            Choose Your View
          </h2>
          <p className="text-xs text-paper-400 max-w-md mx-auto leading-relaxed">
            Select your preferred interface mode. You can toggle between them at any time in the top navigation bar.
          </p>
        </div>

        {/* View Options Cards */}
        <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-4 bg-paper-900">
          {/* Option 1: Volunteer */}
          <div
            onClick={() => handleChoose('volunteer')}
            className={`p-5 rounded-xl border-2 cursor-pointer transition-all flex flex-col justify-between group ${
              currentMode === 'volunteer'
                ? 'border-emerald-400 bg-paper-950 shadow-md ring-2 ring-emerald-400/20'
                : 'border-black bg-paper-950/70 hover:border-paper-600 hover:bg-paper-950'
            }`}
          >
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="w-10 h-10 rounded-xl bg-emerald-400/10 border border-emerald-400/30 flex items-center justify-center text-emerald-400 group-hover:scale-105 transition-transform">
                  <Eye className="w-5 h-5" />
                </div>
                {currentMode === 'volunteer' && (
                  <span className="flex items-center gap-1 text-[10px] font-mono text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded-full border border-emerald-800">
                    <Check className="w-3 h-3" /> Active
                  </span>
                )}
              </div>

              <div>
                <h3 className="font-bold text-base text-paper-100 group-hover:text-emerald-300 transition-colors">
                  Volunteer
                </h3>
                <span className="text-[10px] font-mono text-paper-400 uppercase tracking-wider block mt-0.5">
                  Citizen Science Explorer
                </span>
              </div>

              <p className="text-xs text-paper-400 leading-relaxed">
                Clean, intuitive starfield optimized for human pattern recognition. Rapid multi-epoch blinking to spot Planet 9, moving asteroids, and anomalous transients.
              </p>
            </div>

            <button
              onClick={(e) => {
                e.stopPropagation();
                handleChoose('volunteer');
              }}
              className="mt-5 btn-tactile w-full py-2.5 bg-emerald-400 hover:bg-emerald-300 text-gray-950 rounded-lg font-mono text-xs font-bold border-2 border-black flex items-center justify-center gap-2 cursor-pointer"
            >
              <span>Select Volunteer</span>
            </button>
          </div>

          {/* Option 2: Scientist */}
          <div
            onClick={() => handleChoose('scientist')}
            className={`p-5 rounded-xl border-2 cursor-pointer transition-all flex flex-col justify-between group ${
              currentMode === 'scientist'
                ? 'border-emerald-400 bg-paper-950 shadow-md ring-2 ring-emerald-400/20'
                : 'border-black bg-paper-950/70 hover:border-paper-600 hover:bg-paper-950'
            }`}
          >
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="w-10 h-10 rounded-xl bg-ochre-400/10 border border-ochre-400/30 flex items-center justify-center text-ochre-400 group-hover:scale-105 transition-transform">
                  <Microscope className="w-5 h-5" />
                </div>
                {currentMode === 'scientist' && (
                  <span className="flex items-center gap-1 text-[10px] font-mono text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded-full border border-emerald-800">
                    <Check className="w-3 h-3" /> Active
                  </span>
                )}
              </div>

              <div>
                <h3 className="font-bold text-base text-paper-100 group-hover:text-emerald-300 transition-colors">
                  Scientist
                </h3>
                <span className="text-[10px] font-mono text-paper-400 uppercase tracking-wider block mt-0.5">
                  Astrophysics Telemetry
                </span>
              </div>

              <p className="text-xs text-paper-400 leading-relaxed">
                Full mission data pipeline: Equatorial coordinate grid, live Astrophysics HUD (L2/L3), PSF Gaussian FWHM contours, 102-band spectrophotometric curves, and FITS headers.
              </p>
            </div>

            <button
              onClick={(e) => {
                e.stopPropagation();
                handleChoose('scientist');
              }}
              className="mt-5 btn-tactile w-full py-2.5 bg-paper-800 hover:bg-paper-700 text-emerald-300 rounded-lg font-mono text-xs font-bold border-2 border-black flex items-center justify-center gap-2 cursor-pointer"
            >
              <span>Select Scientist</span>
            </button>
          </div>
        </div>

        {/* Footer */}
        <div className="p-3.5 bg-paper-950 border-t border-paper-800 flex items-center justify-between text-[11px] font-mono text-paper-400 px-6">
          <span>You can switch anytime in the top bar</span>
          <button
            onClick={onClose}
            className="text-paper-400 hover:text-white underline cursor-pointer"
          >
            Continue with current
          </button>
        </div>
      </div>
    </div>
  );
};
