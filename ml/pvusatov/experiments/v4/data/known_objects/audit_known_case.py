"""Portable metadata-only replay of fixed-grid Ceres eligibility; no native pixels."""
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import argparse,gzip,hashlib,json,types,math

def digest(b):return hashlib.sha256(b).hexdigest()
def audit(case):
    case=Path(case);p=case/'search.py';helper=types.ModuleType('known_audit_helper');helper.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),helper.__dict__)
    read=lambda name:json.loads((case/name).read_text());plan=read('plan.json');assert digest((case/'plan.json').read_bytes())==helper.PLAN_SHA
    gridplan=read('point-grid-plan.json');assert gridplan['point_radius_deg']==.001 and gridplan['all_daily_points_before_selection']==15
    assert len(set(plan['excluded_physical_obsids']))==434
    index=read('xml-publication-index.json');xmlmap={Path(r['original_path']).name:r for r in index['xml_files']};assert len(xmlmap)==90
    log=read('search-log.json');selected=read('selected-metadata.json');raw=read('raw-handoff.json');headers=read('header-byte-audit.json');truth=read('offline-header-time-ephemeris.json')
    assert [(r['target'],r['anchor'])for r in log]==[('Ceres',d)for d in plan['anchor_dates'][:3]]
    checked=0;eligible=[];selected_rows=None
    for record in log:
        assert record['status']=='complete'and not record['failures'];point_rows={};domains={c:set()for c in plan['query']['collections']}
        for query in record['queries']:
            name=Path(query['path']).name;publication=xmlmap[name];b=gzip.decompress((case/publication['published_path']).read_bytes())
            assert digest(b)==query['sha256']==publication['original_sha256'];assert len(b)==publication['original_bytes']
            assert digest((case/publication['published_path']).read_bytes())==publication['published_sha256'];rows,status=helper.parse_sia(b);assert status==query['status']and len(rows)==query['raw_rows']
            request=read('evidence/'+name+'.request.json');params=parse_qs(urlsplit(request['url']).query);assert urlsplit(request['url']).netloc=='irsa.ipac.caltech.edu'and urlsplit(request['url']).path=='/SIA'
            collection=params['COLLECTION'][0];assert collection in domains and params['RESPONSEFORMAT']==['VOTABLE']and params['MAXREC'][0]in('512','4096')
            day=query['point_mjd'];domains[collection].add(day);coords=helper.parse_horizons(read('evidence/ceres-grid.json'),'Ceres');point=next(r for r in coords if r['mjd']==day)
            assert params['POS']==[f'CIRCLE {point["ra_deg"]:.10f} {point["dec_deg"]:.10f} 0.001']
            found=[r for r in rows if float(r['t_max'])>=max(record['t_min'],day-.5)and float(r['t_min'])<=min(record['t_max'],day+.5)]
            assert len(found)==query['time_filtered_rows'];assert not any(s.get('value')in('ERROR','OVERFLOW')for s in status)
            point_rows[(collection,day)]=found;checked+=1
        assert all(len(days)==15 for days in domains.values());rows=[r for found in point_rows.values()for r in found];assert len(rows)==record['raw_rows']
        usable=helper.deduplicate(rows,set(plan['excluded_physical_obsids']));assert len(usable)==record['unique_unexcluded_rows'];clusters=[]
        for detector in plan['selection']['detector_preference']:
            det=[r for r in usable if r['energy_bandpassname']==f'SPHEREx-D{detector}']
            for i,start in enumerate(det):
                cluster=[r for r in det[i:]if(float(r['t_max'])-float(start['t_min']))*24<=2][:5]
                if len(cluster)>=3:clusters.append((detector,cluster))
        for i,proof in enumerate(record['clusters_checked']):
            detector,cluster=clusters[i];assert proof['detector']==detector and proof['obsids']==[r['obs_id']for r in cluster]
            ep=case/'evidence'/Path(proof['ephemeris']['path']).name;assert digest(ep.read_bytes())==proof['ephemeris']['sha256'];exact=helper.parse_horizons(json.loads(ep.read_text()),'Ceres')
            times=[(float(r['t_min'])+float(r['t_max']))/2 for r in cluster];points=[min(exact,key=lambda p:abs(p['mjd']-t))for t in times];assert all(abs(p['mjd']-t)<2e-8 for p,t in zip(points,times))
            covered=[(r,p)for r,p in zip(cluster,points)if helper.inside(r['s_region'],[p['ra_deg'],p['dec_deg']])];roi=helper.common_roi([r for r,p in covered],[p for r,p in covered])if len(covered)>=3 else None
            assert len(covered)==proof['covered']and bool(roi)==proof['common_roi'];sep=min(helper.angle(roi['center'],c)for c in plan['excluded_parent_centers'].values())if roi else None
            if sep is not None:assert abs(sep-proof['minimum_parent_separation_deg'])<1e-9
            if roi and sep>=5:
                eligible.append((record['anchor'],detector,[r for r,p in covered],roi));assert i==len(record['clusters_checked'])-1
        if not eligible:assert len(record['clusters_checked'])==len(clusters)
    assert len(eligible)==1;anchor,detector,rows,roi=eligible[0];assert anchor==selected['anchor']and detector==selected['detector']and rows==selected['exposures']and roi==selected['roi'];assert raw['metadata_selection_sha256']==digest((case/'selected-metadata.json').read_bytes())
    assert len(raw['images'])==len(headers['downloads'])==len(truth['positions'])==4;assert len(set(raw['physical_obsids']))==4 and not set(raw['physical_obsids'])&set(plan['excluded_physical_obsids'])
    assert raw['pixels_opened']is False and raw['no_model_calls']is True
    for row,download,image,position in zip(rows,headers['downloads'],raw['images'],truth['positions']):
        assert row['obs_id']==download['obs_id']==image['obs_id']and image['sha256']==download['sha256'];assert download['header_only']is True and download['pixels_opened']is False and download['epsf_detcoord']=='sky'
        assert download['detector']==2 and abs(position['mjd']-download['midpoint_mjd'])<2e-8;assert helper.inside(row['s_region'],[position['ra_deg'],position['dec_deg']])
    assert truth['handoff_sha256']==digest((case/'raw-handoff.json').read_bytes())
    for point,stored in zip(truth['positions'],truth['parallax_arcsec_bounds']):assert abs(math.degrees(math.atan2(8000,point['range_au']*149597870.7-8000))*3600-stored)<1e-12
    return dict(status='PASS',query_responses=checked,complete_priority_anchors=len(log),checked_metadata_clusters=sum(len(r['clusters_checked'])for r in log),selected_target='Ceres',detector=2,physical_exposures=4,excluded_previous_physical_ids=434,byte_metadata=sum(r['bytes']for r in headers['downloads']),raw_handoff_sha256=digest((case/'raw-handoff.json').read_bytes()),scope='Published query/ephemeris/eligibility/header metadata linkage only; original native bytes and original execution environment not reverified; no pixels/models; narrower nonexhaustive daily-point discovery')
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',type=Path,default=Path(__file__).resolve().parent/'point-grid-0750');args=parser.parse_args();print(json.dumps(audit(args.case),indent=2))
