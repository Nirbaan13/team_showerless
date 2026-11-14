import React from 'react';
import type { TargetPreset } from '../types/spherex';
import { NASA_TEST_PRESETS } from '../services/mockSpherexApi';
import { Compass, ArrowRight, ShieldCheck, Layers, Radio, Sparkles } from 'lucide-react';

interface HomePageProps {
  onSelectTarget: (preset: TargetPreset) => void;
  onEnterCustomCoords: () => void;
}

export const HomePage: React.FC<HomePageProps> = ({ onSelectTarget, onEnterCustomCoords }) => {
  return (
    <div className="flex-1 overflow-y-auto bg-[#080c14] text-slate-100 p-8 md:p-12 lg:p-16 select-none">
      <div className="max-w-5xl mx-auto space-y-12">
        {/* Mission Header */}
        <div className="space-y-4 border-b border-slate-800/80 pb-8">
          <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-slate-400">
            <span className="w-2 h-2 rounded-full bg-blue-500" />
            NASA Space Apps Challenge • SPHEREx All-Sky Survey
          </div>
          <h1 className="text-3xl md:text-5xl font-semibold tracking-tight text-white font-sans">
            SPHEREx Sky-Viewer
          </h1>
          <p className="text-base md:text-lg text-slate-400 max-w-3xl font-sans leading-relaxed">
            Explore 102 bands of near-infrared sky imagery captured by NASA's SPHEREx mission.
            Detect moving brown dwarfs, variable transients, and planetary bodies across multiple observation epochs.
          </p>
        </div>

        {/* 5 NASA Requested Targets */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300 font-mono flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-amber-400" />
              NASA Priority Test Targets
            </h2>
            <span className="text-xs text-slate-500 font-mono">5 Curated Verification Fields</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {NASA_TEST_PRESETS.map((target) => (
              <div
                key={target.id}
                onClick={() => onSelectTarget(target)}
                className="group relative bg-[#0d131f] hover:bg-[#121a2b] border border-slate-800 hover:border-blue-500/60 rounded-lg p-5 transition-all cursor-pointer flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-base font-semibold text-white group-hover:text-blue-400 transition-colors">
                        {target.name}
                      </h3>
                      <p className="text-xs text-slate-400 mt-0.5">{target.subtitle}</p>
                    </div>
                    <ArrowRight className="w-4 h-4 text-slate-600 group-hover:text-blue-400 group-hover:translate-x-1 transition-all" />
                  </div>

                  <p className="text-xs text-slate-400 mt-3 line-clamp-2 leading-relaxed">
                    {target.description}
                  </p>
                </div>

                <div className="mt-5 pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] font-mono text-slate-400">
                  <span>RA: {target.raHms}</span>
                  <span className="text-slate-500">Dec: {target.decDms}</span>
                </div>
              </div>
            ))}

            {/* Custom Coordinates Card */}
            <div
              onClick={onEnterCustomCoords}
              className="bg-[#0d131f]/60 hover:bg-[#121a2b] border border-dashed border-slate-800 hover:border-blue-500/60 rounded-lg p-5 transition-all cursor-pointer flex flex-col items-center justify-center text-center space-y-2"
            >
              <div className="w-10 h-10 rounded-full bg-slate-900 border border-slate-700 flex items-center justify-center text-slate-400 group-hover:text-blue-400">
                <Compass className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-semibold text-white">Custom Sky Patch</h3>
              <p className="text-xs text-slate-400 max-w-[200px]">
                Input arbitrary Right Ascension & Declination coordinates.
              </p>
            </div>
          </div>
        </div>

        {/* How It Works & Scientific Features */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-4 border-t border-slate-800/80">
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
              <Layers className="w-4 h-4 text-blue-400" />
              Multi-Epoch Blinking
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Compare celestial exposures across observation epochs to instantly spot moving point sources and rapid transients.
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
              <Radio className="w-4 h-4 text-blue-400" />
              102-Band Spectrophotometry
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Resolve continuous near-infrared spectra (0.75 - 5.00 µm) to classify water, carbon dioxide, and silicate features.
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              Catalog Cross-Verification
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Automatically cross-references Gaia DR3, AllWISE, and Solar System ephemerides to prevent duplicate candidate reporting.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
