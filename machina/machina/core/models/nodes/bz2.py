from pyorient.ogm.property import String, Long, DateTime

from machina.core.models import Node

class BZ2(Node):
    element_plural = 'bz2s'
    element_type = 'bz2'

    # Common attributes
    md5 = String(nullable=False)
    sha256 = String(nullable=False)
    size = Long(nullable=False)
    ts = DateTime(nullable=False)
    type = String(nullable=False)
    ssdeep = String(nullable=True)