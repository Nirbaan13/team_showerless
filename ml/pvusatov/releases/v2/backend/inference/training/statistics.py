"""Paired whole-field bootstrap for the already frozen model's held-out comparison."""
import argparse
import json
from pathlib import Path
import numpy as np
from ml_inference.model import load_ranker


def paired_bootstrap(fields, score, top_k=3, draws=10_000, seed=274912):
    rows = []
    for field in fields:
        matches = np.asarray(field['matches'])
        values = []
        for ratings in [np.asarray(field['baseline']), score(field) if len(matches) else np.empty(0)]:
            selected = matches[np.argsort(-ratings, kind='stable')[:top_k]]
            values.extend([len(set(selected)-{-1}), int(np.count_nonzero(selected == -1))])
        rows.append([field['truth_count'], *values])
    a = np.asarray(rows)
    rng = np.random.default_rng(seed)
    totals = a[rng.integers(len(a), size=(draws, len(a)))].sum(axis=1)
    covered = totals[:, 0] > 0
    recall_difference = (totals[covered, 3]-totals[covered, 1])/totals[covered, 0]
    false_difference = (totals[:, 4]-totals[:, 2])/len(a)
    return dict(method=f'paired bootstrap of whole test fields, {draws} draws, seed{seed}',
                top_k=top_k,
                top_k_recall_difference_rf_minus_baseline_95percent=np.quantile(recall_difference, [.025, .975]).tolist() if covered.any() else None,
                false_tracks_per_field_difference_rf_minus_baseline_95percent=np.quantile(false_difference, [.025, .975]).tolist())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', default=str(Path(__file__).resolve().parents[1] / 'models'))
    args = parser.parse_args()
    directory = Path(args.model_dir)
    ranker = load_ranker(directory)
    fields = json.loads((directory / 'field-candidates.json').read_text())['test']
    report = paired_bootstrap(fields, lambda f: ranker.score(np.asarray(f['features'], np.float32)))
    report['model_sha256'] = ranker.metadata['sha256']
    (directory / 'evaluation-statistics.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
