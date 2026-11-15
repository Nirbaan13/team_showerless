"""Standalone post-hoc figures from frozen report and scored native JSON only."""
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import csv
import gzip
import hashlib
import json
import math
import os
import sys
import tempfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np

HERE = Path(__file__).resolve().parent
REPAIR = HERE.parent
REPORT_SHA = '15cabb840cb8af95771f3534f2b5adfb18caaff5f0e8b57ed678f858525f7e56'
SPEEDS = [.01, .03, .1, .3, 1., 4., 10., 25., 50.]
BRIGHTNESS = [3., 6., 12., 24., 48.]
TITLE_COMPARISON = 'V4 − frozen C13 scorer · shared coverage-preserving preparation'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_csv(path, rows):
    if path.exists():
        raise ValueError('new figure output required')
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def save(fig, name):
    for suffix in ['png', 'svg']:
        target = HERE/(name+'.'+suffix)
        if target.exists():
            raise ValueError('new figure output required')
        fig.savefig(target, dpi=200, facecolor='white', metadata={'Creator':'Frozen V4 descriptive figure producer'})
    plt.close(fig)


def main():
    report_path = REPAIR/'report.json'
    assert sha(report_path) == REPORT_SHA
    report = json.loads(report_path.read_text())
    assert report['scope'] == 'final'
    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':11, 'axes.titlesize':13,
                         'axes.spines.top':False, 'axes.spines.right':False, 'svg.fonttype':'none'})
    inputs = {str(report_path):REPORT_SHA}
    macro = []
    for domain in ['native','synthetic']:
        row = report['reports'][domain]['all_planned']
        for budget in [1,3]:
            interval = row['paired_parent_ci95_top'+str(budget)]
            macro.append(dict(domain=domain, budget=budget, planned_trials=row['trials'], truths=row['truth_count'],
                independent_groups=row['independent_groups'], groups_with_truth=row['groups_with_truth'],
                baseline_recovered=row['baseline']['top'+str(budget)], candidate_recovered=row['candidate']['top'+str(budget)],
                baseline_macro_percent=100*row['baseline']['macro_recall'+str(budget)],
                candidate_macro_percent=100*row['candidate']['macro_recall'+str(budget)],
                delta_percentage_points=100*row['macro_delta_top'+str(budget)],
                paired_ci95_low_pp=100*interval[0], paired_ci95_high_pp=100*interval[1]))
    write_csv(HERE/'primary-macro-deltas.csv',macro)
    fig,ax=plt.subplots(figsize=(10.8,6.1))
    fig.subplots_adjust(left=.22,right=.96,top=.75,bottom=.30)
    positions=np.arange(4)[::-1]
    for y,row in zip(positions,macro):
        mean=row['delta_percentage_points'];lo=row['paired_ci95_low_pp'];hi=row['paired_ci95_high_pp']
        color='#176b95' if row['domain']=='native' else '#8b4c83'
        ax.errorbar(mean,y,xerr=[[mean-lo],[hi-mean]],fmt='o',color=color,
                    markersize=8,elinewidth=2,capsize=5,zorder=3)
        ax.text(hi+.17,y,f"+{mean:.2f}",va='center',fontsize=11,color=color,fontweight='bold')
    ax.set_yticks(positions,[f"{r['domain'].title()} · K={r['budget']}" for r in macro])
    ax.axvline(0,color='#39424c',lw=1)
    ax.set_xlim(-.3,10.8);ax.set_ylim(-.55,3.55)
    ax.set_xticks(np.arange(0,11,2));ax.grid(axis='x',color='#e2e6ea',zorder=0)
    ax.set_xlabel('Macro recovery gain (percentage points)',labelpad=9)
    fig.suptitle('Controlled injections: gain at fixed review budgets',x=.05,y=.96,ha='left',fontsize=18,fontweight='bold')
    fig.text(.05,.875,TITLE_COMPARISON,fontsize=11,color='#414a54')
    fig.text(.05,.19,'Dots: candidate minus baseline macro recovery. Bars: paired 95% bootstrap intervals from the frozen report.',fontsize=10)
    fig.text(.05,.145,'Native: 3,240 trials clustered within 12 parents. Synthetic: 5,993 truths in 3,000 planned fields;',fontsize=10)
    fig.text(.05,.105,'macro recall averages 2,400 truth-containing fields. Bootstrap: 10,000 paired parent/field resamples.',fontsize=10)
    fig.text(.05,.05,'Injection-ranking evidence, not real discoveries, survey sensitivity, or calibrated probabilities.',fontsize=10,color='#414a54')
    save(fig,'primary-macro-deltas')
    cells=defaultdict(lambda:dict(n=0,baseline_top1=0,baseline_top3=0,candidate_top1=0,candidate_top3=0))
    parents=set();identities=set();control_rows=0
    for ref in report['caches']['native']:
        path=Path(ref['path']);assert sha(path)==ref['sha256'];inputs[str(path)]=ref['sha256']
        with gzip.open(path,'rt') as stream:
            cache=json.load(stream)
        assert cache['summary']['evaluation_complete'] is True and cache['summary']['error_trials']==0
        assert len(cache['fields'])==270
        assert cache['parent_id'] not in parents;parents.add(cache['parent_id'])
        control_rows+=len(cache['control']['matches'])
        for field in cache['fields']:
            identity=(field['parent_id'],field['trajectory_id'],field['brightness'])
            assert identity not in identities;identities.add(identity)
            assert field['error'] is None and field['truth_count']==1 and field['peak_cap_reached'] is False
            cell=cells[field['speed_px_hour'],field['brightness']];cell['n']+=1
            labels=field['matches']
            for role,key in [('baseline','scores_c13'),('candidate','scores_v4')]:
                scores=field[key];assert len(scores)==len(labels)
                assert all(math.isfinite(s) for s in scores)
                order=sorted(range(len(scores)),key=lambda i:-scores[i])
                for budget in [1,3]:
                    cell[role+'_top'+str(budget)]+=len({labels[i] for i in order[:budget] if labels[i]>=0})
        del cache
    assert len(parents)==12 and len(identities)==3240 and control_rows==824
    assert set(cells)=={(s,b) for s in SPEEDS for b in BRIGHTNESS}
    heat_rows=[]
    for speed in SPEEDS:
        for brightness in BRIGHTNESS:
            cell=cells[speed,brightness];assert cell['n']==72
            heat_rows.append(dict(speed_px_hour=speed,brightness_injected_peak_over_MAD=brightness,
                planned_trials=72,baseline_top1=cell['baseline_top1'],candidate_top1=cell['candidate_top1'],
                delta_top1_pp=100*(cell['candidate_top1']-cell['baseline_top1'])/72,
                baseline_top3=cell['baseline_top3'],candidate_top3=cell['candidate_top3'],
                delta_top3_pp=100*(cell['candidate_top3']-cell['baseline_top3'])/72))
    for role in ['baseline','candidate']:
        for budget in [1,3]:
            assert sum(r[role+'_top'+str(budget)] for r in heat_rows)==report['reports']['native']['all_planned'][role]['top'+str(budget)]
    write_csv(HERE/'native-speed-brightness.csv',heat_rows)
    matrices={k:np.asarray([r['delta_top'+str(k)+'_pp'] for r in heat_rows]).reshape(9,5) for k in [1,3]}
    bound=max(5.,math.ceil(max(np.max(abs(m)) for m in matrices.values())/5)*5.)
    for budget,matrix in matrices.items():
        fig,ax=plt.subplots(figsize=(8.9,8.2))
        fig.subplots_adjust(left=.14,right=.84,top=.78,bottom=.28)
        image=ax.imshow(matrix,cmap='RdBu',norm=TwoSlopeNorm(vcenter=0,vmin=-bound,vmax=bound),aspect='auto')
        ax.set_xticks(range(5),[f'{b:g}' for b in BRIGHTNESS]);ax.set_yticks(range(9),[f'{s:g}' for s in SPEEDS])
        ax.set_xlabel('Injected typical peak / robust MAD reference',labelpad=8)
        ax.set_ylabel('Injected speed (pixels/hour)',labelpad=8)
        for y in range(9):
            for x in range(5):
                value=matrix[y,x];text=f'{value:+.1f}' if value else '0.0'
                ax.text(x,y,text,ha='center',va='center',fontsize=11,
                        color='white' if abs(value)>.56*bound else '#14202b')
        ax.set_xticks(np.arange(-.5,5,1),minor=True);ax.set_yticks(np.arange(-.5,9,1),minor=True)
        ax.grid(which='minor',color='white',lw=.8);ax.tick_params(which='minor',bottom=False,left=False)
        colorbar=fig.colorbar(image,ax=ax,fraction=.046,pad=.04)
        colorbar.set_label('Δ recovery (percentage points)',labelpad=8)
        fig.suptitle(f'Native injections: K={budget} gain by speed and brightness',x=.05,y=.96,ha='left',fontsize=16,fontweight='bold')
        fig.text(.05,.895,TITLE_COMPARISON,fontsize=10,color='#414a54')
        fig.text(.05,.845,'Each cell: 72 planned trials = 12 parent backgrounds × 6 directions. Original full-pool rankings.',fontsize=9.4)
        fig.text(.05,.18,'All 3,240 planned injections remain, including out-of-footprint and short-span trajectories.',fontsize=9.6)
        fig.text(.05,.135,'No filtering, reranking, or recentering. Cells are descriptive; no cell-wise uncertainty or multiplicity adjustment.',fontsize=9.1)
        fig.text(.05,.09,'Finite true-center coverage is not a hard detectability ceiling. Brightness is an engineering peak/MAD convention.',fontsize=9.1)
        fig.text(.05,.045,'Controlled injection-ranking results, not real discoveries, survey sensitivity, or calibrated probabilities.',fontsize=9.4,color='#414a54')
        save(fig,'native-k'+str(budget)+'-speed-brightness')
    assert sha(report_path)==REPORT_SHA
    description='''# Controlled injection-ranking figures

These standalone PNG and SVG figures describe the frozen, canonically unblinded comparison. The comparator is the **frozen C13 scorer under shared amended coverage-preserving preparation**, rather than the old deployed end-to-end C13 pipeline. No pixels, model artifacts, score calls, fitting, or new selection were used.

`primary-macro-deltas` shows native K1/K3 gains and synthetic K1/K3 gains in percentage points, using exactly the paired 95% intervals already validated in the frozen report. Native uncertainty clusters all derivatives by their 12 parent fields; synthetic uncertainty uses whole fields. These bars do not introduce new inference.

`native-k1-speed-brightness` and `native-k3-speed-brightness` show descriptive recovery differences. Every cell contains 72 planned trials: 12 native parent backgrounds times six directions, with one truth per trial. Every original competitor remains in its original stable score order. No injection, candidate, coverage category, or low-span trajectory was filtered or recentered. Each matrix retains all 3,240 planned native trials. Both maps use one symmetric color scale. Cells have no new uncertainty intervals and no multiplicity adjustment.

Speed is in pixels per hour. Brightness follows the frozen injection engineering convention: flux is scaled so a typical supported projected ePSF peak equals the requested brightness multiple of the median nonempty-epoch robust MAD reference. It is not calibrated flux, physical source signal-to-noise, or a probability. Fixed passband flux, correlated residual noise, absent injected photon noise, and native D1–3 coverage remain limitations of the underlying experiment.

Finite true-center coverage is not a hard necessary detectability ceiling; nearby valid peaks can recover PSF wings within the fixed matching tolerance. Covered or actual matched truth spans are diagnostic geometry rather than confirmation of physical motion. The figures show controlled injection ranking, not newly discovered objects or real survey sensitivity.

The two CSV files contain exact point values and counts. `manifest.json` binds their hashes, all image hashes, producer source, and frozen input cache/report hashes. The original report remains SHA `15cabb840cb8af95771f3534f2b5adfb18caaff5f0e8b57ed678f858525f7e56` and is unchanged. No gate or release decision is made here.
'''
    (HERE/'FIGURES.AI.md').write_text(description)
    products={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='manifest.json'}
    manifest=dict(schema_version=4,designation='POST-HOC PRESENTATION ONLY; controlled injection ranking, no new gates',
        created_utc=datetime.now(timezone.utc).isoformat(),producer_sha256=sha(__file__),
        python=sys.version.split()[0],matplotlib=matplotlib.__version__,numpy=np.__version__,
        frozen_report_sha256=REPORT_SHA,inputs=inputs,products=products,
        native_heatmap_cell_trials=72,native_planned_trials=3240,shared_heatmap_scale_pp=[-bound,bound],
        source_report_unchanged=True,no_pixels_models_fitting_scoring_or_selection=True)
    (HERE/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status='PASS',manifest_sha256=sha(HERE/'manifest.json'),files=len(products),heatmap_range_pp=[-bound,bound])))


if __name__=='__main__':
    main()
