import { useState } from 'react';

/** Published artifacts only; a missing image is a missing measurement. */
export function ArtifactImage({ src, alt, className = 'w-full h-full object-contain pixelated' }: { src?: string; alt: string; className?: string }) {
  const [failedUrl, setFailedUrl] = useState<string>();
  const allowed = src && !src.includes('/api/motion/coadd/') && !src.includes('/api/motion/cutout/render') && !src.startsWith('data:image/svg');
  if (!allowed || failedUrl === src) return <span role="status" className="text-xs text-paper-400 text-center p-2">{alt} unavailable</span>;
  return <img src={src} alt={alt} className={className} onError={() => setFailedUrl(src)} />;
}
