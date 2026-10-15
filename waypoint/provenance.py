"""Passive developer provenance; no telemetry or device identifiers."""
import hashlib
DEVELOPER_EMAIL='youngwang6656@gmail.com'
FINGERPRINT=hashlib.sha256(('waypoint:developer:'+DEVELOPER_EMAIL).encode()).hexdigest()
def metadata():
    return {'format':'waypoint-developer-provenance','schema':1,'developer':DEVELOPER_EMAIL,
            'fingerprint':FINGERPRINT,'algorithm':'sha256','purpose':'passive-source-attribution'}
