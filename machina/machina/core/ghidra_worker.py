import json
import logging
import os
from pathlib import Path
from pprint import pformat
from typing import List, Tuple
import sys

from machina.core.worker import Worker

class GhidraWorker(Worker):
    """Ghidra Analysis worker base class"""

    def __init__(self):
        super(GhidraWorker, self).__init__()

        self.logger.info(f"GhidraWorker subclass name: {self.cls_name}")

        # update worker config with GhidraWorker.json base default configurations, 
        # override with child class if specified.  
        self.config['worker'].update(self._load_ghidra_configs()['worker'])
        
        # set GHIDRA_MAXMEM env var which is used in the patched analyzeHeadless script to control max memory
        os.environ['GHIDRA_MAXMEM'] = self.config['worker']['maxmem']

        # update base configs
        self.gihdra_analyzeheadless_path = Path(os.environ['GHIDRA_HOME'], 'support', 'analyzeHeadless')


    def _load_ghidra_configs(self) -> dict:
        """reload config again using GhidraWorker.json as default base
        
        :return: the configuration dictionary
        :rtype: dict
        """

        fdir = '/configs'

        # Base-worker configurations, will be overridden by worker-specifc
        # configurations if there is overlap
        base_worker_cfg_fp = os.path.join(fdir, 'workers', 'GhidraWorker.json')
        with open(base_worker_cfg_fp, 'r') as f:
            worker_cfg = json.load(f)

        # Worker-specific configuration
        worker_cfg_fp = os.path.join(fdir, 'workers', self.cls_name+'.json')
        with open(worker_cfg_fp, 'r') as f:
            worker_cfg.update(json.load(f))

        return dict(
            worker=worker_cfg
        )


    #############################################################
    # Ghidra API wrappers
    def analyze_headless(
        self,
        project_location:str,
        project_name:str,
        import_files: List[str]=[],
        process:List[str]=[],
        pre_script:List[Tuple[str,List[str]]]=[],
        post_script:List[Tuple[str,List[str]]]=[],
        overwrite: bool=False,
        recursive: bool=False,
        read_only: bool=False,
        delete_poject: bool=False,
        no_analysis: bool=False,
        analysis_timeout_per_file: int=300
        ):
        """run Ghidra's analyzeHeadless

        :param project_location: root directory of an existing project to import (if 'import' set or 'process' set), or where a new project will be created (if 'import' set)
        :type project_location: str
        :param project_name: the name of an existing project to import (if 'import' set or 'process' set), or a new project (if 'import' set).  if the project name includes a folder path, imports will be rooted under that folder
        :type project_name: str
        :param import_files: list of executables and/or directories containing executables to import into a project. cannot be set when 'process' is set
        :type import_files: List[str], optional
        :param process: perform processing (pre/post scripts and/or analysis) on files in the list.  if not set, all files in project_name will be analyzed. cannot be set with 'import_files'
        :type process: List[str], optional
        :param pre_script: a list of tuples where the first element in a tuple is the pre script name (with extension), and the second element is a list of strings containing arguments (if any) for the script. example: [ ('prescript1.java', ['-my-arg1','-my1-arg2]), ('prescript2.java', ['-my2-arg1','-my2-arg2]) ] defaults to []
        :type pre_script: List[Tuple[str,List[str]]], optional
        :param post_script: a list of tuples where the first element in a tuple is the post script name (with extension), and the second element is a list of strings containing arguments (if any) for the script. example: [ ('postcript1.java', ['-my-arg1','-my1-arg2]), ('postscript2.java', ['-my2-arg1','-my2-arg2]) ] defaults to []
        :type post_script: List[Tuple[str,List[str]]], optional
        :param ovewrite: overwrite any existing project files that conflict with the ones being imported.  applies only if 'import' is set, and is ignored if 'read_only' is set. defaults to False
        :type overwrite: bool, optional
        :param recursive: enables decursive descent into directories and project sub-folders when a directory/folder has been specified in 'import' or 'process'. defaults to False
        :type recursive: bool, optional
        :param read_only: ensures imported files will not be written if 'import' is set.  also ensures any changes made when 'process' is set are discarded
        :param delete_project: delete the project once all scripts have completed.  only works on new projects created when 'import' is set. defaults to False
        :type delete_project: bool, optional
        :param no_analysis: disables auto-analysis from running, defaults to False
        :type no_analysis: bool, optional
        :param analysis_timeout_per_file: timeout value in seconds per file analysis. defaults to 300
        :type analysis_timeout_per_file: int

        """

        if not (import_files and process) or (import_files and process):
            self.logger.error('import_files OR process must be set')
            return

        cmd = f'{self.gihdra_analyzeheadless_path} {project_location} {project_name} '

        if import_files:
            cmd += ' '.join(import_files) + ' '
        if process:
            cmd += ' '.join(process) + ' '

        for script_cfg in pre_script:
            script_name = script_cfg[0]
            cmd += f'-preScript {script_name} '
            if len(script_cfg) > 1:
                script_args = script_cfg[1]
                for script_arg in script_args:
                    cmd += f'{script_arg} '

        for script_cfg in post_script:
            script_name = script_cfg[0]
            cmd += f'-postScript {script_name} '
            if len(script_cfg) > 1:
                script_args = script_cfg[1]
                for script_arg in script_args:
                    cmd += f'{script_arg} '

        if overwrite:
            cmd += '-overwrite '

        if recursive:
            cmd += '-recursive '

        if read_only:
            cmd += '-readOnly '

        if delete_poject:
            cmd += '-deleteProject '

        if no_analysis:
            cmd += '-noanalysis '

        cmd += f'-analysisTimeoutPerFile {analysis_timeout_per_file} '

        cmd += f'-max-cpu {self.config["worker"]["max_cpu"]}'

        self.logger.debug(f"running command: {cmd}")

    #############################################################

        # :param pre_script: a list of tuples where the first element in a tuple is the script name (with extension), and the second element is a list of strings containing arguments (if any) for the script, defaults to []
        # :type pre_script: List[Tuple[str,[str]]], optional