from neomodel import StringProperty

from machina.core.models.relationships.base import BaseRelationship

class Extracts(BaseRelationship):
    """Establish a node (some binary data) as being
        extracted from another node"""
    label = 'extracts'

    # E.g. 'dynamic', 'static'
    method = StringProperty()