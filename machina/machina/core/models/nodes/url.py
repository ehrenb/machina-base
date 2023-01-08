from neomodel import StringProperty

from machina.core.models import Base

class URL(Base):
    """extracted URL"""

    # URL Attribute
    url = StringProperty()