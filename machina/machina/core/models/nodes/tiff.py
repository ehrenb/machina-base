from neomodel import JSONProperty

from machina.core.models import Base

class TIFF(Base):
    """TIFf image file"""
    
    # attributes
    exif = JSONProperty()