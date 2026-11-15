import { useEffect, useId, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { filterSkyObjects, type SkyObject } from '../services/skyObjects';

/** The surrounding button row supplies the dropdown's positioning boundary. */
export function ObjectSearch({ onSelect }: { onSelect: (object: SkyObject) => void }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const objects = filterSkyObjects(query);

  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    const dismiss = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener('pointerdown', dismiss);
    return () => document.removeEventListener('pointerdown', dismiss);
  }, [open]);

  useEffect(() => {
    if (open) root.current?.querySelector<HTMLElement>('[role="option"][aria-selected="true"]')?.scrollIntoView({ block: 'nearest' });
  }, [open, activeIndex, query]);

  const close = () => {
    setOpen(false);
    trigger.current?.focus();
  };
  const select = (object: SkyObject) => {
    close();
    onSelect(object);
  };

  return <div ref={root} className="shrink-0" onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }} onKeyDown={event => {
    if (event.key === 'Escape' && open) { event.preventDefault(); event.stopPropagation(); close(); }
  }}>
    <button ref={trigger} type="button" aria-label="Find object" title="Find object"
      aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? listId : undefined}
      onClick={() => { setQuery(''); setActiveIndex(0); setOpen(value => !value); }}
      onKeyDown={event => {
        if (event.key === 'ArrowDown') { event.preventDefault(); setQuery(''); setActiveIndex(0); setOpen(true); }
      }}
      className={`btn-tactile h-9 w-9 flex items-center justify-center rounded-lg border-2 cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400 ${open ? 'bg-paper-700 border-emerald-400 text-emerald-300' : 'bg-paper-800 border-paper-700 text-paper-200 hover:bg-paper-700 hover:text-white'}`}>
      <Search aria-hidden="true" className="h-4 w-4" />
    </button>
    {open && <div className="absolute top-full left-0 right-0 mt-1.5 rounded-lg border border-paper-600 bg-paper-900 p-2 shadow-xl z-50">
      <label htmlFor={`${listId}-input`} className="block mb-1 text-[10px] font-mono text-paper-300">Object name</label>
      <input ref={input} id={`${listId}-input`} type="search" role="combobox" aria-label="Object name"
        aria-autocomplete="list" aria-expanded="true" aria-controls={listId}
        aria-activedescendant={objects[activeIndex] ? `${listId}-${objects[activeIndex].id}` : undefined}
        value={query} placeholder="Search objects…" autoComplete="off"
        onChange={event => { setQuery(event.target.value); setActiveIndex(0); }}
        onKeyDown={event => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            if (objects.length) setActiveIndex(index => (index + (event.key === 'ArrowDown' ? 1 : -1) + objects.length) % objects.length);
          }
          if (event.key === 'Enter') { event.preventDefault(); if (objects[activeIndex]) select(objects[activeIndex]); }
        }}
        className="w-full rounded border border-paper-600 bg-paper-950 px-2 py-1.5 font-mono text-[11px] text-paper-100 focus:outline-none focus:border-emerald-400" />
      <ul id={listId} role="listbox" aria-label="Objects" className="mt-1 max-h-56 overflow-y-auto overscroll-contain">
        {objects.map((object, index) => <li key={object.id} role="presentation">
          <button id={`${listId}-${object.id}`} type="button" role="option" aria-label={object.name}
            aria-selected={activeIndex === index} tabIndex={-1}
            onMouseEnter={() => setActiveIndex(index)} onMouseDown={event => event.preventDefault()}
            onClick={() => select(object)}
            className={`w-full rounded px-2 py-1.5 text-left ${activeIndex === index ? 'bg-paper-700 text-emerald-300' : 'text-paper-200 hover:bg-paper-800'}`}>
            <span className="block text-[11px] font-mono break-words">{object.name}</span>
            <span className="block text-[10px] text-paper-400">{object.kind}</span>
          </button>
        </li>)}
      </ul>
      {!objects.length && <p role="status" className="px-2 py-3 text-paper-400">No matching objects</p>}
      <p className="mt-1 border-t border-paper-800 pt-1 text-[10px] text-paper-400">Reference fields at epoch 2025.9. Search uses the current field size and detector.</p>
    </div>}
  </div>;
}
