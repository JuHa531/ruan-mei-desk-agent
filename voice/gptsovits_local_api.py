"""Load the installed GPT-SoVITS API with local request protection.

Run from the GPT-SoVITS checkout, using its usual -a/-p/-c arguments. Model
loading and inference stay in the upstream implementation without patching it.
"""
import os
import sys

def main():
    sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'app'))
    from local_security import LoopbackASGIGuard
    # The launcher sets cwd to GPT-SoVITS, whose relative model paths must stay intact.
    if not os.path.isfile('api_v2.py'):
        raise RuntimeError('Start from the installed GPT-SoVITS checkout')
    sys.path.insert(0,os.getcwd())
    import api_v2
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
        return JSONResponse({'ok':ok, 'resources':resources}, status_code=200 if ok else 503)

    import uvicorn
    api_v2.APP.add_middleware(LoopbackASGIGuard)
    uvicorn.run(app=api_v2.APP,host='127.0.0.1',port=api_v2.port,workers=1)

if __name__=='__main__':main()
