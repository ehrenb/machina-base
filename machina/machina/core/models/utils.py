from datetime import datetime
from typing import Type

from machina.core.models import Artifact, Base

def resolve_db_node_cls(resolved_type: str) -> Type[Base]:
    """resolve a OGM subclass given a resolved machina type (e.g. in types.json)
    if not resolved, we expect unresolved to be stored as a generic Artifact, so return that cls

    :return: the type string to resolve to a class
    :rtype: str
    """
    all_models = Base.__subclasses__()
    for c in all_models:
        # if c.element_type.lower() == resolved_type.lower():
        if c.__name__.lower() == resolved_type.lower():
            return c
    return Artifact

def db_ts_to_fs_fmt(ts:datetime) -> str:
    """convert database timestamp to file-system formatted timestamp string"""
    return ts.strftime("%Y%m%d%H%M%S%f")