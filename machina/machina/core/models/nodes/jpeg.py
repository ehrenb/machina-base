from neomodel import JSONProperty

from machina.core.models import Base

class JPEG(Base):
    """JPEF Image file"""

    # PNG attributes
    exif = JSONProperty()