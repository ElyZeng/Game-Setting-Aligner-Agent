import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
from config_manager.config_exporter import ConfigExporter

class Game:
    def __init__(self, name):
        self.name = name
        self.install_path = r'C:\games\test'
        self.platform = 'Steam'

cfg = os.path.join(PROJECT_ROOT, 'tmp_test_cfg.json')
out = os.path.join(PROJECT_ROOT, 'tmp_export.json')

with open(cfg, 'w', encoding='utf-8') as f:
    json.dump({
        'data': [{
            'group_name': '/video/display',
            'options': [
                {'name': 'Resolution', 'value': '1920x1080'},
                {'name': 'WindowMode', 'value': 0},
                {'name': 'VSync', 'value': 'UI-Settings-Video-QualitySetting-Off'},
                {'name': 'MaximumFPS_OnOff', 'value': True},
                {'name': 'MaximumFPS', 'value': 120},
                {'name': 'DynamicResolutionScaling', 'value': False},
                {'name': 'ResolutionScaling', 'value': 'DLSS'},
                {'name': 'FrameGeneration', 'value': False},
            ],
        }]
    }, f)

class WikiMock:
    def get_config_info(self, game):
        return {'raw_paths': [], 'expanded_paths': [cfg], 'error': None}

exporter = ConfigExporter(wiki_client=WikiMock())
exporter.export([Game('Cyberpunk 2077')], out)

with open(out, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(data['games']['Cyberpunk 2077']['parsed_settings'])

os.remove(cfg)
os.remove(out)
