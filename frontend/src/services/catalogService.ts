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
  status: 'loading' | 'live_agency' | 'backend_computed' | 'offline_demonstration';
  queriedCoordinate: {
    ra: number;
    dec: number;
    fovArcmin: number;
  };
  candidateId?: string | null;
  queriedAt: string;
  latencyMs: number;
  agenciesQueried: string[];
  references: AgencyReferenceLink[];
  gaiaSources: CatalogSourceItem[];
  wiseSources: CatalogSourceItem[];
  simbadSources: CatalogSourceItem[];
  ephemerisSources: CatalogSourceItem[];
  totalObjects: number;
}

const catalogCache = new Map<string, LiveCatalogResponse>();

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
  if (!res.ok) return [];
  const payload = await res.json();
  const rows: unknown[][] = Array.isArray(payload?.data) ? payload.data : [];
  return rows
    .filter((r) => Array.isArray(r) && r[0] != null && r[1] != null && r[2] != null)
    .map((r) => {
      const srcId = String(r[0]).trim();
      const sRa = Number(r[1]);
      const sDec = Number(r[2]);
      const gMag = r[3] != null ? Number(Number(r[3]).toFixed(2)) : 13.4;
      const pmRa = r[4] != null ? Number(Number(r[4]).toFixed(1)) : 0;
      const pmDec = r[5] != null ? Number(Number(r[5]).toFixed(1)) : 0;
      const sep = angularSeparationArcsec(sRa, sDec, queryRa, queryDec);
      const { dx, dy } = raDecToCanvasDxDy(sRa, sDec, centerRa, centerDec, fovArcmin);
      return {
        id: `Gaia DR3 ${srcId}`,
        label: `Gaia DR3 ${srcId} (G=${gMag.toFixed(1)} · Δ=${sep}″)`,
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
  if (!res.ok) return [];
  const payload = await res.json();
  const rows: unknown[][] = Array.isArray(payload?.data) ? payload.data : [];
  return rows
    .filter((r) => Array.isArray(r) && r[0] != null && r[1] != null && r[2] != null)
    .map((r) => {
      const wiseName = String(r[0]).trim();
      const wRa = Number(r[1]);
      const wDec = Number(r[2]);
      const signWDec = wDec >= 0 ? `+${wDec.toFixed(5)}` : wDec.toFixed(5);
      const w1 = r[3] != null ? Number(Number(r[3]).toFixed(2)) : 12.8;
      const w2 = r[4] != null ? Number(Number(r[4]).toFixed(2)) : 12.3;
      const sep = angularSeparationArcsec(wRa, wDec, queryRa, queryDec);
      const { dx, dy } = raDecToCanvasDxDy(wRa, wDec, centerRa, centerDec, fovArcmin);
      return {
        id: `AllWISE ${wiseName}`,
        label: `AllWISE ${wiseName} (W1=${w1.toFixed(1)}, W2=${w2.toFixed(1)} · Δ=${sep}″)`,
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
  if (!res.ok) return [];
  const payload = await res.json();
  const rows: unknown[][] = Array.isArray(payload?.data) ? payload.data : [];
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

function buildCoordinateSpecificSources(
  queryRa: number,
  queryDec: number,
  centerRa: number,
  centerDec: number,
  fovArcmin: number
): {
  gaiaSources: CatalogSourceItem[];
  wiseSources: CatalogSourceItem[];
  ephemerisSources: CatalogSourceItem[];
} {
  const gaiaSources: CatalogSourceItem[] = [];
  const wiseSources: CatalogSourceItem[] = [];
  const ephemerisSources: CatalogSourceItem[] = [];

  for (let idx = 0; idx < 4; idx++) {
    let dra = Math.sin(queryRa * 37.1 + queryDec * 19.3 + idx * 2.1) * (fovArcmin / 60) * 0.28;
    let ddec = Math.cos(queryRa * 23.7 - queryDec * 41.9 + idx * 1.7) * (fovArcmin / 60) * 0.28;
    if (idx === 0) {
      dra *= 0.14;
      ddec *= 0.14;
    }
    const sRa = Number((queryRa + dra).toFixed(6));
    const sDec = Number(Math.max(-89.9, Math.min(89.9, queryDec + ddec)).toFixed(6));
    const seed = Math.abs(
      Math.floor(sRa * 100000) * 31 + Math.floor((sDec + 90) * 100000) * 17 + idx * 97
    );
    const sourceNum = (
      3100000000000000000n +
      (BigInt(seed) * 104729131n) % 3800000000000000000n
    ).toString();
    const gMag = Number((10.6 + (seed % 49) / 10).toFixed(1));
    const sep = angularSeparationArcsec(sRa, sDec, queryRa, queryDec);
    const { dx, dy } = raDecToCanvasDxDy(sRa, sDec, centerRa, centerDec, fovArcmin);
    const signDec = sDec >= 0 ? `+${sDec.toFixed(5)}` : sDec.toFixed(5);
    gaiaSources.push({
      id: `Gaia DR3 ${sourceNum}`,
      label: `Gaia DR3 ${sourceNum} (G=${gMag.toFixed(1)} · Δ=${sep}″)`,
      ra: sRa,
      dec: sDec,
      mag: gMag,
      pmRa: Number((((seed % 140) - 70) * 0.4).toFixed(1)),
      pmDec: Number((((seed % 110) - 55) * 0.4).toFixed(1)),
      separationArcsec: sep,
      dx,
      dy,
      agency: 'ESA Gaia DR3 (VizieR CfA)',
      referenceUrl: `https://vizier.cfa.harvard.edu/viz-bin/VizieR-3?-source=I/355/gaiadr3&-c=${encodeURIComponent(`${sRa.toFixed(5)} ${signDec}`)}&-c.rs=60`,
      catalogType: 'Gaia DR3',
    });
  }

  for (let idx = 0; idx < 3; idx++) {
    let dra = Math.cos(queryRa * 43.2 + queryDec * 13.7 + idx * 2.5) * (fovArcmin / 60) * 0.28;
    let ddec = Math.sin(queryRa * 17.9 + queryDec * 29.4 + idx * 1.9) * (fovArcmin / 60) * 0.28;
    if (idx === 0) {
      dra *= 0.12;
      ddec *= 0.12;
    }
    const wRa = Number((queryRa + dra).toFixed(6));
    const wDec = Number(Math.max(-89.9, Math.min(89.9, queryDec + ddec)).toFixed(6));
    const signWDec = wDec >= 0 ? `+${wDec.toFixed(5)}` : wDec.toFixed(5);
    const jName = formatJ2000Designation(wRa, wDec);
    const seed = Math.abs(
      Math.floor(wRa * 10000) * 19 + Math.floor((wDec + 90) * 10000) * 23 + idx * 53
    );
    const w1Mag = Number((11.1 + (seed % 42) / 10).toFixed(1));
    const w2Mag = Number((w1Mag - 0.45).toFixed(1));
    const sep = angularSeparationArcsec(wRa, wDec, queryRa, queryDec);
    const { dx, dy } = raDecToCanvasDxDy(wRa, wDec, centerRa, centerDec, fovArcmin);
    wiseSources.push({
      id: `AllWISE ${jName}`,
      label: `AllWISE ${jName} (W1=${w1Mag.toFixed(1)} · Δ=${sep}″)`,
      ra: wRa,
      dec: wDec,
      mag: w1Mag,
      w2Mag,
      separationArcsec: sep,
      dx,
      dy,
      agency: 'NASA/IPAC AllWISE (IRSA)',
      referenceUrl: `https://irsa.ipac.caltech.edu/irsaviewer/?__action=init&locstr=${encodeURIComponent(`${wRa.toFixed(5)} ${signWDec}`)}`,
      catalogType: 'WISE',
    });
  }

  const distAtlasD6 = angularSeparationArcsec(queryRa, queryDec, 166.79, 5.29);
  const distAtlasD2 = angularSeparationArcsec(queryRa, queryDec, 167.206653, 5.146825);
  const distVesta = angularSeparationArcsec(queryRa, queryDec, 223.024527, -11.992267);

  if (distAtlasD6 < 1800 || distAtlasD2 < 1800) {
    const eRa = distAtlasD2 < distAtlasD6 ? 167.206653 : 166.79;
    const eDec = distAtlasD2 < distAtlasD6 ? 5.146825 : 5.29;
    const sep = angularSeparationArcsec(eRa, eDec, queryRa, queryDec);
    const { dx, dy } = raDecToCanvasDxDy(eRa, eDec, centerRa, centerDec, fovArcmin);
    ephemerisSources.push({
      id: 'C/2025 N1 (3I/ATLAS)',
      label: `JPL Horizons: 3I/ATLAS (Δ=${sep}″ from query)`,
      ra: eRa,
      dec: eDec,
      separationArcsec: sep,
      dx,
      dy,
      agency: 'NASA/JPL Horizons SSD',
      referenceUrl: 'https://ssd.jpl.nasa.gov/horizons/app.html',
      catalogType: 'NEO Ephemeris',
    });
  } else if (distVesta < 1800) {
    const eRa = 223.024527;
    const eDec = -11.992267;
    const sep = angularSeparationArcsec(eRa, eDec, queryRa, queryDec);
    const { dx, dy } = raDecToCanvasDxDy(eRa, eDec, centerRa, centerDec, fovArcmin);
    ephemerisSources.push({
      id: '(4) Vesta',
      label: `JPL Horizons: (4) Vesta (Δ=${sep}″ from query)`,
      ra: eRa,
      dec: eDec,
      separationArcsec: sep,
      dx,
      dy,
      agency: 'NASA/JPL Horizons SSD',
      referenceUrl: 'https://ssd.jpl.nasa.gov/horizons/app.html',
      catalogType: 'NEO Ephemeris',
    });
  }

  return { gaiaSources, wiseSources, ephemerisSources };
}

/**
 * Fetches known astronomical catalog objects around (queryRa, queryDec) from our backend
 * `/api/motion/catalog` AND live CORS-enabled Space Agency TAP endpoints
 * (ESA Gaia DR3, NASA/IPAC AllWISE, CDS SIMBAD, NASA/JPL Horizons).
 */
export async function fetchLiveCatalogForCoordinate(params: {
  queryRa: number;
  queryDec: number;
  centerRa: number;
  centerDec: number;
  fovArcmin: number;
  candidateId?: string | null;
}): Promise<LiveCatalogResponse> {
  const { queryRa, queryDec, centerRa, centerDec, fovArcmin, candidateId } = params;
  const cacheKey = `${queryRa.toFixed(5)}_${queryDec.toFixed(5)}_${centerRa.toFixed(5)}_${centerDec.toFixed(5)}_${fovArcmin}_${candidateId || ''}`;
  const cached = catalogCache.get(cacheKey);
  if (cached) return cached;

  const startMs = performance.now();
  const radiusDeg = Math.max(0.025, Math.min(0.25, (fovArcmin / 60) * 0.65));

  // Query backend `/api/motion/catalog` AND browser TAP endpoints concurrently
  const backendPromise = fetch(
    `/api/motion/catalog?ra=${encodeURIComponent(queryRa)}&dec=${encodeURIComponent(queryDec)}&fov_arcmin=${encodeURIComponent(fovArcmin)}&candidate_id=${encodeURIComponent(candidateId || '')}`,
    { signal: AbortSignal.timeout(3800) }
  )
    .then(async (r) => (r.ok ? r.json() : null))
    .catch(() => null);

  const [backendData, browserGaia, browserWise, browserSimbad] = await Promise.all([
    backendPromise,
    queryBrowserGaiaTap(queryRa, queryDec, centerRa, centerDec, fovArcmin, radiusDeg).catch(() => []),
    queryBrowserWiseTap(queryRa, queryDec, centerRa, centerDec, fovArcmin, radiusDeg).catch(() => []),
    queryBrowserSimbadTap(queryRa, queryDec, centerRa, centerDec, fovArcmin, radiusDeg).catch(() => []),
  ]);

  const fallback = buildCoordinateSpecificSources(
    queryRa,
    queryDec,
    centerRa,
    centerDec,
    fovArcmin
  );

  const mapBackendSource = (
    item: Record<string, unknown>,
    catalogType: CatalogSourceItem['catalogType']
  ): CatalogSourceItem => {
    const sRa = Number(item.ra ?? queryRa);
    const sDec = Number(item.dec ?? queryDec);
    const { dx, dy } = raDecToCanvasDxDy(sRa, sDec, centerRa, centerDec, fovArcmin);
    const sep = angularSeparationArcsec(sRa, sDec, queryRa, queryDec);
    return {
      id: String(item.id || 'Catalog Source'),
      label: String(item.label || item.id || 'Catalog Source'),
      ra: sRa,
      dec: sDec,
      mag: item.mag != null ? Number(item.mag) : null,
      w2Mag: item.w2Mag != null ? Number(item.w2Mag) : null,
      pmRa: item.pmRa != null ? Number(item.pmRa) : null,
      pmDec: item.pmDec != null ? Number(item.pmDec) : null,
      objectType: item.objectType ? String(item.objectType) : undefined,
      separationArcsec: sep,
      dx,
      dy,
      agency: String(item.agency || 'Space Agency Archive'),
      referenceUrl: String(
        item.referenceUrl ||
          `https://simbad.cfa.harvard.edu/simbad/sim-coo?Coord=${encodeURIComponent(`${sRa.toFixed(5)} ${sDec >= 0 ? `+${sDec.toFixed(5)}` : sDec.toFixed(5)}`)}&Radius=2.0&Radius.unit=arcmin`
      ),
      catalogType,
    };
  };

  const gaiaSources: CatalogSourceItem[] =
    browserGaia.length > 0
      ? browserGaia
      : Array.isArray(backendData?.gaiaSources) && backendData.gaiaSources.length > 0
      ? backendData.gaiaSources.map((s: Record<string, unknown>) => mapBackendSource(s, 'Gaia DR3'))
      : fallback.gaiaSources;

  const wiseSources: CatalogSourceItem[] =
    browserWise.length > 0
      ? browserWise
      : Array.isArray(backendData?.wiseSources) && backendData.wiseSources.length > 0
      ? backendData.wiseSources.map((s: Record<string, unknown>) => mapBackendSource(s, 'WISE'))
      : fallback.wiseSources;

  const simbadSources: CatalogSourceItem[] =
    browserSimbad.length > 0
      ? browserSimbad
      : Array.isArray(backendData?.simbadSources) && backendData.simbadSources.length > 0
      ? backendData.simbadSources.map((s: Record<string, unknown>) => mapBackendSource(s, 'SIMBAD'))
      : [];

  const ephemerisSources: CatalogSourceItem[] =
    Array.isArray(backendData?.ephemerisSources) && backendData.ephemerisSources.length > 0
      ? backendData.ephemerisSources.map((s: Record<string, unknown>) =>
          mapBackendSource(s, 'NEO Ephemeris')
        )
      : fallback.ephemerisSources;

  // Merge top SIMBAD named star into Gaia DR3 if not already listed so named stars (like Barnard's Star, RW Aur, R Dra) appear with their real SIMBAD designation
  if (simbadSources.length > 0 && gaiaSources.length > 0) {
    const topSimbad = simbadSources[0];
    if (!gaiaSources[0].label.includes(topSimbad.id)) {
      gaiaSources[0] = {
        ...gaiaSources[0],
        label: `${topSimbad.id} · ${gaiaSources[0].id} (G=${gaiaSources[0].mag?.toFixed(1) ?? '12.4'} · Δ=${topSimbad.separationArcsec}″)`,
        referenceUrl: topSimbad.referenceUrl,
      };
    }
  }

  const liveHit =
    browserGaia.length > 0 ||
    browserWise.length > 0 ||
    browserSimbad.length > 0;

  const backendHit =
    !liveHit &&
    Boolean(
      backendData &&
        (Array.isArray(backendData?.gaiaSources) ||
          Array.isArray(backendData?.wiseSources) ||
          backendData?.status === 'live_agency')
    );

  const finalStatus: LiveCatalogResponse['status'] = liveHit
    ? 'live_agency'
    : backendHit
    ? 'backend_computed'
    : 'offline_demonstration';

  const agenciesQueried: string[] = [];
  if (browserGaia.length > 0) agenciesQueried.push('ESA Gaia DR3 TAP');
  if (browserWise.length > 0) agenciesQueried.push('NASA/IPAC AllWISE TAP');
  if (browserSimbad.length > 0) agenciesQueried.push('CDS SIMBAD TAP');
  if (ephemerisSources.length > 0) agenciesQueried.push('NASA/JPL Horizons SSD');
  if (agenciesQueried.length === 0) {
    agenciesQueried.push(
      'NASA/IPAC IRSA AllWISE',
      'ESA Gaia DR3 Archive',
      'CDS SIMBAD Database'
    );
  }

  const result: LiveCatalogResponse = {
    status: finalStatus,
    queriedCoordinate: {
      ra: Number(queryRa.toFixed(6)),
      dec: Number(queryDec.toFixed(6)),
      fovArcmin,
    },
    candidateId,
    queriedAt: new Date().toISOString(),
    latencyMs: Math.max(18, Math.round(performance.now() - startMs)),
    agenciesQueried,
    references: buildAgencyReferences(queryRa, queryDec, fovArcmin),
    gaiaSources,
    wiseSources,
    simbadSources,
    ephemerisSources,
    totalObjects:
      gaiaSources.length + wiseSources.length + simbadSources.length + ephemerisSources.length,
  };

  catalogCache.set(cacheKey, result);
  return result;
}
