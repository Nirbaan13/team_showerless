import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import build_variants as variants

import rebuild_release as rebuild
import export_overlays as export


def add(archive, name, content):
    info = tarfile.TarInfo(name)
    info.size = len(content)
    archive.addfile(info, io.BytesIO(content))


class RebuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_original_inventory_recovers_only_captured_vps_images(self):
        sources = [dict(image='original-'+name, image_id='sha256:'+str(index)*64,
                        revision='a'*40, os='linux', architecture='amd64')
                   for index, name in enumerate(['frontend', 'api', 'ml'], 1)]
        services = {}
        for name, index in [('frontend', 0), ('api', 1), ('pipeline', 1), ('ml-inference', 2)]:
            services[name] = dict(sources[index], image='derived-'+name, image_id='sha256:'+'f'*64,
                                  parent_image_id=sources[index]['image_id'])
        inventory = {'schema_version': 1, 'services': services, 'source_images': sources}
        recovered = rebuild.original_inventory(inventory)
        self.assertEqual(recovered['services']['api'], sources[1])
        self.assertEqual(recovered['services']['pipeline'], sources[1])
        self.assertEqual(recovered['services']['ml-inference'], sources[2])
        self.assertEqual(inventory['services']['api']['image'], 'derived-api')
        inventory['services']['api']['parent_image_id'] = 'sha256:'+'0'*64
        with self.assertRaisesRegex(ValueError, 'parent|captured'):
            rebuild.original_inventory(inventory)

    def test_seed_extraction_preserves_bytes_and_rejects_traversal_before_writing(self):
        source = self.root/'seed.tar'
        with tarfile.open(source, 'w') as archive:
            add(archive, 'api-data/demo/native.fits', b'public pinned scientific bytes')
            add(archive, 'ml-data/demo/manifest.json', b'{}')
        destination = self.root/'seed'
        rebuild.extract_seed(source, destination)
        self.assertEqual((destination/'api-data/demo/native.fits').read_bytes(), b'public pinned scientific bytes')
        with tarfile.open(source, 'w') as archive:
            add(archive, '../escaped', b'bad')
        rejected = self.root/'rejected'
        with self.assertRaises(ValueError):
            rebuild.extract_seed(source, rejected)
        self.assertFalse(rejected.exists())
        self.assertFalse((self.root/'escaped').exists())

    def test_release_identity_and_repository_are_strict(self):
        self.assertEqual(rebuild.release_tag('a'*40), 'demo-v1-main-'+'a'*40)
        for invalid in ('main', 'a'*12, 'A'*40, '../main'):
            with self.assertRaises(ValueError):
                rebuild.release_tag(invalid)
        with self.assertRaisesRegex(ValueError, 'repository'):
            rebuild.check_repository('another/project')
        rebuild.check_repository('Nirbaan13/team_showerless')
        archive = self.root/'download'
        archive.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum|SHA'):
            rebuild.verify_download(archive, '0'*64)

    def test_runtime_copy_plan_includes_all_final_stage_sources(self):
        (self.root/'model').mkdir()
        (self.root/'model/ranker.bin').write_bytes(b'model data')
        (self.root/'runtime').mkdir()
        (self.root/'runtime/current.py').write_text('current implementation')
        (self.root/'Dockerfile').write_text('FROM builder\nCOPY missing-build-input /build/\nFROM runtime\nCOPY --from=builder /stage /app/\nCOPY --chown=app:app runtime /app/runtime\nCOPY model/ranker.bin /app/models/\n')
        destination = self.root/'context'
        destination.mkdir()
        instructions = variants.runtime_copies(self.root, Path('Dockerfile'), destination)
        self.assertEqual((destination/'runtime/current.py').read_text(), 'current implementation')
        self.assertEqual((destination/'model/ranker.bin').read_bytes(), b'model data')
        self.assertIn('COPY model/ranker.bin /app/models/', instructions)
        self.assertNotIn('--from=builder', instructions)

    def test_workflow_token_is_removed_from_build_engine_children(self):
        seen = []
        def record(arguments, **kwargs):
            seen.append(kwargs['env'])
            return type('Result', (), {'returncode': 0})()
        with patch.dict(variants.os.environ, {'GH_TOKEN':'private', 'GITHUB_TOKEN':'private', 'GITHUB_SHA':'a'*40}), patch.object(variants.subprocess, 'run', side_effect=record):
            variants.image_engine('docker').call('image', 'inspect', 'captured:image')
        self.assertNotIn('GH_TOKEN', seen[0])
        self.assertNotIn('GITHUB_TOKEN', seen[0])
        self.assertEqual(seen[0]['GITHUB_SHA'], 'a'*40)

    def test_overlay_normalization_preserves_oci_bytes_and_resolves_referenced_links(self):
        source = self.root/'raw.tar'
        target = self.root/'export.tar.gz'
        config = b'{"architecture":"amd64"}'
        identity = hashlib.sha256(config).hexdigest()
        manifest = json.dumps([{'Config':'blobs/sha256/'+identity, 'RepoTags':['demo:sha'], 'Layers':['alias/layer.tar']}]).encode()
        index = b'{"schemaVersion":2,"manifests":[]}'
        with tarfile.open(source, 'w') as archive:
            add(archive, 'index.json', index)
            add(archive, 'oci-layout', b'{"imageLayoutVersion":"1.0.0"}')
            add(archive, 'blobs/sha256/'+identity, config)
            add(archive, 'real/layer.tar', b'layer bytes')
            link = tarfile.TarInfo('alias/layer.tar')
            link.type = tarfile.SYMTYPE
            link.linkname = '../real/layer.tar'
            archive.addfile(link)
            unused = tarfile.TarInfo('legacy/link')
            unused.type = tarfile.SYMTYPE
            unused.linkname = '/ignored/unreferenced'
            archive.addfile(unused)
            add(archive, 'manifest.json', manifest)
        export.normalize_archive(source, target)
        with tarfile.open(target) as archive:
            self.assertEqual(archive.extractfile('index.json').read(), index)
            self.assertEqual(archive.extractfile('blobs/sha256/'+identity).read(), config)
            self.assertTrue(archive.getmember('alias/layer.tar').isfile())
            self.assertEqual(archive.extractfile('alias/layer.tar').read(), b'layer bytes')
            self.assertNotIn('legacy/link', archive.getnames())

if __name__ == '__main__':
    unittest.main()
