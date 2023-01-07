
from neomodel import (StructuredNode, StringProperty, IntegerProperty,
    UniqueIdProperty, DateTimeProperty, RelationshipTo, Relationship)

from machina.core.models.relationships.extracts import Extracts
from machina.core.models.relationships.similar import Similar
from machina.core.models.relationships.retyped import Retyped

class Base(StructuredNode):
    """Base node type"""

    __abstract_node__ = True
    
    # Common attributes
    uid = UniqueIdProperty()

    md5 = StringProperty(required=True)
    sha256 = StringProperty(required=True)
    size = IntegerProperty(required=True)
    ts = DateTimeProperty(required=True)
    type = StringProperty(required=True)

    ssdeep = StringProperty(required=False) # set later

    extracts = RelationshipTo('Base', 'EXTRACTS', model=Extracts)
    similar = Relationship('Base', 'SIMILAR', model=Similar)
    retyped = RelationshipTo('Base', 'RETYPED', model=Retyped)

