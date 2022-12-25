from pyorient.ogm.property import String, Long, DateTime, EmbeddedMap

from machina.core.models import Node

class Word(Node):
    element_plural = 'words'
    element_type = 'word'

    # Common attributes
    md5 = String(nullable=False)
    sha256 = String(nullable=False)
    size = Long(nullable=False)
    ts = DateTime(nullable=False)
    type = String(nullable=False)
    ssdeep = String(nullable=True)