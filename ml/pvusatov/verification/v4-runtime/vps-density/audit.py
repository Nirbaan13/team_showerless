"""Recheck every fixed density outcome and actual final cgroup receipt offline."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE.parent / 'density-stress'
digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
read = lambda path: json.loads(Path(path).read_text())


def main():
    hashes = {}
    def checked(path):
        hashes[str(path.relative_to(HERE.parent))] = digest(path)
        return read(path)
    manifest = checked(HERE / 'code-manifest.json')
    assert digest(HERE / 'code-manifest.json') == '770a8b0c08c51947b38c111edfa61ef762ef030f6555540c6fa8eb17c55f5152'
    for row in manifest['files']:
        assert digest(LOCAL / row['path']) == row['sha256']
        hashes[str((LOCAL / row['path']).relative_to(HERE.parent))] = row['sha256']
    cases = []
    for attempt, coordinator in (('attempt-1', 'host.py'), ('attempt-2', 'host_complete.py')):
        host = checked(HERE / attempt / 'host-proof.json')
        source_key = 'host_coordinator_sha256' if attempt == 'attempt-1' else 'coordinator_sha256'
        assert host[source_key] == digest(HERE / coordinator)
        assert host['image_id'] == 'sha256:8df7927bd71083a8419454906591d25d1e203b73a84608e2bce1e941da352573'
        assert host['limits'] == dict(Memory=1024**3, MemorySwap=1024**3, NanoCpus=10**9,
                                      PidsLimit=64, NetworkMode='none', ReadonlyRootfs=True)
        assert host['state']['ExitCode'] == 0 and not host['state']['OOMKilled']
        assert not host['production_services_modified']
        for count in (8, 32, 100):
            original = LOCAL / f'case-v2-{count}'
            current = HERE / attempt / 'density' / f'case-v2-{count}'
            left, right = checked(original / 'proof.json'), checked(current / 'proof.json')
            assert left['fixture_sha256'] == right['fixture_sha256']
            assert right['monitor_interruption'] is None
            assert right['shape'] == [32, 512, 512]
            assert right['source_sha256'] == left['source_sha256']
            for relative, expected in right['source_sha256'].items():
                repo = HERE.parents[4]
                assert digest(repo / relative) == expected
            assert right['exit_code'] == (0 if count == 8 else 2)
            assert right['status'] == ('CLI_SUCCESS' if count == 8 else 'CLI_ERROR')
            if count != 8:
                assert right['error']['code'] == 'workload_limit'
            assert checked(original / 'result.json') == checked(current / 'result.json')
            assert left['resources'] == right['resources']
            if count == 8:
                assert right['candidate_count'] == 100
                assert 'candidate_cap_reached_search_incomplete' in right['warnings']
                assert len(right['resources']) == 264
            cases.append(dict(attempt=attempt, engineering_sources=count, status=right['status'],
                              child_elapsed_seconds=right['elapsed_seconds'], child_rss_mib=right['child_maxrss_mib'],
                              identical_input_archive=True, entire_result_value_equal=True,
                              identical_png_hashes=len(right['resources'])))
    final = checked(HERE / 'attempt-2/cgroup-final.json')
    assert digest(HERE / 'attempt-2/cgroup-final.json') == read(HERE / 'attempt-2/host-proof.json')['cgroup-final.json']['sha256']
    after = final['after']
    assert after['memory.max'] == str(1024**3) and after['memory.swap.max'] == '0'
    assert after['cpu.max'] == '100000 100000'
    events = dict(line.split() for line in after['memory.events'].splitlines())
    assert all(int(events[key]) == 0 for key in ('max', 'oom', 'oom_kill', 'oom_group_kill'))
    assert int(after['memory.peak']) <= 1024**3
    proof = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(), status='PASS',
                 audit_source_sha256=digest(__file__), checked_files_sha256=hashes, cases=cases,
                 final_whole_container_peak_mib=final['peak_mib'], final_memory_events=events,
                 limits='One CPU, one GiB, no swap, network none; writable output/tmpfs and inherited anonymous app-data volume',
                 interpretation='Fixed engineering density outcomes, not worst-case completeness, sensitivity or scientific recovery',
                 first_attempt_limitation='Startup cgroup sample only; separate repeat supplies final whole-cgroup accounting',
                 second_attempt_reason='Close missing final cgroup peak/events without changing fixture, runtime, model or policies')
    (HERE / 'audit.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(dict(status=proof['status'], cases=len(cases), peak_mib=final['peak_mib'],
                          audit_sha256=digest(HERE / 'audit.json'))))


if __name__ == '__main__':
    main()
