"""Load the versioned frozen ONNX ranker. No fitting or sklearn dependency here."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort

FEATURE_NAMES = ('epoch_count', 'fit_rms_px', 'median_snr', 'min_snr',
                 'snr_coefficient_of_variation', 'median_peak_ratio')
SCORE_KIND = 'random_forest_vote_fraction'


class Ranker:
    """Bounded CPU inference; scores are uncalibrated mean tree leaf fractions."""

    def __init__(self, session: ort.InferenceSession, metadata: dict):
        self._session = session
        self.metadata = metadata

    def score(self, features: np.ndarray) -> np.ndarray:
        try:
            with np.errstate(over='ignore', invalid='ignore'):
                values = np.asarray(features, dtype=np.float32)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError('features must be finite numeric rows with shape (N, 6)') from exc
        if values.ndim != 2 or values.shape[1] != len(FEATURE_NAMES):
            raise ValueError('features must have shape (N, 6)')
        if not np.isfinite(values).all():
            raise ValueError('features must be finite float32 values')
        if not len(values):
            return np.empty(0, dtype=np.float32)
        labels, probabilities = self._session.run(['label', 'probabilities'], {'X': values})
        if (probabilities.shape != (len(values), 2) or not np.isfinite(probabilities).all()
                or np.any(probabilities < -1e-6) or np.any(probabilities > 1 + 1e-6)
                or not np.allclose(probabilities.sum(axis=1), 1, atol=2e-5)):
            raise ValueError('model produced invalid class scores')
        # Labels independently encode the graph's class ordering. A swapped graph
        # must not pass merely because its external metadata still claims [0, 1].
        winners = np.argmax(probabilities, axis=1)
        decisive = np.abs(probabilities[:, 0] - probabilities[:, 1]) > 2e-6
        if (labels.shape != (len(values),) or not np.isin(labels, [0, 1]).all()
                or np.any(labels[decisive] != winners[decisive])):
            raise ValueError('ONNX class labels disagree with declared class order [0, 1]')
        return np.clip(probabilities[:, 1], 0, 1)


def load_ranker(model_dir: Path | str | None = None) -> Ranker:
    """Verify the trusted installation's schema and SHA-256 before loading bytes."""
    directory = Path(model_dir) if model_dir is not None else Path(__file__).resolve().parent.parent / 'models'
    try:
        metadata = json.loads((directory / 'metadata.json').read_text(encoding='utf-8'))
        artifact = (directory / 'ranker.onnx').read_bytes()
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'cannot read frozen model: {exc}') from exc
    if not isinstance(metadata, dict):
        raise ValueError('model metadata must be an object')
    expected = dict(schema_version=1, feature_names=list(FEATURE_NAMES), class_labels=[0, 1],
                    positive_class=1, score_kind=SCORE_KIND)
    for name, value in expected.items():
        if metadata.get(name) != value:
            raise ValueError(f'incompatible model {name}')
    if not isinstance(metadata.get('model_id'), str) or not metadata['model_id']:
        raise ValueError('model_id must be a nonempty string')
    if metadata.get('sha256') != hashlib.sha256(artifact).hexdigest():
        raise ValueError('model SHA-256 checksum mismatch')
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.add_session_config_entry('session.intra_op.allow_spinning', '0')
    options.add_session_config_entry('session.inter_op.allow_spinning', '0')
    try:
        session = ort.InferenceSession(artifact, sess_options=options, providers=['CPUExecutionProvider'])
        embedded = session.get_modelmeta().custom_metadata_map
        if (embedded.get('schema_version') != '1'
                or json.loads(embedded.get('feature_names', 'null')) != list(FEATURE_NAMES)
                or json.loads(embedded.get('class_labels', 'null')) != [0, 1]
                or embedded.get('score_kind') != SCORE_KIND):
            raise ValueError('embedded ONNX schema does not match metadata')
        inputs = session.get_inputs()
        outputs = {item.name: item for item in session.get_outputs()}
        if (len(inputs) != 1 or inputs[0].name != 'X' or inputs[0].type != 'tensor(float)'
                or len(inputs[0].shape) != 2 or inputs[0].shape[1] != 6
                or 'label' not in outputs or outputs['label'].type != 'tensor(int64)'
                or 'probabilities' not in outputs
                or outputs['probabilities'].type != 'tensor(float)'
                or len(outputs['probabilities'].shape) != 2
                or outputs['probabilities'].shape[1] != 2):
            raise ValueError('incompatible ONNX input/output schema')
    except Exception as exc:
        raise ValueError(f'cannot load frozen ONNX model: {exc}') from exc
    ranker = Ranker(session, metadata)
    ranker.score(np.zeros((1, 6), dtype=np.float32))
    return ranker
