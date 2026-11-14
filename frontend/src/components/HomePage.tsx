import React, { useState } from 'react';
import type { TargetPreset } from '../types/spherex';
import { NASA_TEST_PRESETS } from '../services/mockSpherexApi';
import { Compass, Sparkles, Eye, ShieldCheck, FileCheck, ChevronRight } from 'lucide-react';

interface HomePageProps {
  onSelectTarget: (preset: TargetPreset) => void;
  onEnterCustomCoords: () => void;
  onOpenStep: (stepNumber: number) => void;
}

export const HomePage: React.FC<HomePageProps> = ({
  onSelectTarget,
  onEnterCustomCoords,
  onOpenStep,
}) => {
  const [customRa, setCustomRa] = useState('');
  const [customDec, setCustomDec] = useState('');

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onEnterCustomCoords();
  };

  return (
    <div className="flex-1 overflow-y-auto bg-paper-950 text-paper-100 p-8 md:p-14 select-none">
      <div className="max-w-4xl mx-auto space-y-12">
        {/* Editorial Masthead */}
        <div className="space-y-3 border-b border-paper-800 pb-8">
          <div className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-widest text-paper-400">
            <span className="w-1.5 h-1.5 rounded-full bg-ochre-500" />
            NASA Space Apps Challenge • SPHEREx Survey
          </div>
          <h1 className="text-3xl md:text-5xl font-normal tracking-tight text-paper-100 font-sans">
            SPHEREx Sky-Viewer
          </h1>
          <p className="text-sm md:text-base text-paper-400 max-w-2xl font-sans leading-relaxed">
            A minimalist, volunteer-powered celestial viewer for discovering shifting brown dwarfs,
            planetary bodies, and rapid variable transients across 102 near-infrared bands.
          </p>
        </div>

        {/* Guided Step-by-Step Discovery Protocol (For NASA Judges & Beginners) */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-paper-400">
              Guided Discovery Protocol
            </span>
            <span className="text-[11px] font-mono text-ochre-400">4-Step Citizen Science Workflow</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            {[
              { num: '01', title: 'Target Field', desc: 'Select priority targets or enter sky coordinates.', icon: Compass },
              { num: '02', title: 'Blink Player', desc: 'Play multi-epoch movie to identify moving dipoles.', icon: Eye },
              { num: '03', title: 'Cross-Check', desc: 'Verify against Gaia DR3 & AllWISE catalogs.', icon: ShieldCheck },
              { num: '04', title: 'Dossier Log', desc: 'Log classification and export report for review.', icon: FileCheck },
            ].map((step, idx) => {
              const Icon = step.icon;
              return (
                <div
                  key={step.num}
                  onClick={() => onOpenStep(idx + 1)}
                  className="p-4 rounded-md bg-paper-900 border border-paper-800 hover:border-paper-600 transition-all cursor-pointer group space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-semibold text-ochre-400">{step.num}</span>
                    <Icon className="w-4 h-4 text-paper-500 group-hover:text-paper-100 transition-colors" />
                  </div>
                  <h3 className="font-sans font-medium text-xs text-paper-100 group-hover:text-ochre-300">
                    {step.title}
                  </h3>
                  <p className="text-[11px] text-paper-400 leading-normal">
                    {step.desc}
                  </p>
                </div>
              );
            })}
          </div>
        </div>

        {/* NASA Curated Priority Targets */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-paper-300 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-ochre-400" />
              NASA Priority Benchmark Fields
            </span>
            <span className="text-[11px] font-mono text-paper-500">Test Targets</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {NASA_TEST_PRESETS.map((target) => (
              <div
                key={target.id}
                onClick={() => onSelectTarget(target)}
                className="group bg-paper-900 hover:bg-paper-850 border border-paper-800 hover:border-paper-600 rounded-md p-4 transition-all cursor-pointer flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-sm font-medium text-paper-100 group-hover:text-ochre-300 transition-colors">
                        {target.name}
                      </h3>
                      <p className="text-[11px] text-paper-400 mt-0.5">{target.subtitle}</p>
                    </div>
                    <ChevronRight className="w-4 h-4 text-paper-600 group-hover:text-ochre-400 group-hover:translate-x-0.5 transition-all" />
                  </div>
                  <p className="text-[11px] text-paper-400 mt-2 line-clamp-2 leading-relaxed">
                    {target.description}
                  </p>
                </div>

                <div className="mt-4 pt-2.5 border-t border-paper-800 flex items-center justify-between text-[10px] font-mono text-paper-400">
                  <span>RA: {target.raHms}</span>
                  <span className="text-paper-500">Dec: {target.decDms}</span>
                </div>
              </div>
            ))}

            {/* Custom Coordinate Quick Input */}
            <form
              onSubmit={handleCustomSubmit}
              className="bg-paper-900 border border-dashed border-paper-800 hover:border-paper-600 rounded-md p-4 flex flex-col justify-between space-y-2"
            >
              <div>
                <h3 className="text-sm font-medium text-paper-100 flex items-center gap-1.5">
                  <Compass className="w-3.5 h-3.5 text-ochre-400" />
                  Custom Coordinate Field
                </h3>
                <p className="text-[11px] text-paper-400 mt-0.5">
                  Input custom celestial coordinates.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-1.5 pt-1">
                <input
                  type="text"
                  placeholder="RA (deg)"
                  value={customRa}
                  onChange={(e) => setCustomRa(e.target.value)}
                  className="bg-paper-950 border border-paper-800 rounded px-2 py-1 text-[11px] font-mono text-paper-100 focus:outline-none focus:border-ochre-500"
                />
                <input
                  type="text"
                  placeholder="Dec (deg)"
                  value={customDec}
                  onChange={(e) => setCustomDec(e.target.value)}
                  className="bg-paper-950 border border-paper-800 rounded px-2 py-1 text-[11px] font-mono text-paper-100 focus:outline-none focus:border-ochre-500"
                />
              </div>

              <button
                type="submit"
                className="w-full py-1 bg-paper-800 hover:bg-paper-700 text-paper-100 rounded text-xs font-mono transition-colors"
              >
                Inspect Coordinates
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};
