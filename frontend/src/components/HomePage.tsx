import React, { useState } from 'react';
import type { TargetPreset } from '../types/spherex';
import { NASA_TEST_PRESETS } from '../services/mockSpherexApi';
import { ArrowRight, Sparkles } from 'lucide-react';

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
      setErrorMsg('Please enter valid numeric coordinates (e.g., RA 269.452, Dec 4.693).');
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
    <div className="flex-1 flex flex-col items-center justify-center bg-paper-950 text-paper-100 p-6 md:p-12 select-none overflow-y-auto">
      <div className="w-full max-w-2xl flex flex-col items-center text-center space-y-8 my-auto">
        
        {/* Subtle Mission Tag */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-paper-900 border border-paper-800 text-[11px] font-mono text-paper-400">
          <span className="w-1.5 h-1.5 rounded-full bg-ochre-500" />
          NASA Space Apps Challenge • SPHEREx Survey
        </div>

        {/* Big Prominent Name in the Middle */}
        <div className="space-y-3">
          <h1 className="text-4xl sm:text-6xl md:text-7xl font-light tracking-tight text-paper-100 font-sans">
            SPHEREx <span className="font-medium text-ochre-400">Sky-Viewer</span>
          </h1>
          <p className="text-sm md:text-base text-paper-400 font-sans max-w-md mx-auto leading-relaxed">
            Search any celestial patch or test benchmark targets to blink multi-epoch infrared exposures.
          </p>
        </div>

        {/* Central Search Coordinates Box */}
        <div className="w-full space-y-2">
          <form
            onSubmit={handleSearch}
            className="w-full p-2 rounded-xl bg-paper-900 border border-paper-800 focus-within:border-ochre-500/80 transition-all shadow-xl flex flex-col sm:flex-row gap-2"
          >
            <div className="flex-1 flex items-center px-3 py-2.5 bg-paper-950 rounded-lg border border-paper-800/80">
              <span className="text-[11px] font-mono text-paper-500 mr-2 uppercase">RA</span>
              <input
                type="text"
                placeholder="269.4520"
                value={raInput}
                onChange={(e) => setRaInput(e.target.value)}
                className="w-full bg-transparent text-xs font-mono text-paper-100 focus:outline-none placeholder:text-paper-600"
              />
            </div>

            <div className="flex-1 flex items-center px-3 py-2.5 bg-paper-950 rounded-lg border border-paper-800/80">
              <span className="text-[11px] font-mono text-paper-500 mr-2 uppercase">Dec</span>
              <input
                type="text"
                placeholder="+4.6933"
                value={decInput}
                onChange={(e) => setDecInput(e.target.value)}
                className="w-full bg-transparent text-xs font-mono text-paper-100 focus:outline-none placeholder:text-paper-600"
              />
            </div>

            <button
              type="submit"
              className="px-6 py-2.5 bg-paper-100 hover:bg-white text-paper-950 rounded-lg font-mono text-xs font-semibold flex items-center justify-center gap-2 transition-all shrink-0 shadow-sm"
            >
              <span>Explore Sky</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </form>

          {errorMsg && (
            <p className="text-[11px] font-mono text-rose-400 text-center animate-in fade-in pt-1">
              {errorMsg}
            </p>
          )}
        </div>

        {/* Benchmark Presets: Cleanly located right below coordinates */}
        <div className="w-full space-y-3 pt-6 border-t border-paper-800/60">
          <div className="flex items-center justify-center gap-1.5 text-[11px] font-mono text-paper-400">
            <Sparkles className="w-3.5 h-3.5 text-ochre-400" />
            <span>NASA Test Benchmark Targets:</span>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-2">
            {NASA_TEST_PRESETS.map((preset) => (
              <button
                key={preset.id}
                onClick={() => onSelectPreset(preset)}
                className="px-3.5 py-2 rounded-lg bg-paper-900 hover:bg-paper-800 border border-paper-800 hover:border-ochre-500/50 text-xs font-mono text-paper-200 transition-all flex items-center gap-2 group"
                title={`${preset.name} (${preset.subtitle})\nRA: ${preset.raHms} | Dec: ${preset.decDms}`}
              >
                <span className="group-hover:text-ochre-300 transition-colors">{preset.name}</span>
                <span className="text-[10px] text-paper-500 font-sans">
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
