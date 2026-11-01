"""Opt-in: prove a prepared compact bundle reopens without setup downloads.

Run with that bundle's runtime/python.exe and --root/--data pointing to an already
prepared bundle and its TouchHelm data directory. Does not open a camera or host.
"""
import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(args.root/'app'))
    from portable_setup import ComponentSetup
    setup=ComponentSetup(args.root,args.data)
    with patch('portable_setup.urllib.request.urlopen',side_effect=AssertionError('Unexpected network download')), \
         patch.object(setup,'command',side_effect=AssertionError('Unexpected package installation')):
        setup.ensure()
    report={'cached_setup_without_downloads':True,'camera_models_valid':setup.models_ready(),
            'remote_ready':setup.feature_ready('remote'),'camera_ready':setup.feature_ready('camera')}
    args.report.write_text(json.dumps(report,indent=2))
    print(json.dumps(report));assert all(report.values())


if __name__=='__main__':main()
