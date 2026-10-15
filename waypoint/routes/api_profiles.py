from fastapi import Body
from waypoint.api_profiles import PRESETS


def install(app):
    profiles = app.state.engine.api_profiles
    @app.get('/api/api-profiles')
    def listing(): return {'profiles': profiles.list(), 'presets': PRESETS}
    @app.post('/api/api-profiles')
    def create(data: dict = Body(...)): return profiles.save(data)
    @app.patch('/api/api-profiles/{id}')
    def update(id: str, data: dict = Body(...)): return profiles.save(data, id)
    @app.post('/api/api-profiles/{id}/models')
    async def models(id: str): return await profiles.read_models(id)
