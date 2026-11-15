"""Versioned trusted-worker request validation and public-safe errors."""
import math

MAX_FRAMES = 32
MAX_SIDE = 512
MAX_RESULT_BYTES = 4 * 1024 * 1024


class InferenceError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


DEFAULTS = dict(min_snr=4., min_speed_arcsec_per_hour=3.075,
                max_speed_arcsec_per_hour=369., mask_policy='motion',
                max_candidates=100, max_peaks=100, pixel_scale_arcsec=6.15, min_epochs=3)


def validate_request(request):
    if not isinstance(request, dict) or type(request.get('schema_version')) is not int or request.get('schema_version') != 1:
        raise InferenceError('invalid_request', 'Unsupported request schema version')
    identifier = request.get('analysis_id')
    if not isinstance(identifier, str) or not 1 <= len(identifier) <= 128:
        raise InferenceError('invalid_request', 'A bounded analysis identifier is required')
    source = request.get('source')
    if not isinstance(source, dict) or source.get('kind') not in ('preset', 'fits'):
        raise InferenceError('invalid_request', 'A preset or FITS source is required')
    supplied = request.get('options', {})
    if not isinstance(supplied, dict) or set(supplied) - set(DEFAULTS):
        raise InferenceError('invalid_request', 'Unsupported analysis options')
    options = {**DEFAULTS, **supplied}
    for key in ('min_snr','min_speed_arcsec_per_hour','max_speed_arcsec_per_hour','pixel_scale_arcsec'):
        value = options[key]
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or value <= 0:
            raise InferenceError('invalid_request', 'Thresholds and pixel scale must be finite and positive')
    if options['min_speed_arcsec_per_hour'] > options['max_speed_arcsec_per_hour'] or options['pixel_scale_arcsec'] > 60:
        raise InferenceError('invalid_request', 'Speed range or pixel scale is unsupported')
    for key,minimum,maximum in [('max_candidates',1,100),('max_peaks',1,100),('min_epochs',3,32)]:
        value=options[key]
        if isinstance(value,bool) or not isinstance(value,int) or not minimum<=value<=maximum:
            raise InferenceError('workload_limit', 'Requested counts exceed the supported analysis bounds')
    if options['mask_policy'] not in ('science','motion'):
        raise InferenceError('invalid_request', 'Unknown mask policy')
    return options
