import React, { useState } from 'react';
import { Copy, Check, X } from 'lucide-react';
import type { FOVOption, DetectorArrayId, SubtractionMode } from '../types/spherex';

interface EmbedModalProps {
  isOpen: boolean;
  onClose: () => void;
  ra: number;
  dec: number;
  fov: FOVOption;
  selectedArray: DetectorArrayId | 'all';
  subtractionMode: SubtractionMode;
  activeFrameIndex: number;
}

export const EmbedModal: React.FC<EmbedModalProps> = ({
  isOpen,
  onClose,
  ra,
  dec,
  fov,
  selectedArray,
  subtractionMode,
  activeFrameIndex,
}) => {
  const [copied, setCopied] = useState(false);
  const [width, setWidth] = useState('800');
  const [height, setHeight] = useState('540');

  if (!isOpen) return null;

  const params = new URLSearchParams({
    ra: ra.toFixed(6),
    dec: dec.toFixed(6),
    fov,
    detector: String(selectedArray),
    subtraction: subtractionMode,
    frame: String(activeFrameIndex),
    embed: 'true',
  });

  const embedUrl = `${window.location.origin}${window.location.pathname}?${params.toString()}`;
  const iframeSnippet = `<iframe src="${embedUrl}" width="${width}" height="${height}" frameborder="0" allowfullscreen style="border: 1px solid #21262d; border-radius: 8px;"></iframe>`;

  const handleCopy = () => {
    navigator.clipboard.writeText(iframeSnippet).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2200);
    });
  };

  return (
    <div className="fixed inset-0 bg-space-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-space-900 border border-space-700 rounded-lg max-w-lg w-full p-5 space-y-4 shadow-2xl animate-in fade-in duration-150">
        <div className="flex items-center justify-between border-b border-space-800 pb-3">
          <div className="font-telemetry font-bold text-space-100 text-sm tracking-wide flex items-center gap-2">
            <span>Embed SPHEREx Sky-Viewer</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded text-space-400 hover:text-space-200 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="text-xs text-space-300 font-sans leading-relaxed">
          Embed this interactive celestial blink viewport directly into external citizen science research blogs, NASA Space Apps showcase pages, or community discovery forums.
        </p>

        {/* Dimension inputs */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] font-mono text-space-400 block mb-1">Width (px)</label>
            <input
              type="text"
              value={width}
              onChange={(e) => setWidth(e.target.value)}
              className="w-full bg-space-950 border border-space-700 rounded px-2.5 py-1.5 font-mono text-xs text-space-100 focus:outline-none focus:border-cyan-400"
            />
          </div>
          <div>
            <label className="text-[10px] font-mono text-space-400 block mb-1">Height (px)</label>
            <input
              type="text"
              value={height}
              onChange={(e) => setHeight(e.target.value)}
              className="w-full bg-space-950 border border-space-700 rounded px-2.5 py-1.5 font-mono text-xs text-space-100 focus:outline-none focus:border-cyan-400"
            />
          </div>
        </div>

        {/* Snippet box */}
        <div>
          <label className="text-[10px] font-mono text-space-400 block mb-1">HTML Embed Snippet</label>
          <div className="relative">
            <pre className="p-3 rounded bg-space-950 border border-space-700 font-mono text-[11px] text-cyan-300 overflow-x-auto whitespace-pre-wrap break-all max-h-28">
              {iframeSnippet}
            </pre>
          </div>
        </div>

        <div className="flex items-center justify-end space-x-2 pt-2 border-t border-space-800">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded bg-space-850 border border-space-700 text-space-300 hover:text-space-100 text-xs font-mono transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleCopy}
            className="px-4 py-1.5 rounded bg-cyan-950 border border-cyan-400 text-cyan-300 hover:bg-cyan-900 text-xs font-mono font-semibold flex items-center gap-1.5 shadow-[0_0_8px_rgba(0,242,254,0.3)] transition-all"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copied ? 'Copied to Clipboard!' : 'Copy Snippet'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
