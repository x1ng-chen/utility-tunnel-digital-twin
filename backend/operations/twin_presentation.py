"""Versioned model numbering is separate from unchanged firmware identities."""
import json
from copy import deepcopy
from pathlib import Path
from .models import TwinModelRelease

_catalog = Path(__file__).parent / 'agent_catalog'
BASE_INVENTORY = json.loads((_catalog / 'station-inventory.json').read_text(encoding='utf-8'))
V20 = json.loads((_catalog / 'model-v20-presentation.json').read_text(encoding='utf-8'))


def presentation_for_release(release):
    # A filename/version alone is not evidence that this exact model is loaded.
    if release and release.node_inventory_available and release.sha256 == V20['modelSha256']:
        return deepcopy(V20)
    return None


def runtime_inventory(release=None):
    release = release or TwinModelRelease.objects.filter(status='active').first()
    inventory = deepcopy(BASE_INVENTORY)
    presentation = presentation_for_release(release)
    if presentation:
        for binding in inventory['bindings']:
            binding['legacyStationId'] = binding['stationId']
            binding['stationId'] = presentation['sensorStations'][binding['assetCode']]
        inventory['controllerLegacyMeshes'] = presentation['controllerMeshes']
        inventory['modelNotice'] = presentation['notice']
        inventory['presentationRevision'] = presentation['revision']
        inventory['presentation'] = presentation
    return inventory
