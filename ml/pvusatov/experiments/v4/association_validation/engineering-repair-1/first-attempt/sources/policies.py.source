"""DEV measured-hypothesis association policies; no labels or model fitting.

Hypothesis construction copies the unchanged original linker before its final
pair-exclusive pruning, preserving its2Mcheck/50khypothesis limits.
"""
from collections import Counter,defaultdict
import numpy as np
from scipy.spatial import cKDTree
from ml_inference.detector import Candidate,DetectionLimitError,baseline_score

MAX_OPS=10_000_000


def build_hypotheses(peaks, times, min_speed, max_speed, match_radius, min_epochs, *, subpixel=False,
                    max_link_checks=2_000_000, max_tracks=50_000):
    """Link (x, y, strength, shape metric) rows on a shared grid without target coordinates."""
    trees = [cKDTree(epoch[:, :2]) for epoch in peaks]

    tracks = {}
    link_checks = 0
    for start in range(len(peaks) - min_epochs + 1):
        for end in range(start + min_epochs - 1, len(peaks)):
            dt = times[end] - times[start]
            middle = np.arange(start + 1, end)
            for first_index, first in enumerate(peaks[start][:, :2]):
                offsets = peaks[end][:, :2] - first
                speeds = np.linalg.norm(offsets, axis=1) / dt
                end_ids = np.flatnonzero((speeds >= min_speed) & (speeds <= max_speed))
                if not len(end_ids):
                    continue
                link_checks += len(end_ids) * len(middle)
                if link_checks > max_link_checks:
                    raise DetectionLimitError("The linking search exceeds the supported work limit")
                predictions = first + (times[middle, None, None] - times[start]) / dt * offsets[end_ids]
                matches = np.column_stack([
                    trees[epoch].query(prediction, distance_upper_bound=match_radius)[1]
                    for epoch, prediction in zip(middle, predictions)
                ])
                for end_id, middle_ids in zip(end_ids, matches):
                    links = [(start, first_index)]
                    links.extend((epoch, index) for epoch, index in zip(middle, middle_ids)
                                 if index < len(peaks[epoch]))
                    links.append((end, end_id))
                    if len(links) < min_epochs or tuple(links) in tracks:
                        continue
                    epochs, indexes = zip(*links)
                    detections = np.array([peaks[epoch][index] for epoch, index in zip(epochs, indexes)])
                    positions = detections[:, :2]
                    path_times = times[list(epochs)]
                    centered_times = path_times - path_times.mean()
                    mean_position = positions.mean(axis=0)
                    velocity = (centered_times @ positions) / (centered_times @ centered_times)
                    fit = mean_position + centered_times[:, None] * velocity
                    rms = np.sqrt(np.mean(np.sum((positions - fit) ** 2, axis=1)))
                    speed = np.linalg.norm(velocity)
                    if rms <= match_radius / 2 and min_speed <= speed <= max_speed:
                        tracks[tuple(links)] = Candidate(
                            tuple(map(int, epochs)),
                            tuple(tuple(map(float if subpixel else int, xy)) for xy in positions),
                            tuple(map(float, detections[:, 2])), float(speed), float(rms),
                            float(np.median(detections[:, 3])),
                        )
                        if len(tracks) > max_tracks:
                            raise DetectionLimitError("The linking search exceeds the supported candidate limit")

    return list(tracks.items()),dict(link_checks=link_checks,hypotheses=len(tracks))


def _order(pool,priorities):
    values=np.asarray([baseline_score(c)for _,c in pool]if priorities is None else priorities,float)
    if values.shape!=(len(pool),)or not np.isfinite(values).all():raise ValueError('finite aligned ordering priorities required')
    return np.argsort(-values,kind='stable')


def pair_exclusive(pool,priorities=None,*,max_ops=MAX_OPS):
    seen=set();kept=[];operations=0;suppressed=0
    for i in _order(pool,priorities):
        links=pool[int(i)][0]
        pairs={(a,b)for j,a in enumerate(links)for b in links[j+1:]}
        operations+=len(pairs)
        if operations>max_ops:raise ValueError('association work cap; partial policy results withheld')
        if seen.isdisjoint(pairs):kept.append(int(i));seen.update(pairs)
        else:suppressed+=1
    return kept,dict(kept=len(kept),suppressed=suppressed,budgeted_pair_keys=operations,complete=True)


def near_duplicate(pool,*,max_ops=MAX_OPS,max_comparisons=1_000_000):
    index=defaultdict(set);kept=[];paths={};operations=0;comparisons=0;suppressed=0
    for i in _order(pool,None):
        i=int(i);track=pool[i][1];xy=np.asarray(track.positions_xy,float);counts=Counter()
        for epoch,(x,y)in zip(track.epochs,xy):
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    found=index.get((epoch,int(x)+dx,int(y)+dy),())
                    operations+=1+len(found)
                    if operations>max_ops:raise ValueError('near-duplicate index work cap; partial policy results withheld')
                    counts.update(found)
        duplicate=False
        for j,count in sorted(counts.items()):
            if count<3:continue
            other=pool[j][1];common=sorted(set(track.epochs)&set(other.epochs))
            if len(common)<3 or len(common)<.8*min(len(track.epochs),len(other.epochs)):continue
            comparisons+=1;operations+=len(common)
            if comparisons>max_comparisons or operations>max_ops:raise ValueError('near-duplicate comparison work cap; partial results withheld')
            a=np.asarray([xy[track.epochs.index(e)]for e in common]);b=np.asarray([paths[j][e]for e in common])
            if np.max(np.linalg.norm(a-b,axis=1))<=1.:
                duplicate=True;break
        if duplicate:suppressed+=1;continue
        kept.append(i);paths[i]={e:p for e,p in zip(track.epochs,xy)}
        for epoch,(x,y)in zip(track.epochs,xy):index[epoch,int(x),int(y)].add(i)
    return kept,dict(kept=len(kept),suppressed=suppressed,index_operations=operations,exact_comparisons=comparisons,complete=True,
        criterion='>=3common epochs,>=80%shorter-epoch overlap,maxcommon distance<=1px; proposal grouping,not proven identity')
