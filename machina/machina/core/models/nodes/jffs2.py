from pyorient.ogm.property import String, Long, DateTime

from machina.core.models import Node

class JFFS2(Node):
    element_plural = 'jffs2s'
    element_type = 'jffs2'

    # Common attributes
    md5 = String(nullable=False)
    sha256 = String(nullable=False)
    size = Long(nullable=False)
    ts = DateTime(nullable=False)
    type = String(nullable=False)
    ssdeep = String(nullable=True)