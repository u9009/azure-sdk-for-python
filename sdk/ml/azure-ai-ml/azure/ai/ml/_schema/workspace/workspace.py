# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

from marshmallow import EXCLUDE, fields

from azure.ai.ml._schema._utils.utils import validate_arm_str
from azure.ai.ml._schema.core.fields import NestedField, StringTransformedEnum
from azure.ai.ml._schema.core.schema import PathAwareSchema
from azure.ai.ml._schema.workspace.customer_managed_key import CustomerManagedKeySchema
from azure.ai.ml._schema.workspace.identity import IdentitySchema
from azure.ai.ml._schema.workspace.network_acls import NetworkAclsSchema
from azure.ai.ml._schema.workspace.networking import ManagedNetworkSchema
from azure.ai.ml._schema.workspace.serverless_compute import ServerlessComputeSettingsSchema
from azure.ai.ml._utils.utils import snake_to_pascal
from azure.ai.ml.constants._common import PublicNetworkAccess


class WorkspaceSchema(PathAwareSchema):
    name = fields.Str(required=True)
    location = fields.Str()
    id = fields.Str(dump_only=True)
    resource_group = fields.Str()
    description = fields.Str()
    discovery_url = fields.Str()
    display_name = fields.Str()
    hbi_workspace = fields.Bool()
    storage_account = fields.Str(validate=validate_arm_str)
    container_registry = fields.Str(validate=validate_arm_str)
    key_vault = fields.Str(validate=validate_arm_str)
    application_insights = fields.Str(validate=validate_arm_str)
    customer_managed_key = NestedField(CustomerManagedKeySchema)
    tags = fields.Dict(keys=fields.Str(), values=fields.Str())
    mlflow_tracking_uri = fields.Str(dump_only=True)
    image_build_compute = fields.Str()
    public_network_access = StringTransformedEnum(
        allowed_values=[PublicNetworkAccess.DISABLED, PublicNetworkAccess.ENABLED],
        casing_transform=snake_to_pascal,
    )
    network_acls = NestedField(NetworkAclsSchema)
    system_datastores_auth_mode = fields.Str()
    identity = NestedField(IdentitySchema)
    primary_user_assigned_identity = fields.Str()
    workspace_hub = fields.Str(validate=validate_arm_str)
    managed_network = NestedField(ManagedNetworkSchema, unknown=EXCLUDE)
    provision_network_now = fields.Bool()
    enable_data_isolation = fields.Bool()
    allow_roleassignment_on_rg = fields.Bool()
    serverless_compute = NestedField(ServerlessComputeSettingsSchema)
