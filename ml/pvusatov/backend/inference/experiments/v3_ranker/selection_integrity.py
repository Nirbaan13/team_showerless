"""Provenance and paired-system adapters; never relabel real unknown rows."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
from experiments.v3_evaluation.paired import paired_report,validate_cache_pair


def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_hashes(expected):
    """Fail closed if a training/cache byte changed after the fitting manifest."""
    for path,digest in expected.items():
        p=Path(path)
        if not p.is_file() or _sha(p)!=digest:raise ValueError('recorded input checksum mismatch: '+path)


def validate_relocated_source_hashes(expected):
    """Relocation changes names, never the source-byte provenance being checked."""
    inference=Path(__file__).resolve().parents[2]
    resolved={}
    for name,digest in expected.items():
        path=Path(name)
        if not path.exists() and 'backend/inference/' in name:
            path=inference/name.split('backend/inference/',1)[1]
        if not path.is_file() or _sha(path)!=digest:raise ValueError('fitting source checksum mismatch: '+name)
        resolved[name]=str(path.resolve())
    return resolved


def _identity(f):return (f['parent_id'],f['seed'],f['trajectory_id'],f['brightness'])


def normalize_native_pair(baseline,candidate):
    """Restore absent metadata only from a verified original source cache.

    Earlier narrow-filter caches used `shape` and omitted latent origin/velocity.
    The exact source-cache byte hash lets us restore metadata, without changing
    any candidate feature, match, score or attribution bit. Existing conflicting
    values still fail the root paired validator.
    """
    left,right=deepcopy(baseline),deepcopy(candidate)
    if 'registered_shape' not in right and 'shape' in right:right['registered_shape']=right['shape']
    missing=any(any(k not in f for k in ['origin_xy','velocity_xy_hour']) for f in right['fields'])
    if missing:
        if 'source_cache' not in right or 'source_cache_sha256' not in right:raise ValueError('missing latent metadata lacks verified source cache')
        source=Path(right['source_cache']);validate_hashes({str(source):right['source_cache_sha256']})
        with gzip.open(source,'rt') as handle:authoritative=json.load(handle)
        validate_cache_pair(left,authoritative)
        index={_identity(f):f for f in authoritative['fields']}
        for row in right['fields']:
            original=index[_identity(row)]
            for name in ['expected_xy','injected_flux','speed_px_hour','usable_center_epochs']:
                if row.get(name)!=original.get(name):raise ValueError('restored latent metadata differs: '+name)
            for name in ['origin_xy','velocity_xy_hour']:
                if name not in row:row[name]=deepcopy(original[name])
        right['metadata_restoration']=dict(source_cache=str(source),source_cache_sha256=right['source_cache_sha256'],fields=['origin_xy','velocity_xy_hour'],candidates_changed=False)
    validate_cache_pair(left,right)
    return left,right


def paired_native_report(baseline,candidate,baseline_scores,candidate_scores,bootstrap_samples=10000):
    return paired_report(baseline,candidate,baseline_scores,candidate_scores,bootstrap_samples=bootstrap_samples,bootstrap_seed=20261114)


def shared_selection_cohort(baseline,candidate):
    # Root validation rejects missing/duplicate identities and altered latent
    # trajectories before the shared mask is formed. These are actual heuristic
    # scores, used only to reuse its alignment checks; no fake model scores.
    paired_report(baseline,candidate,[f['baseline'] for f in baseline],[f['baseline'] for f in candidate],bootstrap_samples=1)
    left={_identity(f):f for f in baseline};right={_identity(f):f for f in candidate}
    shared={k for k in left if left[k].get('attribution_eligible',True) and right[k].get('attribution_eligible',True)}
    parents=sorted({f['parent_id'] for f in baseline});counts={}
    for parent in parents:
        keys=[k for k in left if left[k]['parent_id']==parent]
        counts[parent]=dict(planned=len(keys),sigma12_eligible=sum(left[k].get('attribution_eligible',True) for k in keys),sigma08_eligible=sum(right[k].get('attribution_eligible',True) for k in keys),shared_eligible=sum(k in shared for k in keys))
    return shared,dict(planned=len(left),sigma12_eligible=sum(f.get('attribution_eligible',True) for f in baseline),sigma08_eligible=sum(f.get('attribution_eligible',True) for f in candidate),shared_eligible=len(shared),by_parent=counts,features_labels_and_attribution_bits_changed=False)


def selection_subset(fields,values,shared_keys):
    if len(fields)!=len(values):raise ValueError('selection scores length mismatch')
    indices=[i for i,f in enumerate(fields) if _identity(f) in shared_keys]
    if len(indices)!=len(shared_keys):raise ValueError('selection cohort identities missing or duplicated')
    return [fields[i] for i in indices],[values[i] for i in indices]
