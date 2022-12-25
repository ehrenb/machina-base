import json
import logging
import os
from pprint import pformat
import threading
import time
import sys

import jsonschema
import pika
import pyorient
from pyorient.ogm import Graph, Config

# Import any new Nodes or Relationships here, they will be
# Automatically created with a call to init_orientdb()

# import all Nodes and Relationships
from machina.core.models import *

class Worker():
    """
        *types: the data types that a worker can handle, tagged by the Identifier
        *a queue whose name is the class' name: for direct access to the queue
    """
    next_queues = [] # passes data to another queue in the sequence, this should allow for chaining
    types = [] #indicates what queue to bind to, this should be completed in the subclass

    def __init__(self):
        self.cls_name = self.__class__.__name__
        self.config = self._load_configs()
        self.schema = self._load_schema()

        # Logging
        level = logging.getLevelName(self.config['worker']['log_level'])
        logging.basicConfig(level=level, format='[*] %(message)s')
        self.logger = logging.getLogger(__name__)

        self.logger.info(f"Validating types: {pformat(self.types)}")
        types_valid, t = self._types_valid()
        if not types_valid:
            self.logger.error(f"{t} is not configured as a type in types.json")
            raise Exception

        # OrientDB Connection
        self.logger.debug(f"OrientDB cfg: {pformat(self.config['orientdb'])}")
        self.graph = self.get_graph()

        # if regular worker, bind OGM classes,
        # Initializer does initial OGM creation
        if self.cls_name != 'Initializer':
            self.graph.include(Node.registry)
            self.graph.include(Relationship.registry)

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
                self.rmq_recv_channel.queue_bind(exchange='machina',
                                        queue=self.cls_name,
                                        routing_key=t)

            self.rmq_recv_channel.basic_qos(prefetch_count=1)
            self.rmq_recv_channel.basic_consume(self.cls_name,
                on_message_callback=self._callback)

    #############################################################
    # Privates

    def _load_configs(self):
        fdir = '/configs'

        paths_cfg_fp = os.path.join(fdir, 'paths.json')
        with open(paths_cfg_fp, 'r') as f:
            paths_cfg = json.load(f)

        rabbitmq_cfg_fp = os.path.join(fdir, 'rabbitmq.json')
        with open(rabbitmq_cfg_fp, 'r') as f:
            rabbitmq_cfg = json.load(f)

        rethinkdb_cfg_fp = os.path.join(fdir, 'rabbitmq.json')
        with open(rethinkdb_cfg_fp, 'r') as f:
            rethinkdb_cfg = json.load(f)

        orientdb_cfg_fp = os.path.join(fdir, 'orientdb.json')
        with open(orientdb_cfg_fp, 'r') as f:
            orientdb_cfg = json.load(f)

        types_fp = os.path.join(fdir, 'types.json')
        with open(types_fp, 'r') as f:
            types_cfg = json.load(f)

        # Base-worker configurations, will be overridden by worker-specifc
        # configurations if there is overlap
        base_worker_cfg_fp = os.path.join(fdir, 'workers', 'Worker.json')
        with open(base_worker_cfg_fp, 'r') as f:
            worker_cfg = json.load(f)

        # Worker-specific configuration
        worker_cfg_fp = os.path.join(fdir, 'workers', self.cls_name+'.json')
        with open(worker_cfg_fp, 'r') as f:
            worker_cfg.update(json.load(f))

        return dict(paths=paths_cfg,
                    rabbitmq=rabbitmq_cfg,
                    rethinkdb=rethinkdb_cfg,
                    orientdb=orientdb_cfg,
                    types=types_cfg,
                    worker=worker_cfg)

    def _load_schema(self):
        """automatically resolve schema name based on class name"""
        class_schema = os.path.join(self.config['paths']['schemas'], self.cls_name+'.json')
        with open(class_schema, 'r') as f:
            schema_data = json.load(f)

        return schema_data

    def _callback(self, ch, method, properties, body):
        """do last-second validation before handling the callback"""
        self._validate_body(body)

        self.logger.info("entering callback")

        thread = threading.Thread(target=self.callback, args=(body, properties))
        thread.start()
        while thread.is_alive():
            self.rmq_recv_channel._connection.sleep(1.0)
        self.logger.info("exiting callback")

        self.rmq_recv_channel.basic_ack(delivery_tag=method.delivery_tag)

    def _validate_body(self, body):
        """validate incoming messages from RabbitMQ"""
        self.logger.info("validating schema")
        data = json.loads(body)
        # fixed resolver to ensure base schema uri is resolved
        # e.g. https://stackoverflow.com/questions/53968770/how-to-set-up-local-file-references-in-python-jsonschema-document
        # resolver = jsonschema.RefResolver('file://{}'.format(os.path.join(self.config['paths']['schemas'], 'binary.json')), self.schema)
        resolver = jsonschema.RefResolver(f"file:{os.path.join(self.config['paths']['schemas'], self.cls_name+'.json')}", self.schema)

        jsonschema.validate(instance=data, schema=self.schema, resolver=resolver)

    def _types_valid(self):
        """ensure that the type queue to bind to is configured in types.json"""
        for t in self.types:
            if t not in self.config['types']['available_types']:
                return False, t
        return True, None
    #############################################################

    #############################################################
    # RabbitMQ Helpers
    def get_rmq_conn(self, max_attempts=10, delay_seconds=1):
        
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

    def callback(self, data, properties):
        """implement in subclass"""
        raise NotImplementedError

    def publish_next(self, data):
        """publish to configured next_queues"""
        self.publish(data, queues=self.next_queues)

    def publish(self, data, queues):
        """publish directly to a list of arbitrary queues"""
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
    # DB Helpers

    def get_graph(self, max_attempts=5, delay_seconds=1):
        host = self.config['orientdb']['orientdb_host']
        port = self.config['orientdb']['orientdb_port']
        name = self.config['orientdb']['orientdb_name']
        user = self.config['orientdb']['orientdb_user']
        password = self.config['orientdb']['orientdb_pass']
        
        orientdb_url = f'{host}:{port}/{name}'
        conf = Config.from_url(
            orientdb_url, 
            user, 
            password)

        attempts = 0
        graph = None
        while attempts < max_attempts:
            try:
                graph = Graph(conf)
                break
            except Exception as e:
                self.logger.warn(e)
            
            attempts += 1
            time.sleep(delay_seconds)

        if not graph:
            self.logger.error('max attempts to connect to graph exceeded')
            sys.exit()

        return graph

    def resolve_db_node_cls(self, resolved_type):
        """resolve class given a resolved machina type (e.g. in types.json)"""
        all_models = Node.__subclasses__()
        for c in all_models:
            if c.element_type.lower() == resolved_type.lower():
            # if c.__name__.lower() == resolved_type.lower():
                return c
        return None

    def update_node(
        self, 
        node_id,
        data,
        max_retries=10, 
        delay_seconds=1):
        """
        wrap nodde/vertex updating with retries to circumvent stale state
        :param node_id: the node id to resolve
        :param data: a dict containing the data you want to update/set in the node
        :param max_retries: max number of retries
        :return:
        """
        attempts = 0
        while attempts < max_retries:
            try:
                node = self.graph.get_vertex(node_id)
                for k,v in data.items():
                    # node[k] = v
                    setattr(node, k, v)
                node.save()
                break
            except pyorient.exceptions.PyOrientCommandException:
                self.logger.warn(f"Retrying update_node attempt {attempts}/{max_retries}")
                attempts += 1
                time.sleep(delay_seconds)

    def create_edge(
        self, 
        relationship, 
        origin_node_id, 
        destination_node_id, 
        data={}, 
        max_retries=10, 
        delay_seconds=1):
        """
        wrap create_edge in retries, as advised by
        http://orientdb.com/docs/last/Concurrency.html
        to circumvent stale vertex selects
        also refresh the vertex select each time by re-resolving based on its id
        :param relationship: Relationship class to apply to the edge
        :param origin_node_id: the origin/source node id to resolve
        :param destination_node_id: the destination node id to resolve
        :param max_retries: max number of retries
        :return: the edge created, None if not created
        """
        attempts = 0
        edge = None
        while attempts < max_retries:
            try:
                # Re-resolve the vertices, because they may have become stale
                origin_node = self.graph.get_vertex(origin_node_id)
                destination_node = self.graph.get_vertex(destination_node_id)
                edge = self.graph.create_edge(relationship, origin_node, destination_node, **data)
                break
            except pyorient.exceptions.PyOrientCommandException:
                self.logger.warn(f"Retrying create_edge attempt {attempts}/{max_retries}")
                attempts += 1
                time.sleep(delay_seconds)
        return edge
    #############################################################

    #############################################################
    # Misc
    def get_binary_path(self, ts, md5):
        binary_path = os.path.join(self.config['paths']['binaries'], ts, md5)
        return binary_path
#############################################################