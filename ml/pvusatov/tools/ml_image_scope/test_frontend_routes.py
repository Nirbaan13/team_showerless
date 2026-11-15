"""Exercise deployment readiness recovery using the Scala response shapes."""
import importlib.util
from pathlib import Path
import sys
from unittest.mock import patch


def test_nullable_model_discovery_retries_then_verifies_routes(capsys):
    path = Path(__file__).with_name('verify_frontend_routes.py')
    spec = importlib.util.spec_from_file_location('frontend_route_readiness', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    capabilities = dict(revision='test-revision', pipeline={'available': True},
                        motion_models={'models': [{'model_id': 'installed'}]},
                        motion_analysis={'status': 'supported', 'endpoint': '/api/analyses/motion'},
                        legacy_motion_service={'status': 'unsupported'},
                        community_catalogue={'status': 'unsupported'})
    unsupported = dict(code='unsupported_legacy_operation', retryable=False,
                       motion_analysis_url='/api/analyses/motion')
    transient = dict(capabilities, motion_models=None,
                     motion_analysis={'status': 'unavailable', 'endpoint': '/api/analyses/motion'})
    replies = [(200, transient), (200, capabilities),
               (200, {'models': [{'model_id': 'installed'}]})] + [(501, unsupported)] * 3
    with patch.object(module, 'request', side_effect=replies) as request, \
         patch.object(module.time, 'sleep') as sleep, \
         patch.object(sys, 'argv',
                      ['verify_frontend_routes.py', '--base-url', 'http://example.invalid']):
        module.main()
    assert request.call_count == 6
    sleep.assert_called_once_with(2)
    assert '"status": "PASS"' in capsys.readouterr().out
