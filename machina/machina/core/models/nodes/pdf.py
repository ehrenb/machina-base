from pyorient.ogm.property import String, Long, DateTime

from machina.core.models import Node

class PDF(Node):
    element_plural = 'pdfs'
    element_type = 'pdf'

    # Common attributes
    md5 = String(nullable=False)
    sha256 = String(nullable=False)
    size = Long(nullable=False)
    ts = DateTime(nullable=False)
    type = String(nullable=False)
    ssdeep = String(nullable=True)