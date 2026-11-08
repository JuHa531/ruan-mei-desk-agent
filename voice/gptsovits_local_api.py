"""Load the installed GPT-SoVITS API with local request protection.

Run from the GPT-SoVITS checkout, using its usual -a/-p/-c arguments. Model
loading and inference stay in the upstream implementation without patching it.
"""
import os
import sys
import gc
from pathlib import Path


def import_api_memory_efficient():
    """Map ZIP checkpoints during startup; retain normal loading for legacy files.

    Only temporary checkpoint storage changes. Models, dtype and inference stay
    untouched. Restore torch.load before accepting any requests.
    """
    import torch
    import zipfile
    original_load = torch.load

    def startup_load(source, *args, **kwargs):
        if (isinstance(source, (str, os.PathLike)) and 'mmap' not in kwargs
                and zipfile.is_zipfile(source)):
            kwargs['mmap'] = True
        return original_load(source, *args, **kwargs)

    torch.load = startup_load
    try:
        import api_v2
    finally:
        torch.load = original_load
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()  # Startup temporaries only; keep all live models.
    return api_v2

def main():
    sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'app'))
    from local_security import LoopbackASGIGuard
    # The launcher sets cwd to GPT-SoVITS, whose relative model paths must stay intact.
    if not os.path.isfile('api_v2.py'):
        raise RuntimeError('Start from the installed GPT-SoVITS checkout')
    sys.path.insert(0,os.getcwd())
    api_v2 = import_api_memory_efficient()
    import nltk
    # Upstream portable initialization overrides NLTK_DATA. Keep resources
    # installed in the selected Python environment reachable explicitly.
    nltk.data.path.insert(0, os.path.join(sys.prefix, 'nltk_data'))
    from fastapi.responses import JSONResponse

    @api_v2.APP.get('/healthz')
    def runtime_health():
        resources = {}
        for resource in ('taggers/averaged_perceptron_tagger_eng',):
            try:
                nltk.data.find(resource)
                resources[resource] = True
            except LookupError:
                resources[resource] = False
        ok = all(resources.values())
        config = api_v2.tts_pipeline.configs
        weights = {'gpt': str(Path(config.t2s_weights_path).resolve()),
                   'sovits': str(Path(config.vits_weights_path).resolve())}
        return JSONResponse({'ok':ok, 'resources':resources, 'weights':weights}, status_code=200 if ok else 503)

    import uvicorn
    api_v2.APP.add_middleware(LoopbackASGIGuard)
    uvicorn.run(app=api_v2.APP,host='127.0.0.1',port=api_v2.port,workers=1)

if __name__=='__main__':main()
