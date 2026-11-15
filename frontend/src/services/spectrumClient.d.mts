import type { TargetSpectrumResult } from './spherexBackendApi';
export function fetchSpectrum(base: string, parameters: URLSearchParams, signal?: AbortSignal): Promise<TargetSpectrumResult>;
