import React, { useState } from 'react';
import type { FOVOption, DetectorArrayId, SubtractionMode } from '../types/spherex';
import { Share2, Code, Check, Terminal, BookOpen, ChevronDown } from 'lucide-react';

interface TopNavProps {
  ra: number;
  dec: number;
  fov: FOVOption;
  selectedArray: DetectorArrayId | 'all';
  subtractionMode: SubtractionMode;
  activeFrameIndex: number;
  onOpenEmbedModal: () => void;
  isViewerActive: boolean;
  isScientistMode?: boolean;
}

export const TopNav: React.FC<TopNavProps> = ({
  ra,
  dec,
  fov,
  selectedArray,
  subtractionMode,
  activeFrameIndex,
  onOpenEmbedModal,
  isViewerActive,
  isScientistMode = false,
}) => {
  const [copiedLink, setCopiedLink] = useState(false);
  const [copiedSnippet, setCopiedSnippet] = useState<string | null>(null);
  const [showScientistMenu, setShowScientistMenu] = useState(false);

  const getShareUrl = () => {
    const params = new URLSearchParams({
      ra: ra.toFixed(6),
      dec: dec.toFixed(6),
      fov,
      detector: String(selectedArray),
      subtraction: subtractionMode,
      frame: String(activeFrameIndex),
    });
    return `${window.location.origin}${window.location.pathname}?${params.toString()}`;
  };

  const handleCopyShareLink = () => {
    const url = getShareUrl();
    navigator.clipboard.writeText(url).then(() => {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    });
  };

  const handleCopyAstropy = () => {
    const snippet = `# SPHEREx Observation Coordinate Target\nfrom astropy.coordinates import SkyCoord\nimport astropy.units as u\n\ntarget = SkyCoord(ra=${ra.toFixed(6)} * u.deg, dec=${dec.toFixed(6)} * u.deg, frame='icrs')\nprint(f"SPHEREx RA {target.ra.to_string(unit=u.hour, precision=2)}, Dec {target.dec.to_string(unit=u.deg, precision=2)}")\n`;
    navigator.clipboard.writeText(snippet).then(() => {
      setCopiedSnippet('astropy');
      setTimeout(() => setCopiedSnippet(null), 2000);
    });
  };

  const handleCopyBibtex = () => {
    const bibtex = `@misc{spherex_viewer_${ra.toFixed(2)}_${dec.toFixed(2)},\n  author = {{SPHEREx Sky-Viewer Collaboration}},\n  title = {SPHEREx Celestial Field at RA ${ra.toFixed(4)}^\\circ, Dec ${dec.toFixed(4)}^\\circ},\n  year = {2026},\n  howpublished = {\\url{${getShareUrl()}}},\n  note = {NASA/IPAC Infrared Science Archive SPHEREx Quick Release}\n}`;
    navigator.clipboard.writeText(bibtex).then(() => {
      setCopiedSnippet('bibtex');
      setTimeout(() => setCopiedSnippet(null), 2000);
    });
  };

  if (!isViewerActive) {
    return null;
  }

  return (
    <div className="flex items-center space-x-2 relative">
      {/* Current Coordinates Indicator */}
      <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded bg-paper-950 border border-paper-800 text-[11px] font-mono text-paper-300">
        <span className="text-paper-500">RA:</span>
        <span className="text-ochre-300 font-medium">{ra.toFixed(4)}°</span>
        <span className="text-paper-700">•</span>
        <span className="text-paper-500">Dec:</span>
        <span className="text-ochre-300 font-medium">{dec.toFixed(4)}°</span>
      </div>

      {/* Share View (Direct Link Copy) */}
      <div className="relative inline-flex">
        <button
          onClick={handleCopyShareLink}
          className={`btn-tactile-sm px-2.5 py-1 rounded-lg bg-paper-900 border-2 border-black text-paper-200 hover:text-emerald-300 text-[11px] font-mono flex items-center gap-1.5 cursor-pointer ${
            isScientistMode ? 'rounded-r-none border-r-0' : ''
          }`}
          title="Copy direct shareable coordinate URL to clipboard"
        >
          {copiedLink ? <Check className="w-3.5 h-3.5 text-emerald-400 stroke-[2.5]" /> : <Share2 className="w-3.5 h-3.5 text-emerald-400" />}
          <span>{copiedLink ? 'Link Copied!' : 'Share View'}</span>
        </button>

        {/* Scientist Mode dropdown for Astropy / BibTeX */}
        {isScientistMode && (
          <>
            <button
              onClick={() => setShowScientistMenu((p) => !p)}
              className="btn-tactile-sm px-1.5 py-1 rounded-r-lg bg-paper-900 border-2 border-black text-paper-400 hover:text-emerald-300 text-[11px] font-mono cursor-pointer"
              title="Scientist Citation & Astropy export options"
            >
              <ChevronDown className="w-3 h-3" />
            </button>

            {showScientistMenu && (
              <div
                onMouseLeave={() => setShowScientistMenu(false)}
                className="absolute right-0 top-full mt-1.5 w-52 bg-paper-950 border-2 border-black rounded-xl card-tactile p-1.5 z-50 text-[11px] font-mono space-y-1 anim-fall"
              >
                <div className="px-2 py-1 text-[10px] text-paper-500 uppercase font-semibold border-b border-paper-800">
                  Scientist Export
                </div>
                <button
                  onClick={() => {
                    handleCopyAstropy();
                    setShowScientistMenu(false);
                  }}
                  className="w-full px-2 py-1.5 rounded-lg hover:bg-paper-850 text-left text-paper-200 hover:text-emerald-300 flex items-center gap-2 cursor-pointer transition-colors"
                >
                  {copiedSnippet === 'astropy' ? <Check className="w-3 h-3 text-emerald-400" /> : <Terminal className="w-3 h-3 text-emerald-400" />}
                  <span>{copiedSnippet === 'astropy' ? 'Copied Astropy!' : 'Copy Astropy Snippet'}</span>
                </button>
                <button
                  onClick={() => {
                    handleCopyBibtex();
                    setShowScientistMenu(false);
                  }}
                  className="w-full px-2 py-1.5 rounded-lg hover:bg-paper-850 text-left text-paper-200 hover:text-emerald-300 flex items-center gap-2 cursor-pointer transition-colors"
                >
                  {copiedSnippet === 'bibtex' ? <Check className="w-3 h-3 text-emerald-400" /> : <BookOpen className="w-3 h-3 text-emerald-400" />}
                  <span>{copiedSnippet === 'bibtex' ? 'Copied BibTeX!' : 'Copy BibTeX Citation'}</span>
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Embed Iframe Snippet */}
      <button
        onClick={onOpenEmbedModal}
        className="btn-tactile-sm px-2.5 py-1 rounded-lg bg-paper-900 border-2 border-black text-paper-200 hover:text-emerald-300 text-[11px] font-mono flex items-center gap-1.5 cursor-pointer"
        title="Generate responsive <iframe> embed snippet for blogs or research writeups"
      >
        <Code className="w-3.5 h-3.5 text-ochre-400" />
        <span>Embed</span>
      </button>
    </div>
  );
};
