export interface CatalogSourceItem {
  id: string;
  label: string;
  ra: number;
  dec: number;
  mag?: number | null;
  w2Mag?: number | null;
  pmRa?: number | null;
  pmDec?: number | null;
  objectType?: string;
  separationArcsec: number;
  dx: number;
  dy: number;
  agency: string;
  referenceUrl: string;
  catalogType: 'Gaia DR3' | 'WISE' | 'NEO Ephemeris' | 'SIMBAD';
}

export interface AgencyReferenceLink {
  agency: string;
  title: string;
  url: string;
}

export interface LiveCatalogResponse {
  status: 'loading' | 'live_agency' | 'partial' | 'unavailable';
  queriedCoordinate: {
    ra: number;
    dec: number;
    fovArcmin: number;
  };
  candidateId?: string | null;
  queriedAt: string;
  latencyMs: number;
  agenciesQueried: string[];
  providers: { catalog: string; status: 'ok' | 'failed' }[];
  references: AgencyReferenceLink[];
  gaiaSources: CatalogSourceItem[];
  wiseSources: CatalogSourceItem[];
  simbadSources: CatalogSourceItem[];
  ephemerisSources: CatalogSourceItem[];
  totalObjects: number;
}


export function formatJ2000Designation(raDeg: number, decDeg: number): string {
  const normRa = ((raDeg % 360) + 360) % 360;
  const raHoursTotal = normRa / 15;
  const rh = Math.floor(raHoursTotal);
  const rm = Math.floor((raHoursTotal - rh) * 60);
  const rs = ((raHoursTotal - rh - rm / 60) * 3600).toFixed(2).padStart(5, '0');
  const sign = decDeg >= 0 ? '+' : '-';
  const absDec = Math.abs(decDeg);
  const dd = Math.floor(absDec);
  const dm = Math.floor((absDec - dd) * 60);
  const ds = ((absDec - dd - dm / 60) * 3600).toFixed(1).padStart(4, '0');
  return `J${String(rh).padStart(2, '0')}${String(rm).padStart(2, '0')}${rs}${sign}${String(dd).padStart(2, '0')}${String(dm).padStart(2, '0')}${ds}`;
}

export function raDecToCanvasDxDy(
  srcRa: number,
  srcDec: number,
  centerRa: number,
  centerDec: number,
  fovArcmin: number
): { dx: number; dy: number } {
  const cosDec = Math.max(0.15, Math.cos((centerDec * Math.PI) / 180));
  const draArcmin = (srcRa - centerRa) * cosDec * 60;
  const ddecArcmin = (srcDec - centerDec) * 60;
  const scalePxPerArcmin = 420 / Math.max(1, fovArcmin);
  const dx = Math.max(-225, Math.min(225, Math.round(draArcmin * scalePxPerArcmin * 10) / 10));
  const dy = Math.max(-225, Math.min(225, Math.round(-ddecArcmin * scalePxPerArcmin * 10) / 10));
  return { dx, dy };
}

export function angularSeparationArcsec(
  ra1: number,
  dec1: number,
  ra2: number,
  dec2: number
): number {
  const cosDec = Math.max(0.15, Math.cos(((dec1 + dec2) * 0.5 * Math.PI) / 180));
  return Math.round(Math.hypot((ra1 - ra2) * cosDec, dec1 - dec2) * 3600 * 10) / 10;
}

export function buildAgencyReferences(
  ra: number,
  dec: number,
  fovArcmin: number
): AgencyReferenceLink[] {
  const signDec = dec >= 0 ? `+${dec.toFixed(5)}` : dec.toFixed(5);
  const coordQuery = `${ra.toFixed(5)} ${signDec}`;
  const encodedCoord = encodeURIComponent(coordQuery);
  const fovRadiusArcmin = Math.max(0.5, Math.min(30, fovArcmin)).toFixed(1);
  const fovRadiusArcsec = Math.round(Number(fovRadiusArcmin) * 60).toString();
  const fovDeg = (Math.max(0.5, Math.min(60, fovArcmin)) / 60).toFixed(3);

  return [
    {
      agency: 'NASA/IPAC IRSA',
      title: 'NASA/IPAC IRSA Interactive Viewer (SPHEREx & AllWISE)',
      url: `https://irsa.ipac.caltech.edu/irsaviewer/?__action=init&locstr=${encodedCoord}`,
    },
    {
      agency: 'ESA Gaia / VizieR',
      title: 'ESA Gaia DR3 Cone Search (VizieR CfA Mirror)',
      url: `https://vizier.cfa.harvard.edu/viz-bin/VizieR-3?-source=I/355/gaiadr3&-c=${encodedCoord}&-c.rs=${fovRadiusArcsec}`,
    },
    {
      agency: 'CDS SIMBAD',
      title: 'CDS SIMBAD Astronomical Object Database (CfA Mirror)',
      url: `https://simbad.cfa.harvard.edu/simbad/sim-coo?Coord=${encodedCoord}&Radius=${fovRadiusArcmin}&Radius.unit=arcmin`,
    },
    {
      agency: 'CDS Aladin Lite',
      title: 'CDS Aladin Sky Atlas (AllWISE / PanSTARRS Multi-epoch)',
      url: `https://aladin.cds.unistra.fr/AladinLite/?target=${encodedCoord}&fov=${fovDeg}&survey=P%2FallWISE%2Fcolor`,
    },
    {
      agency: 'NASA/JPL Horizons',
      title: 'NASA/JPL Solar System Dynamics Small-Body Ephemeris',
      url: 'https://ssd.jpl.nasa.gov/horizons/app.html',
    },
  ];
}

async function queryBrowserGaiaTap(
  queryRa: number,
  queryDec: number,
  centerRa: number,
  centerDec: number,
  fovArcmin: number,
  radiusDeg: number
): Promise<CatalogSourceItem[]> {
  const adql = `SELECT TOP 6 "I/355/gaiadr3".Source, "I/355/gaiadr3".RA_ICRS, "I/355/gaiadr3".DE_ICRS, "I/355/gaiadr3".Gmag, "I/355/gaiadr3".pmRA, "I/355/gaiadr3".pmDE FROM "I/355/gaiadr3" WHERE CONTAINS(POINT('ICRS', "I/355/gaiadr3".RA_ICRS, "I/355/gaiadr3".DE_ICRS), CIRCLE('ICRS', ${queryRa.toFixed(6)}, ${queryDec.toFixed(6)}, ${radiusDeg.toFixed(5)})) = 1 ORDER BY "I/355/gaiadr3".Gmag ASC`;
  const url = `https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync?request=doQuery&lang=adql&format=json&query=${encodeURIComponent(adql)}`;
  const res = await fetch(url, { signal: AbortSignal.timeout(3500) });
  if (!res.ok) throw new Error(`Catalogue HTTP ${res.status}`);
  const payload = await res.json();
  if (!Array.isArray(payload?.data)) throw new Error('Invalid catalogue response');
  const rows: unknown[][] = payload.data;
  return rows
    .filter((r) => Array.isArray(r) && r[0] != null && (typeof r[0] !== 'number' || Number.isSafeInteger(r[0])) && r[1] != null && r[2] != null && Number.isFinite(Number(r[1])) && Number.isFinite(Number(r[2])))
    .map((r) => {
      const srcId = String(r[0]).trim();
      const sRa = Number(r[1]);
      const sDec = Number(r[2]);
      const gMag = r[3] != null ? Number(Number(r[3]).toFixed(2)) : null;
      const pmRa = r[4] != null ? Number(Number(r[4]).toFixed(1)) : null;
      const pmDec = r[5] != null ? Number(Number(r[5]).toFixed(1)) : null;
      const sep = angularSeparationArcsec(sRa, sDec, queryRa, queryDec);
      const { dx, dy } = raDecToCanvasDxDy(sRa, sDec, centerRa, centerDec, fovArcmin);
      return {
        id: `Gaia DR3 ${srcId}`,
        label: `Gaia DR3 ${srcId} (G=${gMag?.toFixed(1) ?? 'unavailable'} · Δ=${sep}″)`,
        ra: Number(sRa.toFixed(6)),
        dec: Number(sDec.toFixed(6)),
        mag: gMag,
        pmRa,
        pmDec,
        separationArcsec: sep,
        dx,
        dy,
        agency: 'ESA Gaia DR3 (VizieR CfA)',
        referenceUrl: `https://vizier.cfa.harvard.edu/viz-bin/VizieR-5?-ref=VIZ&-out.add=.&-source=I/355/gaiadr3&Source=${encodeURIComponent(srcId)}`,
        catalogType: 'Gaia DR3' as const,
      };
    });
}

async function queryBrowserWiseTap(
  queryRa: number,
  queryDec: number,
  centerRa: number,
  centerDec: number,
  fovArcmin: number,
  radiusDeg: number
): Promise<CatalogSourceItem[]> {
  const adql = `SELECT TOP 5 "II/328/allwise".AllWISE, "II/328/allwise".RAJ2000, "II/328/allwise".DEJ2000, "II/328/allwise".W1mag, "II/328/allwise".W2mag FROM "II/328/allwise" WHERE CONTAINS(POINT('ICRS', "II/328/allwise".RAJ2000, "II/328/allwise".DEJ2000), CIRCLE('ICRS', ${queryRa.toFixed(6)}, ${queryDec.toFixed(6)}, ${radiusDeg.toFixed(5)})) = 1 ORDER BY "II/328/allwise".W1mag ASC`;
  const url = `https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync?request=doQuery&lang=adql&format=json&query=${encodeURIComponent(adql)}`;
  const res = await fetch(url, { signal: AbortSignal.timeout(3500) });
  if (!res.ok) throw new Error(`Catalogue HTTP ${res.status}`);
  const payload = await res.json();
  if (!Array.isArray(payload?.data)) throw new Error('Invalid catalogue response');
  const rows: unknown[][] = payload.data;
  return rows
    .filter((r) => Array.isArray(r) && r[0] != null && (typeof r[0] !== 'number' || Number.isSafeInteger(r[0])) && r[1] != null && r[2] != null && Number.isFinite(Number(r[1])) && Number.isFinite(Number(r[2])))
    .map((r) => {
      const wiseName = String(r[0]).trim();
      const wRa = Number(r[1]);
      const wDec = Number(r[2]);
      const signWDec = wDec >= 0 ? `+${wDec.toFixed(5)}` : wDec.toFixed(5);
      const w1 = r[3] != null ? Number(Number(r[3]).toFixed(2)) : null;
      const w2 = r[4] != null ? Number(Number(r[4]).toFixed(2)) : null;
      const sep = angularSeparationArcsec(wRa, wDec, queryRa, queryDec);
      const { dx, dy } = raDecToCanvasDxDy(wRa, wDec, centerRa, centerDec, fovArcmin);
      return {
        id: `AllWISE ${wiseName}`,
        label: `AllWISE ${wiseName} (W1=${w1?.toFixed(1) ?? 'unavailable'}, W2=${w2?.toFixed(1) ?? 'unavailable'} · Δ=${sep}″)`,
        ra: Number(wRa.toFixed(6)),
        dec: Number(wDec.toFixed(6)),
        mag: w1,
        w2Mag: w2,
        separationArcsec: sep,
        dx,
        dy,
        agency: 'NASA/IPAC AllWISE (IRSA)',
        referenceUrl: `https://irsa.ipac.caltech.edu/irsaviewer/?__action=init&locstr=${encodeURIComponent(`${wRa.toFixed(5)} ${signWDec}`)}`,
        catalogType: 'WISE' as const,
      };
    });
}

async function queryBrowserSimbadTap(
  queryRa: number,
  queryDec: number,
  centerRa: number,
  centerDec: number,
  fovArcmin: number,
  radiusDeg: number
): Promise<CatalogSourceItem[]> {
  const adql = `SELECT TOP 5 main_id, otype_txt, ra, dec FROM basic WHERE CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', ${queryRa.toFixed(6)}, ${queryDec.toFixed(6)}, ${radiusDeg.toFixed(5)})) = 1`;
  const url = `https://simbad.cfa.harvard.edu/simbad/sim-tap/sync?request=doQuery&lang=adql&format=json&query=${encodeURIComponent(adql)}`;
  const res = await fetch(url, { signal: AbortSignal.timeout(3200) });
  if (!res.ok) throw new Error(`Catalogue HTTP ${res.status}`);
  const payload = await res.json();
  if (!Array.isArray(payload?.data)) throw new Error('Invalid catalogue response');
  const rows: unknown[][] = payload.data;
  return rows
    .filter((r) => Array.isArray(r) && r[0] != null && r[2] != null && r[3] != null)
    .map((r) => {
      const mainId = String(r[0]).replace(/\s+/g, ' ').trim();
      const otype = String(r[1] || 'Star').trim();
      const sRa = Number(r[2]);
      const sDec = Number(r[3]);
      const sep = angularSeparationArcsec(sRa, sDec, queryRa, queryDec);
      const { dx, dy } = raDecToCanvasDxDy(sRa, sDec, centerRa, centerDec, fovArcmin);
      return {
        id: mainId,
        label: `${mainId} (${otype} · Δ=${sep}″)`,
        objectType: otype,
        ra: Number(sRa.toFixed(6)),
        dec: Number(sDec.toFixed(6)),
        separationArcsec: sep,
        dx,
        dy,
        agency: 'CDS SIMBAD (CfA)',
        referenceUrl: `https://simbad.cfa.harvard.edu/simbad/sim-id?Ident=${encodeURIComponent(mainId)}`,
        catalogType: 'SIMBAD' as const,
      };
    });
}

export async function fetchLiveCatalogForCoordinate(params: {
  queryRa: number;
  queryDec: number;
  centerRa: number;
  centerDec: number;
  fovArcmin: number;
  candidateId?: string | null;
}): Promise<LiveCatalogResponse> {
  const { queryRa, queryDec, centerRa, centerDec, fovArcmin, candidateId } = params;
  const started = performance.now();
  const radiusDeg = Math.max(0.025, Math.min(0.25, (fovArcmin / 60) * 0.65));
  const outcomes = await Promise.allSettled([
    fetch(`/api/motion/catalog?ra=${queryRa}&dec=${queryDec}&fov_arcmin=${fovArcmin}`, { signal: AbortSignal.timeout(10000) }).then(async response => {
      if (!response.ok) throw new Error(`Catalogue HTTP ${response.status}`);
      return response.json();
    }),
    queryBrowserGaiaTap(queryRa, queryDec, centerRa, centerDec, fovArcmin, radiusDeg),
    queryBrowserWiseTap(queryRa, queryDec, centerRa, centerDec, fovArcmin, radiusDeg),
    queryBrowserSimbadTap(queryRa, queryDec, centerRa, centerDec, fovArcmin, radiusDeg),
  ]);
  const backend = outcomes[0].status === 'fulfilled' ? outcomes[0].value : null;
  const providers: LiveCatalogResponse['providers'] = [];
  const mapBackend = (items: any[], catalogType: CatalogSourceItem['catalogType']): CatalogSourceItem[] => items
    .filter(item => typeof item.id === 'string' && typeof item.ra === 'number' && typeof item.dec === 'number' && Number.isFinite(item.ra) && Number.isFinite(item.dec))
    .map(item => ({ ...item, label: item.label ?? item.id, ...raDecToCanvasDxDy(item.ra, item.dec, centerRa, centerDec, fovArcmin), separationArcsec: angularSeparationArcsec(item.ra, item.dec, queryRa, queryDec), catalogType }));
  const source = (index: number, key: string, catalog: CatalogSourceItem['catalogType']): CatalogSourceItem[] => {
    const browser = outcomes[index];
    if (browser.status === 'fulfilled') {
      providers.push({ catalog, status: 'ok' });
      return browser.value;
    }
    const items = backend?.[key];
    const available = backend?.providers?.find((item: any) => item.catalog === catalog)?.status === 'ok';
    if (Array.isArray(items) && (available || items.length > 0)) {
      providers.push({ catalog, status: 'ok' });
      return mapBackend(items, catalog);
    }
    providers.push({ catalog, status: 'failed' });
    return [];
  };
  const gaiaSources = source(1, 'gaiaSources', 'Gaia DR3');
  const wiseSources = source(2, 'wiseSources', 'WISE');
  const simbadSources = source(3, 'simbadSources', 'SIMBAD');
  const ephemerisSources = mapBackend(Array.isArray(backend?.ephemerisSources) ? backend.ephemerisSources : [], 'NEO Ephemeris');
  const successful = providers.filter(provider => provider.status === 'ok').length;
  return {
    status: successful === 0 ? 'unavailable' : successful === providers.length ? 'live_agency' : 'partial',
    queriedCoordinate: { ra: queryRa, dec: queryDec, fovArcmin }, candidateId,
    queriedAt: new Date().toISOString(), latencyMs: Math.round(performance.now() - started),
    agenciesQueried: providers.filter(provider => provider.status === 'ok').map(provider => provider.catalog), providers,
    references: buildAgencyReferences(queryRa, queryDec, fovArcmin),
    gaiaSources, wiseSources, simbadSources, ephemerisSources,
    totalObjects: gaiaSources.length + wiseSources.length + simbadSources.length + ephemerisSources.length,
  };
}
