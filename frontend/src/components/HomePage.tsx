import React, { useState } from 'react';
import type { TargetPreset } from '../types/spherex';
import { NASA_TEST_PRESETS } from '../services/mockSpherexApi';
import { ArrowRight, Compass } from 'lucide-react';

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
    <div className="relative flex-1 flex flex-col items-center justify-center text-paper-100 p-6 md:p-12 select-none overflow-y-auto">
      {/* Wide space photo background */}
      <div
        aria-hidden
        className="absolute inset-0 bg-cover bg-center"
        style={{ backgroundImage: "url('/space-hero.jpg')" }}
      />
      <div aria-hidden className="absolute inset-0 bg-gradient-to-b from-black/40 via-black/30 to-[#0a0a0e]/90" />

      <div className="relative w-full max-w-4xl flex flex-col items-center text-center space-y-10 my-auto">
        {/* Big Prominent Name */}
        <h1 className="anim-fall text-6xl sm:text-8xl md:text-9xl font-bold tracking-tight text-white font-sans leading-[0.95] drop-shadow-[0_4px_24px_rgba(0,0,0,0.8)]">
          SPHEREx
          <br />
          <span className="text-emerald-400">Sky</span>{' '}
          <span className="text-ochre-400 font-light">Viewer</span>
        </h1>

        {/* Coordinate Search */}
        <div className="anim-fall w-full max-w-2xl space-y-3" style={{ animationDelay: '120ms' }}>
          <form
            onSubmit={handleSearch}
            className="w-full p-2.5 rounded-2xl bg-paper-900/90 backdrop-blur border-2 border-black card-tactile flex flex-col sm:flex-row gap-2.5"
          >
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

            <button
              type="submit"
              className="btn-tactile px-6 py-2.5 bg-emerald-400 hover:bg-emerald-300 text-gray-950 border-2 border-black rounded-xl font-mono text-xs font-bold flex items-center justify-center gap-2 shrink-0 cursor-pointer"
            >
              <span>Explore Sky</span>
              <ArrowRight className="w-4 h-4 stroke-[2.5]" />
            </button>
          </form>

          {errorMsg && (
            <p className="text-[11px] font-mono text-rose-400 text-center pt-1">{errorMsg}</p>
          )}
        </div>

        {/* Quick targets */}
        <div className="anim-fall flex flex-wrap items-center justify-center gap-2.5" style={{ animationDelay: '220ms' }}>
          {NASA_TEST_PRESETS.map((preset) => (
            <button
              key={preset.id}
              onClick={() => onSelectPreset(preset)}
              className="btn-tactile-sm px-3.5 py-2 rounded-xl bg-paper-900/90 border-2 border-black text-xs font-mono text-paper-200 hover:text-emerald-300 transition-all flex items-center gap-2 group cursor-pointer"
              title={`${preset.name} (${preset.subtitle})`}
            >
              <Compass className="w-3.5 h-3.5 text-emerald-400 group-hover:rotate-45 transition-transform" />
              <span className="font-semibold">{preset.name}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
