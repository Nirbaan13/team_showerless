import React from 'react';
import { Eye, Microscope } from 'lucide-react';

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

  const options = [
    { id: 'volunteer' as const, label: 'Volunteer', Icon: Eye },
    { id: 'scientist' as const, label: 'Scientist', Icon: Microscope },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm select-none">
      <div className="anim-fall w-full max-w-md bg-paper-900 border-2 border-black rounded-2xl card-tactile p-6 text-paper-100">
        <h2 className="text-2xl font-bold font-sans tracking-tight text-white text-center mb-5">
          Choose your view
        </h2>
        <div className="grid grid-cols-2 gap-4">
          {options.map(({ id, label, Icon }, i) => (
            <button
              key={id}
              onClick={() => handleChoose(id)}
              style={{ animationDelay: `${80 + i * 60}ms` }}
              className={`anim-fall btn-tactile py-6 rounded-xl border-2 border-black flex flex-col items-center gap-3 font-mono font-bold text-sm cursor-pointer transition-colors ${
                currentMode === id
                  ? 'bg-emerald-400 text-gray-950'
                  : 'bg-paper-950 text-paper-100 hover:text-emerald-300'
              }`}
            >
              <Icon className="w-8 h-8" />
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
