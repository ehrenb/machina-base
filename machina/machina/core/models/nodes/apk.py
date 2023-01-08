from neomodel import (JSONProperty, StringProperty, 
    ArrayProperty)

from machina.core.models import Base

class APK(Base):

    # APK Attribute
    package = StringProperty()
    name = StringProperty()
    androidversion_code = StringProperty()
    androidversion_name = StringProperty()
    permissions = ArrayProperty(StringProperty())
    activities = ArrayProperty(StringProperty())
    providers = ArrayProperty(StringProperty())
    receivers = ArrayProperty(StringProperty())
    services = ArrayProperty(StringProperty())
    min_sdk_version = StringProperty()
    max_sdk_version = StringProperty()
    max_sdk_version = StringProperty()
    effective_target_sdk_version = StringProperty()
    libraries = ArrayProperty(StringProperty())
    main_activity = StringProperty()
    content_provider_uris = ArrayProperty(StringProperty())

    classes = ArrayProperty(JSONProperty())
