import { useEffect, useRef, useState } from 'react';
import { listArchives, searchArchive, downloadObservations, getArchiveDownload, waitForArchivePoll,
  type ArchiveInventory, type ArchiveQuery, type ArchiveSearchResult, type ArchiveDownload } from '../services/archiveObservationsApi';

export function useArchiveObservations() {
  const [inventory, setInventory] = useState<ArchiveInventory[]>([]);
  const [inventoryError, setInventoryError] = useState('');
  const [query, setQuery] = useState<ArchiveQuery | null>(null);
  const [result, setResult] = useState<ArchiveSearchResult | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [job, setJob] = useState<ArchiveDownload | null>(null);
  const [searching, setSearching] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState('');
  const downloadRequest = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    listArchives(controller.signal).then(setInventory).catch(e => { if (!controller.signal.aborted) setInventoryError(String(e.message ?? e)); });
    return () => { controller.abort(); downloadRequest.current?.abort(); };
  }, []);
  const reset = () => {
    downloadRequest.current?.abort();
    setQuery(null); setResult(null); setSelectedIds([]); setJob(null); setError(''); setSearching(false); setDownloading(false);
  };
  const search = async (value: ArchiveQuery, signal: AbortSignal) => {
    reset(); setQuery(value); setSearching(true);
    try {
      const found = await searchArchive(value, signal);
      signal.throwIfAborted();
      setResult(found);
      return found;
    } catch (e) {
      if (!signal.aborted) setError(e instanceof Error ? e.message : 'Archive search failed');
      throw e;
    } finally { if (!signal.aborted) setSearching(false); }
  };
  const download = async () => {
    downloadRequest.current?.abort();
    const controller = new AbortController(); downloadRequest.current = controller;
    const ids = [...selectedIds];
    setDownloading(true); setError(''); setJob(null);
    try {
      let current = await downloadObservations(ids, controller.signal);
      setJob(current);
      while (!['completed', 'completed_with_errors', 'failed'].includes(current.status)) {
        await waitForArchivePoll(controller.signal);
        current = await getArchiveDownload(current.status_url, controller.signal);
        controller.signal.throwIfAborted(); setJob(current);
      }
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Archive download failed');
    } finally { if (!controller.signal.aborted) setDownloading(false); }
  };
  const toggle = (id: string) => setSelectedIds(ids => ids.includes(id) ? ids.filter(value => value !== id) : [...ids, id]);
  return { inventory, inventoryError, query, result, selectedIds, job, searching, downloading, error, search, reset, download, toggle };
}
