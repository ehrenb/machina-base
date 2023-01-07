from datetime import datetime

from neomodel import StructuredRel, DateTimeProperty

class BaseRelationship(StructuredRel):
    """Base relationship"""

    ts = DateTimeProperty(default=lambda: datetime.now())