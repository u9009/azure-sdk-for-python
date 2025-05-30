# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""
FILE: sample_metrics_query_async.py
DESCRIPTION:
    This sample demonstrates authenticating the MetricsQueryClient and retrieving the "Ingress"
    metric along with the "Average" aggregation type. The query will execute over a timespan
    of 2 hours with a granularity of 15 minutes.
USAGE:
    python sample_metrics_query_async.py
    Set the environment variables with your own values before running the sample:
    1) METRICS_RESOURCE_URI - The resource URI of the resource for which the metrics are being queried.

    This example uses DefaultAzureCredential, which requests a token from Azure Active Directory.
    For more information on DefaultAzureCredential, see https://learn.microsoft.com/python/api/overview/azure/identity-readme?view=azure-python#defaultazurecredential.

    In this example, a Storage account resource URI is taken.
"""
import asyncio

# [START send_metrics_query_async]
from datetime import timedelta
import os

from azure.core.exceptions import HttpResponseError
from azure.identity.aio import DefaultAzureCredential
from azure.monitor.query.aio import MetricsQueryClient
from azure.monitor.query import MetricAggregationType


async def query_metrics():
    credential = DefaultAzureCredential()
    client = MetricsQueryClient(credential)

    metrics_uri = os.environ["METRICS_RESOURCE_URI"]
    async with client:
        try:
            response = await client.query_resource(
                metrics_uri,
                metric_names=["Ingress"],
                timespan=timedelta(hours=2),
                granularity=timedelta(minutes=15),
                aggregations=[MetricAggregationType.AVERAGE],
            )

            for metric in response.metrics:
                print(metric.name)
                for time_series_element in metric.timeseries:
                    for metric_value in time_series_element.data:
                        print(metric_value.timestamp)
        except HttpResponseError as err:
            print("something fatal happened")
            print(err)
    await credential.close()


# [END send_metrics_query_async]

if __name__ == "__main__":
    asyncio.run(query_metrics())
