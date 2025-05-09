#!/usr/bin/env python

# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
An example to show receiving events from an Event Hub with checkpoint store doing checkpoint by batch.
In the `receive_batch` method of `EventHubConsumerClient`:
If no partition id is specified, the checkpoint_store are used for load-balance and checkpoint.
If partition id is specified, the checkpoint_store can only be used for checkpoint without load balancing.
"""

import os
import logging
from azure.eventhub import EventHubConsumerClient
from azure.eventhub.extensions.checkpointstoreblob import BlobCheckpointStore
from azure.identity import DefaultAzureCredential

FULLY_QUALIFIED_NAMESPACE = os.environ["EVENT_HUB_HOSTNAME"]
EVENTHUB_NAME = os.environ["EVENT_HUB_NAME"]

storage_account_name = os.environ["AZURE_STORAGE_ACCOUNT"]
protocol = os.environ.get("PROTOCOL", "https")
suffix = os.environ.get("ACCOUNT_URL_SUFFIX", "core.windows.net")
BLOB_ACCOUNT_URL = f"{protocol}://{storage_account_name}.blob.{suffix}"
BLOB_CONTAINER_NAME = "your-blob-container-name"  # Please make sure the blob container resource exists.

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def on_event_batch(partition_context, event_batch):
    log.info("Partition {}, Received count: {}".format(partition_context.partition_id, len(event_batch)))
    # put your code here
    partition_context.update_checkpoint()


def receive_batch():
    checkpoint_store = BlobCheckpointStore(
        blob_account_url=BLOB_ACCOUNT_URL, container_name=BLOB_CONTAINER_NAME, credential=DefaultAzureCredential()
    )
    client = EventHubConsumerClient(
        fully_qualified_namespace=FULLY_QUALIFIED_NAMESPACE,
        eventhub_name=EVENTHUB_NAME,
        credential=DefaultAzureCredential(),
        consumer_group="$Default",
        checkpoint_store=checkpoint_store,
    )
    with client:
        client.receive_batch(
            on_event_batch=on_event_batch,
            max_batch_size=100,
            starting_position="-1",  # "-1" is from the beginning of the partition.
        )


if __name__ == "__main__":
    receive_batch()
