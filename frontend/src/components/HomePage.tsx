import React, { useState } from 'react';
import type { TargetPreset } from '../types/spherex';
import { NASA_TEST_PRESETS } from '../services/mockSpherexApi';
import { ArrowRight, Sparkles, Compass } from 'lucide-react';

interface HomePageProps {
  onSearchCoordinates: (ra: number, dec: number) => void;
  onSelectPreset: (preset: TargetPreset) => void;
}

export const HomePage: React.FC<HomePageProps> = ({
  onSearchCoordinates,
  onSelectPreset,
}) => {
  const [raInput, setRaInput] = useState('');
  const [decInput, setDecInput] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const parsedRa = parseFloat(raInput);
    const parsedDec = parseFloat(decInput);

    if (isNaN(parsedRa) || isNaN(parsedDec)) {
      setErrorMsg('Please enter valid numeric coordinates (e.g. RA 269.452, Dec 4.693).');
      return;
    }
    if (parsedRa < 0 || parsedRa > 360) {
      setErrorMsg('Right Ascension must be between 0° and 360°.');
      return;
    }
    if (parsedDec < -90 || parsedDec > 90) {
      setErrorMsg('Declination must be between -90° and +90°.');
      return;
    }

    setErrorMsg('');
    onSearchCoordinates(parsedRa, parsedDec);
  };

  return (
    <div className="flex-1 flex flex-col items-center justify-center bg-[#0a0a0e] text-paper-100 p-6 md:p-12 select-none overflow-y-auto">
      <div className="w-full max-w-2xl flex flex-col items-center text-center space-y-8 my-auto">
        
        {/* Tactile Mission Pill */}
        <div className="btn-tactile-sm inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-paper-900 border-2 border-black text-[11px] font-mono text-paper-300">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>NASA Space Apps • SPHEREx Survey</span>
          <span className="text-paper-500 font-sans">|</span>
          <span className="text-emerald-400 font-medium">102 Spectrophotometric Bands</span>
        </div>

        {/* Big Prominent Name in the Middle */}
        <div className="space-y-3">
          <h1 className="text-4xl sm:text-6xl md:text-7xl font-bold tracking-tight text-paper-100 font-sans">
            SPHEREx <span className="text-emerald-400">Sky</span>
            <span className="text-ochre-400 font-light">Viewer</span>
          </h1>
          <p className="text-sm md:text-base text-paper-400 font-sans max-w-md mx-auto leading-relaxed">
            Search celestial coordinates or explore NASA benchmark targets to blink multi-epoch infrared exposures.
          </p>
        </div>

        {/* Central Tactile Search Box (GitIngest-style card & pop-up button) */}
        <div className="w-full space-y-3">
          <form
            onSubmit={handleSearch}
            className="w-full p-2.5 rounded-2xl bg-paper-900 border-2 border-black card-tactile flex flex-col sm:flex-row gap-2.5"
          >
            {/* RA Input */}
            <div className="flex-1 flex items-center px-3.5 py-2.5 bg-paper-950 rounded-xl border-2 border-black/80 focus-within:border-emerald-400 transition-colors">
              <span className="text-[11px] font-mono text-emerald-400 font-bold mr-2 uppercase">RA</span>
              <input
                type="text"
                placeholder="269.4520°"
                value={raInput}
                onChange={(e) => setRaInput(e.target.value)}
                className="w-full bg-transparent text-xs font-mono text-paper-100 focus:outline-none placeholder:text-paper-600"
              />
            </div>

            {/* Dec Input */}
            <div className="flex-1 flex items-center px-3.5 py-2.5 bg-paper-950 rounded-xl border-2 border-black/80 focus-within:border-emerald-400 transition-colors">
              <span className="text-[11px] font-mono text-emerald-400 font-bold mr-2 uppercase">Dec</span>
              <input
                type="text"
                placeholder="+04.6933°"
                value={decInput}
                onChange={(e) => setDecInput(e.target.value)}
                className="w-full bg-transparent text-xs font-mono text-paper-100 focus:outline-none placeholder:text-paper-600"
              />
            </div>

            {/* Tactile Pop-up Explore Button */}
            <button
              type="submit"
              className="btn-tactile px-6 py-2.5 bg-emerald-400 hover:bg-emerald-300 text-gray-950 border-2 border-black rounded-xl font-mono text-xs font-bold flex items-center justify-center gap-2 shrink-0 cursor-pointer"
            >
              <span>Explore Sky</span>
              <ArrowRight className="w-4 h-4 stroke-[2.5]" />
            </button>
          </form>

          {errorMsg && (
            <p className="text-[11px] font-mono text-rose-400 text-center animate-in fade-in pt-1">
              {errorMsg}
            </p>
          )}
        </div>

        {/* Real SPHEREx Interim Results Feature Card */}
        <div
          onClick={() => onSelectPreset(NASA_TEST_PRESETS[0])}
          className="w-full p-4 rounded-2xl bg-paper-900 border-2 border-emerald-500/80 card-tactile cursor-pointer hover:border-emerald-400 text-left transition-all group"
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="font-mono font-bold text-xs text-emerald-400 uppercase tracking-wider">
                Real Interim Result: 3I/ATLAS Comet
              </span>
            </div>
            <span className="text-[10px] font-mono text-paper-300 bg-paper-950 px-2 py-0.5 rounded border border-paper-700">
              NASA/IPAC IRSA QR2
            </span>
          </div>

          <p className="text-xs text-paper-300 font-sans leading-relaxed">
            Detector found interstellar comet <strong className="text-white">3I/ATLAS</strong> in all 4 real SPHEREx exposures within <strong className="text-emerald-300">0.54 pixels</strong> of predicted ephemeris. Track ranked <strong>#1 of 25</strong> (Baseline) and <strong>#2 of 25</strong> (Random Forest ML).
          </p>

          <div className="mt-3 flex items-center justify-between text-[11px] font-mono text-emerald-400 pt-2 border-t border-paper-800/80">
            <span>RA 166.790° • Dec +05.290° (Band 6: 4.47–4.85 µm)</span>
            <span className="group-hover:translate-x-1 transition-transform flex items-center gap-1 font-bold">
              Load Real Exposures →
            </span>
          </div>
        </div>

        {/* Benchmark Presets: Styled like GitIngest's example repo pills */}
        <div className="w-full space-y-3 pt-6 border-t border-paper-800/80">
          <div className="flex items-center justify-center gap-1.5 text-[11px] font-mono text-paper-400">
            <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
            <span>Try NASA Test Benchmark Targets:</span>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-2.5">
            {NASA_TEST_PRESETS.map((preset) => (
              <button
                key={preset.id}
                onClick={() => onSelectPreset(preset)}
                className="btn-tactile-sm px-3.5 py-2 rounded-xl bg-paper-900 border-2 border-black text-xs font-mono text-paper-200 hover:text-emerald-300 hover:border-emerald-400 transition-all flex items-center gap-2 group cursor-pointer"
                title={`${preset.name} (${preset.subtitle})\nRA: ${preset.raHms} | Dec: ${preset.decDms}`}
              >
                <Compass className="w-3.5 h-3.5 text-emerald-400 group-hover:rotate-45 transition-transform" />
                <span className="font-semibold">{preset.name}</span>
                <span className="text-[10px] text-paper-500 font-sans bg-paper-950 px-1.5 py-0.5 rounded border border-black/50">
                  {preset.subtitle}
                </span>
              </button>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
};
