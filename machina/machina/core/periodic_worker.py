from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
from typing import Type

from neomodel import config
from rocketry import Rocketry

from machina.core.models import Base

class PeriodicWorker():
    """Analysis worker base class.  Workers inheriting from this class analzye based on a schedule"""
    
    def __init__(self):
        self.cls_name = self.__class__.__name__
        self.config = self._load_configs()
        self.app = Rocketry()

        # Logging
        level = logging.getLevelName(self.config['worker']['log_level'])
        logging.basicConfig(level=level, format='[*] %(message)s')
        self.logger = logging.getLogger(__name__)

        # reduce Rocketry logging level
        logging.getLogger('rocketry.scheduler').setLevel(logging.ERROR)

        # neo4j set connection
        _cfg = self.config['neo4j']
        config.DATABASE_URL = f"bolt://{_cfg['user']}:{_cfg['pass']}@{_cfg['host']}:{_cfg['port']}/{_cfg['db_name']}"

    #############################################################
    # Privates
    def _load_configs(self) -> dict:
        """load configuration files from expected path, return as dictionary

        :return: the configuration dictionary
        :rtype: dict
        """

        fdir = '/configs'

        paths_cfg_fp = Path(fdir, 'paths.json')
        with open(paths_cfg_fp, 'r') as f:
            paths_cfg = json.load(f)

        neo4j_cfg_fp = Path(fdir, 'neo4j.json')
        with open(neo4j_cfg_fp, 'r') as f:
            neo4j_cfg = json.load(f)

        types_fp = Path(fdir, 'types.json')
        with open(types_fp, 'r') as f:
            types_cfg = json.load(f)

        # Base-worker configurations, will be overridden by worker-specifc
        # configurations if there is overlap
        base_worker_cfg_fp = Path(fdir, 'workers', 'PeriodicWorker.json')
        with open(base_worker_cfg_fp, 'r') as f:
            worker_cfg = json.load(f)

        # Worker-specific configuration
        worker_cfg_fp = Path(fdir, 'workers', self.cls_name+'.json')
        with open(worker_cfg_fp, 'r') as f:
            worker_cfg.update(json.load(f))

        return dict(paths=paths_cfg,
                    neo4j=neo4j_cfg,
                    types=types_cfg,
                    worker=worker_cfg)
    #############################################################

    def start(self):
        """start running callback at interval"""
        self.logger.info(f"starting with interval: {self.config['worker']['interval']}")
        self.app.task(self.config['worker']['interval'], func=self.callback)
        self.app.run()

    def callback(self):
        """implement in subclass"""
        raise NotImplemented

    #############################################################
    # Triggers
    def n_nodes_added_since(
        n: int, 
        node_cls: Type[Base], 
        duration: timedelta):
        """return True if 'n' nodes of 'node_cls' type have been added within a duration
        of time, return False if either (or both) condition was not met.

        :param n: the threshold number of nodes to consider before returning True
        :type n: int
        :param node_cls: the neomodel OGM class to use for counting node instances
        :type node_cls: type[Base]
        :param duration: the datetime.timedelta object specifying the threshold duration of time
        :type duration: timedelta
        :return: True if both conditions were met, False of neither (or both) not met
        :rtype: bool
        """

        # get adjusted timestamp for provided 
        # threshold duration
        now = datetime.now(timezone.utc)
        duration_ts = (now - duration)
        
        # filter nodes within the duration window
        nodes = node_cls.nodes.filter(ts__gte=duration_ts).order_by('ts')
        if len(nodes) >= n:
            return True
        return False
    #############################################################