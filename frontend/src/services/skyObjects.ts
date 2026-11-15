/** Named fields with real SPHEREx observation manifests verified on 2026-11-15.
 * Positions are the published 2025.9 query centers, not J2000-epoch positions.
 * They select a field; they do not imply downloaded pixels or a detection.
 * Provenance and verification: frontend/docs/OBJECT-SEARCH.AI.md.
 */
export interface SkyObject {
  id: string;
  name: string;
  kind: string;
  aliases: string[];
  ra: number;
  dec: number;
}

export const SKY_OBJECTS: readonly SkyObject[] = [
  { id: 'barnard', name: "Barnard's Star", kind: 'Red dwarf', aliases: ['Barnard', 'Barnards Star', 'звезда Барнарда'], ra: 269.4462908, dec: 4.7679166 },
  { id: 'rw-aur', name: 'RW Aurigae', kind: 'Young variable star', aliases: ['RW Aur'], ra: 76.9565863, dec: 30.4012919 },
  { id: 'r-dra', name: 'R Draconis', kind: 'Variable red giant', aliases: ['R Dra'], ra: 248.1672345, dec: 66.7550237 },
  { id: 'wolf-28', name: 'Wolf 28', kind: 'White dwarf', aliases: [], ra: 12.3001416, dec: 5.3690989 },
  { id: 'lawd-37', name: 'LAWD 37', kind: 'White dwarf', aliases: [], ra: 176.473864, dec: -64.8439988 },
  { id: 'omi02-eri-b', name: '40 Eridani B', kind: 'White dwarf', aliases: ['40 Eri B', 'omi02 Eri B', 'Omicron2 Eridani B'], ra: 63.8245827, dec: -7.6821341 },
  { id: 'g-221-5', name: 'G 221-5', kind: 'Red dwarf', aliases: [], ra: 47.7899253, dec: 73.7644022 },
  { id: 'eps-indi-b', name: 'Epsilon Indi B', kind: 'Brown dwarf pair', aliases: ['eps Ind B', 'Epsilon Ind B'], ra: 331.0964419, dec: -56.8005917 },
  { id: 'wise-0855', name: 'WISE 0855-0714', kind: 'Brown dwarf', aliases: ['WISE0855', 'WISEA J085510.74-071442.5'], ra: 133.7599921, dec: -7.2422047 },
  { id: '2mass-j02511490-0352459', name: '2MASS J02511490-0352459', kind: 'Brown dwarf', aliases: ['2MASS0251'], ra: 42.8205188, dec: -3.8933583 },
];

export function findSkyObject(id: string | null | undefined): SkyObject | undefined {
  return SKY_OBJECTS.find(object => object.id === id);
}

function normalized(value: string): string {
  return value.toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
}

export function filterSkyObjects(query: string): readonly SkyObject[] {
  const needle = normalized(query);
  return SKY_OBJECTS.filter(object => [object.name, object.id, ...object.aliases].some(name => normalized(name).includes(needle)));
}
