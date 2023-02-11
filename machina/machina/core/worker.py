import json
import logging
from pathlib import Path
from pprint import pformat
import threading
import time
import typing
import sys

from machina.core.models import Base

import jsonschema
from neomodel import config
import pika

class Worker():
    """Analysis worker base class.  Workers inheriting from this class receive data to analyze based on the chosen data type bindings"""

    next_queues = [] # passes data to another queue in the sequence, this should allow for chaining
    types = [] # indicates what type data to bind to, this should be completed in the subclass
    types_blacklist = [] # indicates what type data NOT to bind to, this should be completed in the subclass. implies binding to all types not in this list.  cannot be combined with types

    def __init__(self):
        self.cls_name = self.__class__.__name__
        self.config = self._load_configs()
        self.schema = self._load_schema()

        # Logging
        level = logging.getLevelName(self.config['worker']['log_level'])
        logging.basicConfig(level=level, format='[*] %(message)s')
        self.logger = logging.getLogger(__name__)

        if self.types and self.types_blacklist:
            self.logger.error("both types and types_blacklist cannot be set at the same time")
            raise Exception

        # validate whitelist types
        # if *, then set types to all available types
        if self.types:
            self.logger.info(f"Validating types: {pformat(self.types)}")
            if '*' in self.types:
                self.types = self.config['types']['available_types']
            else:
                types_valid, t = self._types_valid()
                if not types_valid:
                    self.logger.error(f"{t} is not configured as a type in types.json")
                    raise Exception

        # validate black list types
        if self.types_blacklist:
            self.logger.info(f"Validating types blacklist: {pformat(self.types_blacklist)}")
            types_blacklist_valid, t = self._types_blacklist_valid()
            if not types_blacklist_valid:
                self.logger.error(f"{t} is not configured as a type in types.json, so cannot be blacklisted")
                raise Exception
            
            # if valid, set types to all except the ones in valid blacklist, and '*'
            self.types = [t for t in self.config['types']['available_types'] if t not in self.types_blacklist]
            # self.types.remove('*')

        # neo4j set connection
        _cfg = self.config['neo4j']
        config.DATABASE_URL = f"bolt://{_cfg['user']}:{_cfg['pass']}@{_cfg['host']}:{_cfg['port']}/{_cfg['db_name']}"

        # Initializer does no queue consumption, so
        # dont create a connection or queue for it
        if self.cls_name != 'Initializer':

            # RabbitMQ Connection info
            # note this is not thread-safe
            self.rmq_conn = self.get_rmq_conn()
            self.rmq_recv_channel = self.rmq_conn.channel()

            # reduce Pika logging level
            logging.getLogger('pika').setLevel(logging.ERROR)

            # The queue to bind to is the name of the class
            bind_queue = self.cls_name

            # Initialize an exchange
            self.rmq_recv_channel.exchange_declare('machina')

            # Initialize direct queue w/ subclass name
            self.logger.info(f"Binding to direct queue: {bind_queue}")
            self.rmq_recv_channel.queue_declare(self.cls_name, durable=True)

            # Ensure that the worker's queue is bound to the exchange
            self.rmq_recv_channel.queue_bind(exchange='machina',
                queue=self.cls_name)

            # multiple-bindings approach:
            # https://www.rabbitmq.com/tutorials/tutorial-four-python.html
            # Bind using type strings as routing_keys
            # Publish using only a routing_key should go to all queues
            # that are bound to that routing_key
            for t in self.types:
                self.logger.info(f'binding to type: {t}')
                self.rmq_recv_channel.queue_bind(exchange='machina',
                    queue=self.cls_name,
                    routing_key=t)

            self.rmq_recv_channel.basic_qos(prefetch_count=1)
            self.rmq_recv_channel.basic_consume(self.cls_name,
                on_message_callback=self._callback)

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

        rabbitmq_cfg_fp = Path(fdir, 'rabbitmq.json')
        with open(rabbitmq_cfg_fp, 'r') as f:
            rabbitmq_cfg = json.load(f)

        neo4j_cfg_fp = Path(fdir, 'neo4j.json')
        with open(neo4j_cfg_fp, 'r') as f:
            neo4j_cfg = json.load(f)

        types_fp = Path(fdir, 'types.json')
        with open(types_fp, 'r') as f:
            types_cfg = json.load(f)

        # Base-worker configurations, will be overridden by worker-specifc
        # configurations if there is overlap
        base_worker_cfg_fp = Path(fdir, 'workers', 'Worker.json')
        with open(base_worker_cfg_fp, 'r') as f:
            worker_cfg = json.load(f)

        # Worker-specific configuration
        worker_cfg_fp = Path(fdir, 'workers', self.cls_name+'.json')
        with open(worker_cfg_fp, 'r') as f:
            worker_cfg.update(json.load(f))

        return dict(paths=paths_cfg,
                    rabbitmq=rabbitmq_cfg,
                    neo4j=neo4j_cfg,
                    types=types_cfg,
                    worker=worker_cfg)

    def _load_schema(self) -> dict:
        """automatically resolve schema name based on class name

        :return: the schema dictionary
        :rtype: dict
        """
        class_schema = Path(self.config['paths']['schemas'], self.cls_name+'.json')
        with open(class_schema, 'r') as f:
            schema_data = json.load(f)
        return schema_data

    def _callback(
        self, 
        ch: pika.channel.Channel, 
        method: pika.spec.Basic.Deliver, 
        properties: pika.spec.BasicProperties, 
        body: bytes):
        """do last-second validation before handling the callback

        :param ch: pika channel
        :type ch: pika.channel.Channel
        :param method: pike method
        :type method: pika.spec.Basic.Deliver
        :param properties: pika properties
        :type properties: pika.spec.BasicProperties
        :param body: message body
        :type body: bytes
        """
        self._validate_body(body)

        self.logger.info("entering callback")
        thread = threading.Thread(target=self.callback, args=(body, properties))
        thread.start()
        while thread.is_alive():
            self.rmq_recv_channel._connection.sleep(1.0)
        self.logger.info("exiting callback")

        self.rmq_recv_channel.basic_ack(delivery_tag=method.delivery_tag)

    def _validate_body(self, body: bytes):
        """apply subclass worker schema and validate

        :param body: message body
        :type body: bytes
        """
        self.logger.info("validating schema")
        data = json.loads(body)
        # fixed resolver to ensure base schema uri is resolved
        # e.g. https://stackoverflow.com/questions/53968770/how-to-set-up-local-file-references-in-python-jsonschema-document
        # resolver = jsonschema.RefResolver('file://{}'.format(os.path.join(self.config['paths']['schemas'], 'binary.json')), self.schema)
        resolver = jsonschema.RefResolver(f"file:{Path(self.config['paths']['schemas'], self.cls_name+'.json')}", self.schema)

        jsonschema.validate(
            instance=data, 
            schema=self.schema, 
            resolver=resolver)

    def _types_valid(self) -> tuple:
        """ensure that the type to bind to is configured in types.json

        :return: tuple where first element is True if all requested type bindings are valid, or False if not.  If invalid, set the second element to the first discovered invalid type
        :rtype: tuple
        """
        for t in self.types:
            if t not in self.config['types']['available_types']:
                return False, t
        return True, None

    def _types_blacklist_valid(self) -> tuple:
        """ensure that the type to bind to is configured in types.json 

        :return: tuple where first element is True if all requested type bindings are valid, or False if not.  If invalid, set the second element to the first discovered invalid type
        :rtype: tuple
        """
        for t in self.types_blacklist:
            if t not in self.config['types']['available_types']:
                return False, t
        return True, None
    #############################################################

    #############################################################
    # RabbitMQ Helpers
    def get_rmq_conn(
        self, 
        max_attempts:int=10, 
        delay_seconds:int=1) -> pika.BlockingConnection:
        """get RabbitMQ connection instance

        :param max_attempts: max number of attempts to try to get the connection, defaults to 10
        :type max_attempts: int, optional
        :param delay_seconds: the delay between attempts to get the connection, defaults to 1
        :type delay_seconds: int, optional
        :return: the connection instance
        :rtype: pika.BlockingConnection
        """

        rabbitmq_user = self.config['rabbitmq']['rabbitmq_user']
        rabbitmq_password = self.config['rabbitmq']['rabbitmq_password']
        rabbitmq_host = self.config['rabbitmq']['rabbitmq_host']
        rabbitmq_port = self.config['rabbitmq']['rabbitmq_port']
        rabbitmq_heartbeat = self.config['rabbitmq']['rabbitmq_heartbeat']

        connection = None
        credentials = pika.PlainCredentials(rabbitmq_user, rabbitmq_password)
        parameters = pika.ConnectionParameters(rabbitmq_host,
            int(rabbitmq_port),
            '/',
            credentials,
            heartbeat=int(rabbitmq_heartbeat),
            socket_timeout=2)

        attempt = 0
        while attempt < max_attempts:
            try:
                connection = pika.BlockingConnection(parameters)
                break
            except pika.exceptions.AMQPConnectionError as e:
                self.logger.info(f"Attempt {attempt}/{max_attempts} to connect to RabbitMQ at {rabbitmq_host}:{rabbitmq_port}")
                self.logger.warn("Error connecting to RabbitMQ")
            
            attempt += 1
            time.sleep(delay_seconds)
        
        if not connection:
            self.logger.error('max attempts exceeded')
            sys.exit()

        return connection

    def start_consuming(self):
        """start consuming"""
        self.logger.info(f'{self.cls_name} worker started')
        try:
            self.rmq_recv_channel.start_consuming()
        except Exception as e:
            self.logger.error(e, exc_info=True)
            self.rmq_recv_channel.stop_consuming()
        self.connection.close()

    def callback(self, data: bytes, properties: pika.spec.BasicProperties):
        """callback for worker, implement in subclass

        :param data: incoming string payload
        :type data: bytes
        :param properties: message properties
        :type properties: pika.spec.BasicProperties
        :raises NotImplementedError:
        """
        raise NotImplementedError

    def publish_next(self, data: bytes):
        """publish to configured next_queues

        :param data: the data to publish
        :type data: bytes
        """
        if not self.next_queues:
            self.logger.warn('attempting to publish to next queue, but no next_queues defined in worker class')
        self.publish(data, queues=self.next_queues)

    def publish(self, data: bytes, queues: list):
        """publish directly to a list of arbitrary queues

        :param data: the data to publish
        :type data: bytes
        :param queues: the list of queue names (as strings) to publish data to
        :type queues: list
        """
        rmq_conn = self.get_rmq_conn()
        for q in queues:
            self.logger.info(f"publishing directly to {q}")
            rmq_channel = rmq_conn.channel()
            rmq_channel.basic_publish(
                exchange='machina',
                routing_key=q,
                body=data)
        rmq_conn.close()

    #############################################################

    #############################################################
    # Misc
    def get_binary_path(self, ts:str, md5:str) -> str:
        """get path to a binary on disk given a timestamp and its md5

        :param ts: the timestamp of the binary
        :type ts: str
        :param md5: the md5 of the binary
        :type md5: str
        :return: the path to the binary
        :rtype: str
        """
        binary_path = Path(self.config['paths']['binaries'], ts, md5)
        return str(binary_path)
#############################################################