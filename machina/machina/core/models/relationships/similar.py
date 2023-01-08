from neomodel import JSONProperty

from machina.core.models.relationships.base import BaseRelationship

class Similar(BaseRelationship):
    """Establish a node (some binary data) as being
        to another node"""

    measurements = JSONProperty()