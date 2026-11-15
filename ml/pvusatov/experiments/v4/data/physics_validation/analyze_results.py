"""Read-only interpretation of recorded physics results; metrics stay unchanged."""
from pathlib import Path
from datetime import datetime,timezone
import json
from native_overlay import digest
OWN=Path(__file__).resolve().parent

def main():
    stages={};all_frames=[]
    for stage in ['stationary','moving']:
        summary_path=OWN/f'summary-{stage}.json';records_path=OWN/f'results-{stage}.jsonl';summary=json.loads(summary_path.read_text());records=[json.loads(line)for line in records_path.read_text().splitlines()]
        executed=[record for record in records if record.get('executed')];epochs=[epoch for record in executed for epoch in record['epoch_metrics']];frames=[frame for record in executed for frame in record['frames']];all_frames.extend(frames)
        empty=[epoch for epoch in epochs if epoch['old_registered_response_sum']==0. and epoch['native_crop_response_sum']==0.]
        positive=[epoch for epoch in epochs if epoch['old_registered_response_sum']>0.]
        large_relative=[epoch for epoch in epochs if(epoch['delta_vs_old_add_median_relative_L2']or 0.)>.01]
        if len(records)!=summary['planned_trials']or len(executed)!=summary['executed_trials']:raise ValueError('Recorded physics counts differ')
        for record in executed:
            if not record['all_derivative_fits_deleted']or not record['all_nonimage_arrays_masks_physical_epochs_preserved']:raise ValueError('Physics cleanup/preservation assertion failed')
            for frame in record['frames']:
                if Path(frame['derivative']['derivative_path']).exists():raise ValueError('Scratch derivative unexpectedly retained')
        stages[stage]=dict(summary_sha256=digest(summary_path),records_sha256=digest(records_path),planned_trials=summary['planned_trials'],executed_trials=len(executed),unavailable_trials=summary['unavailable_trials'],runtime_errors=summary['runtime_error_trials'],derivative_epochs=len(epochs),
            maximum_absolute_prepared_delta_error=summary['maximum_delta_error'],raw_unconditioned_maximum_relative_L2=summary['maximum_relative_L2_error'],
            zero_response_epochs=len(empty),positive_response_epochs=len(positive),maximum_relative_L2_positive_response=max((epoch['delta_vs_old_add_median_relative_L2']or 0. for epoch in positive),default=None),
            maximum_absolute_error_zero_response=max((epoch['delta_vs_old_add_median_max_abs']for epoch in empty),default=None),
            large_relative_error_epochs=len(large_relative),large_relative_error_epochs_with_exactly_zero_response=sum(epoch in empty for epoch in large_relative),
            maximum_absolute_median_shift=max(abs(epoch['old_postregistration_median_shift'])for epoch in epochs),maximum_median_constant_prediction_error=max(epoch['median_constant_prediction_error']for epoch in epochs),
            epsf_zone_disagreements=sum(not epoch['independent_and_old_epsf_zone_agree']for epoch in epochs),all_full_celestial_wcs_include_sip=all(frame['independent_native_metadata']['has_sip']for frame in frames),
            native_crop_response_sum_range=[min(epoch['native_crop_response_sum']for epoch in epochs),max(epoch['native_crop_response_sum']for epoch in epochs)],
            native_motion_good_response_sum_range=[min(epoch['native_motion_good_response_sum']for epoch in epochs),max(epoch['native_motion_good_response_sum']for epoch in epochs)])
    report=dict(schema_version=1,created_utc=datetime.now(timezone.utc).isoformat(),scope='TRAIN-only engineering interpretation; original result files, metrics, source, model and cohorts unmodified',
        plan_sha256=digest(OWN/'plan.json'),analysis_source_sha256=digest(__file__),stages=stages,total_trials=sum(stage['planned_trials']for stage in stages.values()),total_derivative_epochs=len(all_frames),
        scratch_derivatives_retained=0,added_photon_noise=False,variance_updated=False,final_pixels_opened=False,model_or_detector_called=False,
        finding='Independent pre-registration IMAGE overlay and the historical registered response agree in absolute prepared-image units for these cases, after the existing median subtraction. Near-zero response makes relative error ill-conditioned; original unconditioned maximum remains visible.',
        scientific_limits=['No calibrated point-source flux or Poisson/electron conversion established.','No empirical PSF-shape or photometric calibration validation.','No ranking/recovery metric or real-control precision estimate.','Phase/mask/SIP agreement is engineering consistency, not astronomical motion confirmation.'])
    path=OWN/'analysis.json'
    with path.open('x')as handle:json.dump(report,handle,indent=2,allow_nan=False);handle.write('\n')
    print(json.dumps(report,indent=2));print('analysis_sha256',digest(path))
if __name__=='__main__':main()
