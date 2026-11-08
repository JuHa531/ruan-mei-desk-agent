"""Check checkpoint mapping scope without loading speech models."""
import builtins
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('voice_api', Path(__file__).resolve().parents[1] / 'voice/gptsovits_local_api.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StartupMemoryTests(unittest.TestCase):
    def run_import(self, fail=False):
        calls = []
        def load(source, *args, **kwargs):
            calls.append(kwargs)
        torch = types.SimpleNamespace(load=load, cuda=types.SimpleNamespace(is_available=lambda: False))
        original_import = builtins.__import__
        with tempfile.TemporaryDirectory() as folder:
            checkpoint = Path(folder) / 'model.pt'
            with zipfile.ZipFile(checkpoint, 'w') as archive:
                archive.writestr('model/data.pkl', b'test')
            def intercept(name, *args, **kwargs):
                if name == 'api_v2':
                    torch.load(checkpoint, map_location='cpu', weights_only=False)
                    torch.load(io.BytesIO(b'legacy'))
                    torch.load(checkpoint, mmap=False)
                    if fail:
                        raise RuntimeError('model loading failed')
                    return types.SimpleNamespace()
                return original_import(name, *args, **kwargs)
            with patch.dict(sys.modules, {'torch': torch}), patch('builtins.__import__', intercept):
                if fail:
                    with self.assertRaisesRegex(RuntimeError, 'model loading failed'):
                        module.import_api_memory_efficient()
                else:
                    module.import_api_memory_efficient()
            self.assertIs(torch.load, load)
        self.assertEqual(calls, [dict(map_location='cpu', weights_only=False, mmap=True), {}, dict(mmap=False)])

    def test_mapping_and_restore(self):
        self.run_import()

    def test_restore_on_failure(self):
        self.run_import(fail=True)



if __name__ == '__main__':
    unittest.main()
