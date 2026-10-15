import asyncio,json
from pathlib import Path
from waypoint.providers.codex import CodexProvider
async def run_probe(data_dir:Path):
    p=CodexProvider(data_dir)
    try: return await p.capabilities()
    finally: await p.close()
if __name__=='__main__':
    print(json.dumps(asyncio.run(run_probe(Path.home()/'.waypoint')),ensure_ascii=False,indent=2))
