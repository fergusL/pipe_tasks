from .ingestCalibs import IngestCalibsTask, IngestCalibsConfig
from .read_defects import read_all_defects
from lsst.pipe.base import InputOnlyArgumentParser

import tempfile
import shutil
import os


class IngestDefectsArgumentParser(InputOnlyArgumentParser):
    """Argument parser to support ingesting calibration images into the repository"""

    def __init__(self, *args, **kwargs):
        InputOnlyArgumentParser.__init__(self, *args, **kwargs)
        self.add_argument("-n", "--dry-run", dest="dryrun", action="store_true",
                          default=False, help="Don't perform any action?")
        self.add_argument("--create", action="store_true", help="Create new registry?")
        self.add_argument("--ignore-ingested", dest="ignoreIngested", action="store_true",
                          help="Don't register files that have already been registered")
        self.add_argument("root", help="Root directory to scan for defects.")


class IngestDefectsConfig(IngestCalibsConfig):
    def setDefaults(self):
        if "filter" in self.register.columns:
            self.parse.defaults["filter"] = "NONE"


class IngestDefectsTask(IngestCalibsTask):
    """Task that generates registry for calibration images"""
    ArgumentParser = IngestDefectsArgumentParser
    _DefaultName = "ingestDefects"
    ConfigClass = IngestDefectsConfig

    def run(self, args):
        """Ingest all defect files and add them to the registry"""

        try:
            camera = args.butler.get('camera')
            temp_dir = tempfile.mkdtemp()
            defects = read_all_defects(args.root, camera)
            file_names = []
            for d in defects:
                for s in defects[d]:
                    file_name = f'defects_{d}_{s.isoformat()}.fits'
                    full_file_name = os.path.join(temp_dir, file_name)
                    self.log.info('%i defects written for sensor: %s and calibDate: %s' %
                                  (len(defects[d][s]), d, s.isoformat()))
                    defects[d][s].writeFits(full_file_name)
                    file_names.append(full_file_name)
            args.files = file_names
            args.mode = 'move'
            args.validity = None  # Validity range is determined from the files
            IngestCalibsTask.run(self, args)
        finally:
            shutil.rmtree(temp_dir)