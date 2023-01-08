from neomodel import JSONProperty

from machina.core.models import Base

class PNG(Base):

    # PNG attributes
    exif = JSONProperty()