import React, { useState } from 'react';
import { Copy, Check, X, Code2 } from 'lucide-react';
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
  const iframeSnippet = `<iframe src="${embedUrl}" width="${width}" height="${height}" frameborder="0" allowfullscreen style="border: 2px solid #000; border-radius: 12px;"></iframe>`;

  const handleCopy = () => {
    navigator.clipboard.writeText(iframeSnippet).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2200);
    });
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 select-none">
      <div className="bg-paper-900 border-2 border-black rounded-2xl max-w-lg w-full p-6 space-y-4 card-tactile text-paper-100 anim-fall">
        <div className="flex items-center justify-between border-b border-paper-800 pb-3">
          <div className="font-sans font-bold text-white text-base tracking-tight flex items-center gap-2">
            <Code2 className="w-5 h-5 text-emerald-400" />
            <span>Embed SPHEREx Sky-Viewer</span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-paper-400 hover:text-white hover:bg-paper-800 transition-colors cursor-pointer"
            title="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="text-xs text-paper-300 font-sans leading-relaxed">
          Embed this live, interactive celestial blink viewport directly into external science blogs, research write-ups, or project showcase pages.
        </p>

        {/* Dimension inputs */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] font-mono text-paper-400 block mb-1 uppercase font-semibold">Width (px)</label>
            <input
              type="text"
              value={width}
              onChange={(e) => setWidth(e.target.value)}
              className="w-full bg-paper-950 border-2 border-black rounded-lg px-2.5 py-1.5 font-mono text-xs text-paper-100 focus:outline-none focus:border-emerald-400"
            />
          </div>
          <div>
            <label className="text-[10px] font-mono text-paper-400 block mb-1 uppercase font-semibold">Height (px)</label>
            <input
              type="text"
              value={height}
              onChange={(e) => setHeight(e.target.value)}
              className="w-full bg-paper-950 border-2 border-black rounded-lg px-2.5 py-1.5 font-mono text-xs text-paper-100 focus:outline-none focus:border-emerald-400"
            />
          </div>
        </div>

        {/* Snippet box */}
        <div>
          <label className="text-[10px] font-mono text-paper-400 block mb-1 uppercase font-semibold">HTML Embed Snippet</label>
          <pre className="p-3 rounded-lg bg-paper-950 border-2 border-black font-mono text-[11px] text-emerald-300 overflow-x-auto whitespace-pre-wrap break-all max-h-28">
            {iframeSnippet}
          </pre>
        </div>

        <div className="flex items-center justify-end space-x-2 pt-3 border-t border-paper-800">
          <button
            onClick={onClose}
            className="btn-tactile-sm px-3.5 py-2 rounded-xl bg-paper-950 border-2 border-black text-paper-300 hover:text-white text-xs font-mono cursor-pointer"
          >
            Close
          </button>
          <button
            onClick={handleCopy}
            className="btn-tactile px-4 py-2 rounded-xl bg-emerald-400 hover:bg-emerald-300 text-gray-950 border-2 border-black text-xs font-mono font-bold flex items-center gap-1.5 cursor-pointer"
          >
            {copied ? <Check className="w-3.5 h-3.5 stroke-[2.5]" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copied ? 'Copied to Clipboard!' : 'Copy Snippet'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
