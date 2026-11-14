import React, { useState } from 'react';
import type { TargetPreset } from '../types/spherex';
import { NASA_TEST_PRESETS } from '../services/mockSpherexApi';
import {
  REAL_3I_ATLAS_FRAMES,
  REAL_BARNARD_FRAMES,
  REAL_WISE_0855_FRAMES,
} from '../services/realSpherexFrames';
import { ArrowRight, Compass, UserCheck } from 'lucide-react';

interface HomePageProps {
  onSearchCoordinates: (ra: number, dec: number) => void;
  onSelectPreset: (preset: TargetPreset) => void;
  onOpenFeed?: () => void;
}

export const HomePage: React.FC<HomePageProps> = ({
  onSearchCoordinates,
  onSelectPreset,
  onOpenFeed,
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

      <div className="relative w-full max-w-4xl flex flex-col items-center text-center space-y-8 my-auto">
        {/* Big Prominent Name with cinematic reveal & pulse glow */}
        <h1 className="anim-hero-title text-6xl sm:text-8xl md:text-9xl font-bold tracking-tight text-white font-sans leading-[0.95] drop-shadow-[0_4px_30px_rgba(0,0,0,0.9)] select-none">
          SPHEREx
          <br />
          <span className="text-emerald-400 anim-blink-glow inline-block">Blink</span>
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

        {/* Dedicated Sky Blue Button: Community Verification Feed */}
        {onOpenFeed && (
          <div className="anim-fall pt-1" style={{ animationDelay: '280ms' }}>
            <button
              onClick={onOpenFeed}
              className="btn-tactile px-5 py-2.5 rounded-xl bg-sky-400 hover:bg-sky-300 text-gray-950 border-2 border-black font-mono text-xs font-bold flex items-center gap-2 group cursor-pointer shadow-[0_0_20px_rgba(56,189,248,0.35)] transition-all"
            >
              <UserCheck className="w-4 h-4 stroke-[2.5] text-gray-950 group-hover:scale-110 transition-transform" />
              <span>Community Verification Feed</span>
              <ArrowRight className="w-3.5 h-3.5 stroke-[2.5] text-gray-950" />
            </button>
          </div>
        )}

        {/* 2D Verification Feed: Real NASA SPHEREx Calibrated Targets */}
        <div className="anim-fall w-full max-w-4xl pt-4 space-y-3" style={{ animationDelay: '340ms' }}>
          <div className="flex items-center justify-between px-1">
            <span className="font-mono text-[11px] text-emerald-400 uppercase font-bold tracking-wider flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
              2D Verification Feed: Calibrated SPHEREx Images
            </span>
            {onOpenFeed && (
              <button
                onClick={onOpenFeed}
                className="text-[11px] font-mono text-sky-400 hover:text-sky-300 transition-colors cursor-pointer flex items-center gap-1"
              >
                <span>View All Discussions</span>
                <ArrowRight className="w-3 h-3" />
              </button>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[
              {
                id: '3i-atlas',
                name: '3I/ATLAS Comet',
                type: 'Interstellar Interloper',
                badge: 'NASA QR2 Detection',
                priority: 'P1',
                pBg: '#ef4444',
                thumb: REAL_3I_ATLAS_FRAMES[2]?.pngDataUrl,
                coords: 'RA 166.790°, Dec +05.290°',
                desc: 'Hyperbolic track across 4 QR2 frames within 0.54 px of JPL Horizons.',
              },
              {
                id: 'barnards-star',
                name: "Barnard's Star",
                type: 'High Proper Motion Red Dwarf',
                badge: '5-Epoch Multi-Blink',
                priority: 'P1',
                pBg: '#ef4444',
                thumb: REAL_BARNARD_FRAMES[2]?.pngDataUrl,
                coords: 'RA 269.452°, Dec +04.693°',
                desc: 'Fast apparent vector motion (10.3″/yr) with confirmed Gaia DR3 cross-match.',
              },
              {
                id: 'wise-0855',
                name: 'WISE 0855-0714',
                type: 'Coldest Sub-Brown Dwarf',
                badge: 'Band 5/6 Ice Clouds',
                priority: 'P1',
                pBg: '#ef4444',
                thumb: REAL_WISE_0855_FRAMES[0]?.pngDataUrl,
                coords: 'RA 133.795°, Dec -07.245°',
                desc: 'Y-type sub-stellar object exhibiting strong atmospheric H2O ice absorption.',
              },
            ].map((feedItem) => {
              const matchingPreset = NASA_TEST_PRESETS.find((p) => p.id === feedItem.id);
              if (!matchingPreset) return null;

              return (
                <div
                  key={feedItem.id}
                  onClick={() => onSelectPreset(matchingPreset)}
                  className="p-3 rounded-xl bg-paper-900/95 border-2 border-black hover:border-emerald-400/80 transition-all card-tactile cursor-pointer group flex flex-col justify-between space-y-2.5 text-left"
                >
                  <div className="space-y-2">
                    {/* 2D Cutout Thumbnail */}
                    <div className="relative w-full h-28 rounded-lg overflow-hidden bg-black border border-black/80 flex items-center justify-center">
                      <img
                        src={feedItem.thumb}
                        alt={feedItem.name}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                      />
                      {/* Optical Reticle */}
                      <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                        <div className="w-5 h-5 rounded-full border border-rose-500/90 animate-pulse flex items-center justify-center">
                          <div className="w-1 h-1 rounded-full bg-rose-400" />
                        </div>
                      </div>
                      <span className="absolute bottom-1 left-1 px-1.5 py-0.5 rounded bg-black/85 font-mono text-[8px] text-emerald-300 font-bold border border-emerald-400/30">
                        2D FITS Cutout
                      </span>
                    </div>

                    <div className="space-y-1">
                      <div className="flex items-center justify-between gap-1">
                        <span
                          style={{ backgroundColor: feedItem.pBg }}
                          className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded text-white shadow-sm border border-black/40"
                        >
                          {feedItem.priority}
                        </span>
                        <span className="text-[9px] font-mono text-emerald-300 px-1.5 py-0.5 rounded bg-paper-950 border border-paper-800">
                          {feedItem.badge}
                        </span>
                      </div>
                      <h4 className="text-xs font-bold font-sans text-paper-100 group-hover:text-emerald-300 transition-colors">
                        {feedItem.name}
                      </h4>
                      <p className="text-[10px] font-sans text-paper-400 leading-snug line-clamp-2">
                        {feedItem.desc}
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    className="w-full py-1.5 rounded-lg bg-emerald-400 group-hover:bg-emerald-300 text-gray-950 font-mono text-[10px] font-bold border-2 border-black flex items-center justify-center gap-1.5 transition-transform"
                  >
                    <span>Verify in Sky Viewer</span>
                    <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
