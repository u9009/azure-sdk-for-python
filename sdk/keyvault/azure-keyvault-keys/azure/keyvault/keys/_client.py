# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
from datetime import datetime
from functools import partial
from typing import Any, Dict, List, Optional, Union

from azure.core.paging import ItemPaged
from azure.core.polling import LROPoller
from azure.core.tracing.decorator import distributed_trace

from .crypto import CryptographyClient
from ._enums import KeyCurveName, KeyExportEncryptionAlgorithm, KeyOperation, KeyType
from ._generated.models import KeyAttributes
from ._models import JsonWebKey, KeyRotationLifetimeAction
from ._shared import KeyVaultClientBase
from ._shared._polling import DeleteRecoverPollingMethod, KeyVaultOperationPoller
from ._models import DeletedKey, KeyVaultKey, KeyProperties, KeyReleasePolicy, KeyRotationPolicy, ReleaseKeyResult


def _get_key_id(vault_url, key_name, version=None):
    without_version = f"{vault_url}/keys/{key_name}"
    return without_version + "/" + version if version else without_version


class KeyClient(KeyVaultClientBase):
    """A high-level interface for managing a vault's keys.

    :param str vault_url: URL of the vault the client will access. This is also called the vault's "DNS Name".
        You should validate that this URL references a valid Key Vault or Managed HSM resource.
        See https://aka.ms/azsdk/blog/vault-uri for details.
    :param credential: An object which can provide an access token for the vault, such as a credential from
        :mod:`azure.identity`
    :type credential: ~azure.core.credentials.TokenCredential

    :keyword api_version: Version of the service API to use. Defaults to the most recent.
    :paramtype api_version: ~azure.keyvault.keys.ApiVersion or str
    :keyword bool verify_challenge_resource: Whether to verify the authentication challenge resource matches the Key
        Vault or Managed HSM domain. Defaults to True.

    Example:
        .. literalinclude:: ../tests/test_samples_keys.py
            :start-after: [START create_key_client]
            :end-before: [END create_key_client]
            :language: python
            :caption: Create a new ``KeyClient``
            :dedent: 4
    """

    # pylint:disable=protected-access, too-many-public-methods

    def _get_attributes(
        self,
        enabled: Optional[bool],
        not_before: Optional[datetime],
        expires_on: Optional[datetime],
        exportable: Optional[bool] = None,
    ) -> Optional[KeyAttributes]:
        """Return a KeyAttributes object if non-None attributes are provided, or None otherwise.

        :param enabled: Whether the key is enabled.
        :type enabled: bool or None
        :param not_before: Not before date of the key in UTC.
        :type not_before: ~datetime.datetime or None
        :param expires_on: Expiry date of the key in UTC.
        :type expires_on: ~datetime.datetime or None
        :param exportable: Whether the private key can be exported.
        :type exportable: bool or None

        :returns: An autorest-generated model of the key's attributes.
        :rtype: KeyAttributes
        """
        if enabled is not None or not_before is not None or expires_on is not None or exportable is not None:
            return self._models.KeyAttributes(
                enabled=enabled, not_before=not_before, expires=expires_on, exportable=exportable
            )
        return None

    def get_cryptography_client(
            self,
            key_name: str,
            *,
            key_version: Optional[str] = None,
            **kwargs,  # pylint: disable=unused-argument
        ) -> CryptographyClient:
        """Gets a :class:`~azure.keyvault.keys.crypto.CryptographyClient` for the given key.

        :param str key_name: The name of the key used to perform cryptographic operations.

        :keyword key_version: Optional version of the key used to perform cryptographic operations.
        :paramtype key_version: str or None

        :returns: A :class:`~azure.keyvault.keys.crypto.CryptographyClient` using the same options, credentials, and
            HTTP client as this :class:`~azure.keyvault.keys.KeyClient`.
        :rtype: ~azure.keyvault.keys.crypto.CryptographyClient
        """
        key_id = _get_key_id(self._vault_url, key_name, key_version)

        # We provide a fake credential because the generated client already has the KeyClient's real credential
        return CryptographyClient(
            key_id, object(), generated_client=self._client, generated_models=self._models  # type: ignore
        )

    @distributed_trace
    def create_key(
        self,
        name: str,
        key_type: Union[str, KeyType],
        *,
        size: Optional[int] = None,
        curve: Optional[Union[str, KeyCurveName]] = None,
        public_exponent: Optional[int] = None,
        key_operations: Optional[List[Union[str, KeyOperation]]] = None,
        enabled: Optional[bool] = None,
        tags: Optional[Dict[str, str]] = None,
        not_before: Optional[datetime] = None,
        expires_on: Optional[datetime] = None,
        exportable: Optional[bool] = None,
        release_policy: Optional[KeyReleasePolicy] = None,
        **kwargs: Any,
    ) -> KeyVaultKey:
        """Create a key or, if ``name`` is already in use, create a new version of the key.

        Requires keys/create permission.

        :param str name: The name of the new key.
        :param key_type: The type of key to create
        :type key_type: ~azure.keyvault.keys.KeyType or str

        :keyword size: Key size in bits. Applies only to RSA and symmetric keys. Consider using
            :func:`create_rsa_key` or :func:`create_oct_key` instead.
        :paramtype size: int or None
        :keyword curve: Elliptic curve name. Applies only to elliptic curve keys. Defaults to the NIST P-256
            elliptic curve. To create an elliptic curve key, consider using :func:`create_ec_key` instead.
        :paramtype curve: ~azure.keyvault.keys.KeyCurveName or str or None
        :keyword public_exponent: The RSA public exponent to use. Applies only to RSA keys created in a Managed HSM.
        :paramtype public_exponent: int or None
        :keyword key_operations: Allowed key operations
        :paramtype key_operations: List[~azure.keyvault.keys.KeyOperation or str] or None
        :keyword enabled: Whether the key is enabled for use.
        :paramtype enabled: bool or None
        :keyword tags: Application specific metadata in the form of key-value pairs.
        :paramtype tags: dict[str, str] or None
        :keyword not_before: Not before date of the key in UTC
        :paramtype not_before: ~datetime.datetime or None
        :keyword expires_on: Expiry date of the key in UTC
        :paramtype expires_on: ~datetime.datetime or None
        :keyword exportable: Whether the private key can be exported.
        :paramtype exportable: bool or None
        :keyword release_policy: The policy rules under which the key can be exported.
        :paramtype release_policy: ~azure.keyvault.keys.KeyReleasePolicy or None

        :returns: The created key
        :rtype: ~azure.keyvault.keys.KeyVaultKey

        :raises ~azure.core.exceptions.HttpResponseError:

        Example:
            .. literalinclude:: ../tests/test_samples_keys.py
                :start-after: [START create_key]
                :end-before: [END create_key]
                :language: python
                :caption: Create a key
                :dedent: 8
        """
        attributes = self._get_attributes(
            enabled=enabled, not_before=not_before, expires_on=expires_on, exportable=exportable
        )

        policy = release_policy
        if policy is not None:
            policy = self._models.KeyReleasePolicy(
                encoded_policy=policy.encoded_policy, content_type=policy.content_type, immutable=policy.immutable
            )
        parameters = self._models.KeyCreateParameters(
            kty=key_type,
            key_size=size,
            key_attributes=attributes,
            key_ops=key_operations,
            tags=tags,
            curve=curve,
            public_exponent=public_exponent,
            release_policy=policy,
        )

        bundle = self._client.create_key(key_name=name, parameters=parameters, **kwargs)
        return KeyVaultKey._from_key_bundle(bundle)

    @distributed_trace
    def create_rsa_key(
        self,
        name: str,
        *,
        size: Optional[int] = None,
        public_exponent: Optional[int] = None,
        hardware_protected: Optional[bool] = False,
        key_operations: Optional[List[Union[str, KeyOperation]]] = None,
        enabled: Optional[bool] = None,
        tags: Optional[Dict[str, str]] = None,
        not_before: Optional[datetime] = None,
        expires_on: Optional[datetime] = None,
        exportable: Optional[bool] = None,
        release_policy: Optional[KeyReleasePolicy] = None,
        **kwargs: Any,
    ) -> KeyVaultKey:
        """Create a new RSA key or, if ``name`` is already in use, create a new version of the key

        Requires the keys/create permission.

        :param str name: The name for the new key.

        :keyword size: Key size in bits, for example 2048, 3072, or 4096.
        :paramtype size: int or None
        :keyword public_exponent: The RSA public exponent to use. Applies only to RSA keys created in a Managed HSM.
        :paramtype public_exponent: int or None
        :keyword hardware_protected: Whether the key should be created in a hardware security module.
            Defaults to ``False``.
        :paramtype hardware_protected: bool or None
        :keyword key_operations: Allowed key operations
        :paramtype key_operations: List[~azure.keyvault.keys.KeyOperation or str] or None
        :keyword enabled: Whether the key is enabled for use.
        :paramtype enabled: bool or None
        :keyword tags: Application specific metadata in the form of key-value pairs.
        :paramtype tags: dict[str, str] or None
        :keyword not_before: Not before date of the key in UTC
        :paramtype not_before: ~datetime.datetime or None
        :keyword expires_on: Expiry date of the key in UTC
        :paramtype expires_on: ~datetime.datetime or None
        :keyword exportable: Whether the private key can be exported.
        :paramtype exportable: bool or None
        :keyword release_policy: The policy rules under which the key can be exported.
        :paramtype release_policy: ~azure.keyvault.keys.KeyReleasePolicy or None

        :returns: The created key
        :rtype: ~azure.keyvault.keys.KeyVaultKey

        :raises ~azure.core.exceptions.HttpResponseError:

        Example:
            .. literalinclude:: ../tests/test_samples_keys.py
                :start-after: [START create_rsa_key]
                :end-before: [END create_rsa_key]
                :language: python
                :caption: Create RSA key
                :dedent: 8
        """
        return self.create_key(
            name,
            key_type="RSA-HSM" if hardware_protected else "RSA",
            size=size,
            public_exponent=public_exponent,
            key_operations=key_operations,
            enabled=enabled,
            tags=tags,
            not_before=not_before,
            expires_on=expires_on,
            exportable=exportable,
            release_policy=release_policy,
            **kwargs,
        )

    @distributed_trace
    def create_ec_key(
        self,
        name: str,
        *,
        curve: Optional[Union[str, KeyCurveName]] = None,
        key_operations: Optional[List[Union[str, KeyOperation]]] = None,
        hardware_protected: Optional[bool] = False,
        enabled: Optional[bool] = None,
        tags: Optional[Dict[str, str]] = None,
        not_before: Optional[datetime] = None,
        expires_on: Optional[datetime] = None,
        exportable: Optional[bool] = None,
        release_policy: Optional[KeyReleasePolicy] = None,
        **kwargs: Any,
    ) -> KeyVaultKey:
        """Create a new elliptic curve key or, if ``name`` is already in use, create a new version of the key.

        Requires the keys/create permission.

        :param str name: The name for the new key.

        :keyword curve: Elliptic curve name. Defaults to the NIST P-256 elliptic curve.
        :paramtype curve: ~azure.keyvault.keys.KeyCurveName or str or None
        :keyword key_operations: Allowed key operations
        :paramtype key_operations: List[~azure.keyvault.keys.KeyOperation or str] or None
        :keyword hardware_protected: Whether the key should be created in a hardware security module.
            Defaults to ``False``.
        :paramtype hardware_protected: bool or None
        :keyword enabled: Whether the key is enabled for use.
        :paramtype enabled: bool or None
        :keyword tags: Application specific metadata in the form of key-value pairs.
        :paramtype tags: dict[str, str] or None
        :keyword not_before: Not before date of the key in UTC
        :paramtype not_before: ~datetime.datetime or None
        :keyword expires_on: Expiry date of the key in UTC
        :paramtype expires_on: ~datetime.datetime or None
        :keyword exportable: Whether the private key can be exported.
        :paramtype exportable: bool or None
        :keyword release_policy: The policy rules under which the key can be exported.
        :paramtype release_policy: ~azure.keyvault.keys.KeyReleasePolicy or None

        :returns: The created key
        :rtype: ~azure.keyvault.keys.KeyVaultKey

        :raises ~azure.core.exceptions.HttpResponseError:

        Example:
            .. literalinclude:: ../tests/test_samples_keys.py
                :start-after: [START create_ec_key]
                :end-before: [END create_ec_key]
                :language: python
                :caption: Create an elliptic curve key
                :dedent: 8
        """
        return self.create_key(
            name,
            key_type="EC-HSM" if hardware_protected else "EC",
            curve=curve,
            key_operations=key_operations,
            enabled=enabled,
            tags=tags,
            not_before=not_before,
            expires_on=expires_on,
            exportable=exportable,
            release_policy=release_policy,
            **kwargs,
        )

    @distributed_trace
    def create_oct_key(
        self,
        name: str,
        *,
        size: Optional[int] = None,
        key_operations: Optional[List[Union[str, KeyOperation]]] = None,
        hardware_protected: Optional[bool] = False,
        enabled: Optional[bool] = None,
        tags: Optional[Dict[str, str]] = None,
        not_before: Optional[datetime] = None,
        expires_on: Optional[datetime] = None,
        exportable: Optional[bool] = None,
        release_policy: Optional[KeyReleasePolicy] = None,
        **kwargs: Any,
    ) -> KeyVaultKey:
        """Create a new octet sequence (symmetric) key or, if ``name`` is in use, create a new version of the key.

        Requires the keys/create permission.

        :param str name: The name for the new key.

        :keyword size: Key size in bits, for example 128, 192, or 256.
        :paramtype size: int or None
        :keyword key_operations: Allowed key operations.
        :paramtype key_operations: List[~azure.keyvault.keys.KeyOperation or str] or None
        :keyword hardware_protected: Whether the key should be created in a hardware security module.
            Defaults to ``False``.
        :paramtype hardware_protected: bool or None
        :keyword enabled: Whether the key is enabled for use.
        :paramtype enabled: bool or None
        :keyword tags: Application specific metadata in the form of key-value pairs.
        :paramtype tags: dict[str, str] or None
        :keyword not_before: Not before date of the key in UTC
        :paramtype not_before: ~datetime.datetime or None
        :keyword expires_on: Expiry date of the key in UTC
        :paramtype expires_on: ~datetime.datetime or None
        :keyword exportable: Whether the key can be exported.
        :paramtype exportable: bool or None
        :keyword release_policy: The policy rules under which the key can be exported.
        :paramtype release_policy: ~azure.keyvault.keys.KeyReleasePolicy or None

        :returns: The created key
        :rtype: ~azure.keyvault.keys.KeyVaultKey
        :raises ~azure.core.exceptions.HttpResponseError:

        Example:
            .. literalinclude:: ../tests/test_samples_keys.py
                :start-after: [START create_oct_key]
                :end-before: [END create_oct_key]
                :language: python
                :caption: Create an octet sequence (symmetric) key
                :dedent: 8
        """
        return self.create_key(
            name,
            key_type="oct-HSM" if hardware_protected else "oct",
            size=size,
            key_operations=key_operations,
            enabled=enabled,
            tags=tags,
            not_before=not_before,
            expires_on=expires_on,
            exportable=exportable,
            release_policy=release_policy,
            **kwargs,
        )

    @distributed_trace
    def begin_delete_key(self, name: str, **kwargs: Any) -> LROPoller[DeletedKey]:  # pylint:disable=bad-option-value,delete-operation-wrong-return-type
        """Delete all versions of a key and its cryptographic material.

        Requires keys/delete permission. When this method returns Key Vault has begun deleting the key. Deletion may
        take several seconds in a vault with soft-delete enabled. This method therefore returns a poller enabling you to
        wait for deletion to complete.

        :param str name: The name of the key to delete.

        :returns: A poller for the delete key operation. The poller's `result` method returns the
            :class:`~azure.keyvault.keys.DeletedKey` without waiting for deletion to complete. If the vault has
            soft-delete enabled and you want to permanently delete the key with :func:`purge_deleted_key`, call the
            poller's `wait` method first. It will block until the deletion is complete. The `wait` method requires
            keys/get permission.
        :rtype: ~azure.core.polling.LROPoller[~azure.keyvault.keys.DeletedKey]

        :raises ~azure.core.exceptions.ResourceNotFoundError or ~azure.core.exceptions.HttpResponseError:
            the former if the key doesn't exist; the latter for other errors

        Example:
            .. literalinclude:: ../tests/test_samples_keys.py
                :start-after: [START delete_key]
                :end-before: [END delete_key]
                :language: python
                :caption: Delete a key
                :dedent: 8
        """
        polling_interval = kwargs.pop("_polling_interval", None)
        if polling_interval is None:
            polling_interval = 2
        pipeline_response, deleted_key_bundle = self._client.delete_key(
            key_name=name,
            cls=lambda pipeline_response, deserialized, _: (pipeline_response, deserialized),
            **kwargs,
        )
        deleted_key = DeletedKey._from_deleted_key_bundle(deleted_key_bundle)

        command = partial(self.get_deleted_key, name=name, **kwargs)
        polling_method = DeleteRecoverPollingMethod(
            # no recovery ID means soft-delete is disabled, in which case we initialize the poller as finished
            finished=deleted_key.recovery_id is None,
            pipeline_response=pipeline_response,
            command=command,
            final_resource=deleted_key,
            interval=polling_interval,
        )
        return KeyVaultOperationPoller(polling_method)

    @distributed_trace
    def get_key(self, name: str, version: Optional[str] = None, **kwargs: Any) -> KeyVaultKey:
        """Get a key's attributes and, if it's an asymmetric key, its public material.

        Requires keys/get permission.

        :param str name: The name of the key to get.
        :param version: (optional) A specific version of the key to get. If not specified, gets the latest version
            of the key.
        :type version: str or None

        :returns: The fetched key.
        :rtype: ~azure.keyvault.keys.KeyVaultKey

        :raises ~azure.core.exceptions.ResourceNotFoundError or ~azure.core.exceptions.HttpResponseError:
            the former if the key doesn't exist; the latter for other errors

        Example:
            .. literalinclude:: ../tests/test_samples_keys.py
                :start-after: [START get_key]
                :end-before: [END get_key]
                :language: python
                :caption: Get a key
                :dedent: 8
        """
        bundle = self._client.get_key(name, key_version=version or "", **kwargs)
        return KeyVaultKey._from_key_bundle(bundle)

    @distributed_trace
    def get_deleted_key(self, name: str, **kwargs: Any) -> DeletedKey:
        """Get a deleted key. Possible only in a vault with soft-delete enabled.

        Requires keys/get permission.

        :param str name: The name of the key

        :returns: The deleted key
        :rtype: ~azure.keyvault.keys.DeletedKey

        :raises ~azure.core.exceptions.ResourceNotFoundError or ~azure.core.exceptions.HttpResponseError:
            the former if the key doesn't exist; the latter for other errors

        Example:
            .. literalinclude:: ../tests/test_samples_keys.py
                :start-after: [START get_deleted_key]
                :end-before: [END get_deleted_key]
                :language: python
                :caption: Get a deleted key
                :dedent: 8
        """
        bundle = self._client.get_deleted_key(name, **kwargs)
        return DeletedKey._from_deleted_key_bundle(bundle)

    @distributed_trace
    def list_deleted_keys(self, **kwargs: Any) -> ItemPaged[DeletedKey]:
        """List all deleted keys, including the public part of each. Possible only in a vault with soft-delete enabled.

        Requires keys/list permission.

        :returns: An iterator of deleted keys
        :rtype: ~azure.core.paging.ItemPaged[~azure.keyvault.keys.DeletedKey]

        Example:
            .. literalinclude:: ../tests/test_samples_keys.py
                :start-after: [START list_deleted_keys]
                :end-before: [END list_deleted_keys]
                :language: python
                :caption: List all the deleted keys
                :dedent: 8
        """
        return self._client.get_deleted_keys(
            maxresults=kwargs.pop("max_page_size", None),
            cls=lambda objs: [DeletedKey._from_deleted_key_item(x) for x in objs],
            **kwargs
        )

    @distributed_trace
    def list_properties_of_keys(self, **kwargs: Any) -> ItemPaged[KeyProperties]:
        """List identifiers and properties of all keys in the vault.

        Requires keys/list permission.

        :returns: An iterator of keys without their cryptographic material or version information
        :rtype: ~azure.core.paging.ItemPaged[~azure.keyvault.keys.KeyProperties]

        Example:
            .. literalinclude:: ../tests/test_samples_keys.py
                :start-after: [START list_keys]
                :end-before: [END list_keys]
                :language: python
                :caption: List all keys
                :dedent: 8
        """
        return self._client.get_keys(
            maxresults=kwargs.pop("max_page_size", None),
            cls=lambda objs: [KeyProperties._from_key_item(x) for x in objs],
            **kwargs
        )

    @distributed_trace
    def list_properties_of_key_versions(self, name: str, **kwargs: Any) -> ItemPaged[KeyProperties]:
        """List the identifiers and properties of a key's versions.

        Requires keys/list permission.

        :param str name: The name of the key

        :returns: An iterator of keys without their cryptographic material
        :rtype: ~azure.core.paging.ItemPaged[~azure.keyvault.keys.KeyProperties]

        Example:
            .. literalinclude:: ../tests/test_samples_keys.py
                :start-after: [START list_properties_of_key_versions]
                :end-before: [END list_properties_of_key_versions]
                :language: python
                :caption: List all versions of a key
                :dedent: 8
        """
        return self._client.get_key_versions(
            name,
            maxresults=kwargs.pop("max_page_size", None),
            cls=lambda objs: [KeyProperties._from_key_item(x) for x in objs],
            **kwargs
        )

    @distributed_trace
    def purge_deleted_key(self, name: str, **kwargs: Any) -> None:
        """Permanently deletes a deleted key. Only possible in a vault with soft-delete enabled.

        Performs an irreversible deletion of the specified key, without possibility for recovery. The operation is not
        available if the :py:attr:`~azure.keyvault.keys.KeyProperties.recovery_level` does not specify 'Purgeable'.
        This method is only necessary for purging a key before its
        :py:attr:`~azure.keyvault.keys.DeletedKey.scheduled_purge_date`.

        Requires keys/purge permission.

        :param str name: The name of the deleted key to purge

        :returns: None

        :raises ~azure.core.exceptions.HttpResponseError:

        Example:
            .. code-block:: python

                # if the vault has soft-delete enabled, purge permanently deletes a deleted key
                # (with soft-delete disabled, begin_delete_key is permanent)
                key_client.purge_deleted_key("key-name")

        """
        self._client.purge_deleted_key(key_name=name, **kwargs)

    @distributed_trace
    def begin_recover_deleted_key(self, name: str, **kwargs: Any) -> LROPoller[KeyVaultKey]:
        """Recover a deleted key to its latest version. Possible only in a vault with soft-delete enabled.

        Requires keys/recover permission.

        When this method returns Key Vault has begun recovering the key. Recovery may take several seconds. This
        method therefore returns a poller enabling you to wait for recovery to complete. Waiting is only necessary when
        you want to use the recovered key in another operation immediately.

        :param str name: The name of the deleted key to recover

        :returns: A poller for the recovery operation. The poller's `result` method returns the recovered
            :class:`~azure.keyvault.keys.KeyVaultKey` without waiting for recovery to complete. If you want to use the
            recovered key immediately, call the poller's `wait` method, which blocks until the key is ready to use. The
            `wait` method requires keys/get permission.
        :rtype: ~azure.core.polling.LROPoller[~azure.keyvault.keys.KeyVaultKey]

        :raises ~azure.core.exceptions.HttpResponseError:

        Example:
            .. literalinclude:: ../tests/test_samples_keys.py
                :start-after: [START recover_deleted_key]
                :end-before: [END recover_deleted_key]
                :language: python
                :caption: Recover a deleted key
                :dedent: 8
        """
        polling_interval = kwargs.pop("_polling_interval", None)
        if polling_interval is None:
            polling_interval = 2
        pipeline_response, recovered_key_bundle = self._client.recover_deleted_key(
            key_name=name,
            cls=lambda pipeline_response, deserialized, _: (pipeline_response, deserialized),
            **kwargs,
        )
        recovered_key = KeyVaultKey._from_key_bundle(recovered_key_bundle)
        command = partial(self.get_key, name=name, **kwargs)
        polling_method = DeleteRecoverPollingMethod(
            finished=False,
            pipeline_response=pipeline_response,
            command=command,
            final_resource=recovered_key,
            interval=polling_interval,
        )

        return KeyVaultOperationPoller(polling_method)

    @distributed_trace
    def update_key_properties(
        self,
        name: str,
        version: Optional[str] = None,
        *,
        key_operations: Optional[List[Union[str, KeyOperation]]] = None,
        enabled: Optional[bool] = None,
        tags: Optional[Dict[str, str]] = None,
        not_before: Optional[datetime] = None,
        expires_on: Optional[datetime] = None,
        release_policy: Optional[KeyReleasePolicy] = None,
        **kwargs: Any,
    ) -> KeyVaultKey:
        """Change a key's properties (not its cryptographic material).

        Requires keys/update permission.

        :param str name: The name of key to update
        :param version: (optional) The version of the key to update. If unspecified, the latest version is updated.
        :type version: str or None

        :keyword key_operations: Allowed key operations
        :paramtype key_operations: List[~azure.keyvault.keys.KeyOperation or str] or None
        :keyword enabled: Whether the key is enabled for use.
        :paramtype enabled: bool or None
        :keyword tags: Application specific metadata in the form of key-value pairs.
        :paramtype tags: dict[str, str] or None
        :keyword not_before: Not before date of the key in UTC
        :paramtype not_before: ~datetime.datetime or None
        :keyword expires_on: Expiry date of the key in UTC
        :paramtype expires_on: ~datetime.datetime or None
        :keyword release_policy: The policy rules under which the key can be exported.
        :paramtype release_policy: ~azure.keyvault.keys.KeyReleasePolicy or None

        :returns: The updated key
        :rtype: ~azure.keyvault.keys.KeyVaultKey

        :raises ~azure.core.exceptions.ResourceNotFoundError or ~azure.core.exceptions.HttpResponseError:
            the former if the key doesn't exist; the latter for other errors

        Example:
            .. literalinclude:: ../tests/test_samples_keys.py
                :start-after: [START update_key]
                :end-before: [END update_key]
                :language: python
                :caption: Update a key's attributes
                :dedent: 8
        """
        attributes = self._get_attributes(enabled=enabled, not_before=not_before, expires_on=expires_on)

        policy = release_policy
        if policy is not None:
            policy = self._models.KeyReleasePolicy(
                content_type=policy.content_type, encoded_policy=policy.encoded_policy, immutable=policy.immutable
            )
        parameters = self._models.KeyUpdateParameters(
            key_ops=key_operations,
            key_attributes=attributes,
            tags=tags,
            release_policy=policy,
        )

        bundle = self._client.update_key(
            name, key_version=version or "", parameters=parameters, **kwargs
        )
        return KeyVaultKey._from_key_bundle(bundle)

    @distributed_trace
    def backup_key(self, name: str, **kwargs: Any) -> bytes:
        """Back up a key in a protected form useable only by Azure Key Vault.

        Requires keys/backup permission.

        This is intended to allow copying a key from one vault to another. Both vaults must be owned by the same Azure
        subscription. Also, backup / restore cannot be performed across geopolitical boundaries. For example, a backup
        from a vault in a USA region cannot be restored to a vault in an EU region.

        :param str name: The name of the key to back up

        :returns: The key backup result, in a protected bytes format that can only be used by Azure Key Vault.
        :rtype: bytes

        :raises ~azure.core.exceptions.ResourceNotFoundError or ~azure.core.exceptions.HttpResponseError:
            the former if the key doesn't exist; the latter for other errors

        Example:
            .. literalinclude:: ../tests/test_samples_keys.py
                :start-after: [START backup_key]
                :end-before: [END backup_key]
                :language: python
                :caption: Get a key backup
                :dedent: 8
        """
        backup_result = self._client.backup_key(name, **kwargs)
        return backup_result.value

    @distributed_trace
    def restore_key_backup(self, backup: bytes, **kwargs: Any) -> KeyVaultKey:
        """Restore a key backup to the vault.

        Requires keys/restore permission.

        This imports all versions of the key, with its name, attributes, and access control policies. If the key's name
        is already in use, restoring it will fail. Also, the target vault must be owned by the same Microsoft Azure
        subscription as the source vault.

        :param bytes backup: A key backup as returned by :func:`backup_key`

        :returns: The restored key
        :rtype: ~azure.keyvault.keys.KeyVaultKey

        :raises ~azure.core.exceptions.ResourceExistsError or ~azure.core.exceptions.HttpResponseError:
            the former if the backed up key's name is already in use; the latter for other errors

        Example:
            .. literalinclude:: ../tests/test_samples_keys.py
                :start-after: [START restore_key_backup]
                :end-before: [END restore_key_backup]
                :language: python
                :caption: Restore a key backup
                :dedent: 8
        """
        bundle = self._client.restore_key(
            parameters=self._models.KeyRestoreParameters(key_bundle_backup=backup),
            **kwargs
        )
        return KeyVaultKey._from_key_bundle(bundle)

    @distributed_trace
    def import_key(
        self,
        name: str,
        key: JsonWebKey,
        *,
        hardware_protected: Optional[bool] = None,
        enabled: Optional[bool] = None,
        tags: Optional[Dict[str, str]] = None,
        not_before: Optional[datetime] = None,
        expires_on: Optional[datetime] = None,
        exportable: Optional[bool] = None,
        release_policy: Optional[KeyReleasePolicy] = None,
        **kwargs: Any,
    ) -> KeyVaultKey:
        """Import a key created externally.

        Requires keys/import permission. If ``name`` is already in use, the key will be imported as a new version.

        :param str name: Name for the imported key
        :param key: The JSON web key to import
        :type key: ~azure.keyvault.keys.JsonWebKey

        :keyword hardware_protected: Whether the key should be backed by a hardware security module
        :paramtype hardware_protected: bool or None
        :keyword enabled: Whether the key is enabled for use.
        :paramtype enabled: bool or None
        :keyword tags: Application specific metadata in the form of key-value pairs.
        :paramtype tags: dict[str, str] or None
        :keyword not_before: Not before date of the key in UTC
        :paramtype not_before: ~datetime.datetime or None
        :keyword expires_on: Expiry date of the key in UTC
        :paramtype expires_on: ~datetime.datetime or None
        :keyword exportable: Whether the private key can be exported.
        :paramtype exportable: bool or None
        :keyword release_policy: The policy rules under which the key can be exported.
        :paramtype release_policy: ~azure.keyvault.keys.KeyReleasePolicy or None

        :returns: The imported key
        :rtype: ~azure.keyvault.keys.KeyVaultKey

        :raises ~azure.core.exceptions.HttpResponseError:
        """
        attributes = self._get_attributes(
            enabled=enabled, not_before=not_before, expires_on=expires_on, exportable=exportable
        )

        policy = release_policy
        if policy is not None:
            policy = self._models.KeyReleasePolicy(
                content_type=policy.content_type, encoded_policy=policy.encoded_policy, immutable=policy.immutable
            )
        parameters = self._models.KeyImportParameters(
            key=key._to_generated_model(),
            key_attributes=attributes,
            hsm=hardware_protected,
            tags=tags,
            release_policy=policy,
        )

        bundle = self._client.import_key(name, parameters=parameters, **kwargs)
        return KeyVaultKey._from_key_bundle(bundle)

    @distributed_trace
    def release_key(
        self,
        name: str,
        target_attestation_token: str,
        *,
        version: Optional[str] = None,
        algorithm: Optional[Union[str, KeyExportEncryptionAlgorithm]] = None,
        nonce: Optional[str] = None,
        **kwargs: Any,
    ) -> ReleaseKeyResult:
        """Releases a key.

        The release key operation is applicable to all key types. The target key must be marked
        exportable. This operation requires the keys/release permission.

        :param str name: The name of the key to get.
        :param str target_attestation_token: The attestation assertion for the target of the key release.

        :keyword version: A specific version of the key to release. If unspecified, the latest version is released.
        :paramtype version: str or None
        :keyword algorithm: The encryption algorithm to use to protect the released key material.
        :paramtype algorithm: str or ~azure.keyvault.keys.KeyExportEncryptionAlgorithm or None
        :keyword nonce: A client-provided nonce for freshness.
        :paramtype nonce: str or None

        :return: The result of the key release.
        :rtype: ~azure.keyvault.keys.ReleaseKeyResult

        :raises ~azure.core.exceptions.HttpResponseError:
        """
        result = self._client.release(
            key_name=name,
            key_version=version or "",
            parameters=self._models.KeyReleaseParameters(
                target_attestation_token=target_attestation_token,
                nonce=nonce,
                enc=algorithm,
            ),
            **kwargs
        )
        return ReleaseKeyResult(result.value)

    @distributed_trace
    def get_random_bytes(self, count: int, **kwargs: Any) -> bytes:
        """Get the requested number of random bytes from a managed HSM.

        :param int count: The requested number of random bytes.

        :return: The random bytes.
        :rtype: bytes

        :raises ValueError or ~azure.core.exceptions.HttpResponseError:
            the former if less than one random byte is requested; the latter for other errors

        Example:
            .. literalinclude:: ../tests/test_key_client.py
                :start-after: [START get_random_bytes]
                :end-before: [END get_random_bytes]
                :language: python
                :caption: Get random bytes
                :dedent: 12
        """
        if count < 1:
            raise ValueError("At least one random byte must be requested")
        parameters = self._models.GetRandomBytesRequest(count=count)
        result = self._client.get_random_bytes(parameters=parameters, **kwargs)
        return result.value

    @distributed_trace
    def get_key_rotation_policy(self, key_name: str, **kwargs: Any) -> KeyRotationPolicy:
        """Get the rotation policy of a Key Vault key.

        :param str key_name: The name of the key.

        :return: The key rotation policy.
        :rtype: ~azure.keyvault.keys.KeyRotationPolicy

        :raises ~azure.core.exceptions.HttpResponseError:
        """
        policy = self._client.get_key_rotation_policy(key_name=key_name, **kwargs)
        return KeyRotationPolicy._from_generated(policy)

    @distributed_trace
    def rotate_key(self, name: str, **kwargs: Any) -> KeyVaultKey:
        """Rotate the key based on the key policy by generating a new version of the key.

        This operation requires the keys/rotate permission.

        :param str name: The name of the key to rotate.

        :return: The new version of the rotated key.
        :rtype: ~azure.keyvault.keys.KeyVaultKey

        :raises ~azure.core.exceptions.HttpResponseError:
        """
        bundle = self._client.rotate_key(key_name=name, **kwargs)
        return KeyVaultKey._from_key_bundle(bundle)

    @distributed_trace
    def update_key_rotation_policy(  # pylint: disable=unused-argument
        self,
        key_name: str,
        policy: KeyRotationPolicy,
        *,
        lifetime_actions: Optional[List[KeyRotationLifetimeAction]] = None,
        expires_in: Optional[str] = None,
        **kwargs: Any,
    ) -> KeyRotationPolicy:
        """Updates the rotation policy of a Key Vault key.

        This operation requires the keys/update permission.

        :param str key_name: The name of the key in the given vault.
        :param policy: The new rotation policy for the key.
        :type policy: ~azure.keyvault.keys.KeyRotationPolicy

        :keyword lifetime_actions: Actions that will be performed by Key Vault over the lifetime of a key. This will
            override the lifetime actions of the provided ``policy``.
        :paramtype lifetime_actions: List[~azure.keyvault.keys.KeyRotationLifetimeAction]
        :keyword str expires_in: The expiry time of the policy that will be applied on new key versions, defined as an
            ISO 8601 duration. For example: 90 days is "P90D", 3 months is "P3M", and 48 hours is "PT48H". See
            `Wikipedia <https://wikipedia.org/wiki/ISO_8601#Durations>`_ for more information on ISO 8601 durations.
            This will override the expiry time of the provided ``policy``.

        :return: The updated rotation policy.
        :rtype: ~azure.keyvault.keys.KeyRotationPolicy

        :raises ~azure.core.exceptions.HttpResponseError:
        """
        actions = lifetime_actions or policy.lifetime_actions
        if actions:
            actions = [
                self._models.LifetimeActions(
                    action=self._models.LifetimeActionsType(type=action.action),
                    trigger=self._models.LifetimeActionsTrigger(
                        time_after_create=action.time_after_create, time_before_expiry=action.time_before_expiry
                    ),
                )
                for action in actions
            ]

        attributes = self._models.KeyRotationPolicyAttributes(expiry_time=expires_in or policy.expires_in)
        new_policy = self._models.KeyRotationPolicy(lifetime_actions=actions or [], attributes=attributes)
        result = self._client.update_key_rotation_policy(key_name=key_name, key_rotation_policy=new_policy)
        return KeyRotationPolicy._from_generated(result)

    @distributed_trace
    def get_key_attestation(self, name: str, version: Optional[str] = None, **kwargs: Any) -> KeyVaultKey:
        """Get a key and its attestation blob.
        
        This method is applicable to any key stored in Azure Key Vault Managed HSM. This operation requires the keys/get
        permission.

        :param str name: The name of the key.
        :param version: (optional) A specific version of the key to get. If not specified, gets the latest version
            of the key.
        :type version: str or None

        :return: The key attestation.
        :rtype: ~azure.keyvault.keys.KeyAttestation

        :raises ~azure.core.exceptions.HttpResponseError:
        """
        bundle = self._client.get_key_attestation(key_name=name, key_version=version or "", **kwargs)
        return KeyVaultKey._from_key_bundle(bundle)

    def __enter__(self) -> "KeyClient":
        self._client.__enter__()
        return self
