# --------------------------------------------------------------------------
#
# Copyright (c) Microsoft Corporation. All rights reserved.
#
# The MIT License (MIT)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the ""Software""), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED *AS IS*, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#
# --------------------------------------------------------------------------
from typing import TypeVar
from azure.core.exceptions import TooManyRedirectsError
from azure.core.pipeline import PipelineResponse, PipelineRequest
from azure.core.pipeline.transport import (
    AsyncHttpResponse as LegacyAsyncHttpResponse,
    HttpRequest as LegacyHttpRequest,
)
from azure.core.rest import AsyncHttpResponse, HttpRequest
from . import AsyncHTTPPolicy
from ._redirect import RedirectPolicyBase, domain_changed
from ._utils import get_domain

AsyncHTTPResponseType = TypeVar("AsyncHTTPResponseType", AsyncHttpResponse, LegacyAsyncHttpResponse)
HTTPRequestType = TypeVar("HTTPRequestType", HttpRequest, LegacyHttpRequest)


class AsyncRedirectPolicy(RedirectPolicyBase, AsyncHTTPPolicy[HTTPRequestType, AsyncHTTPResponseType]):
    """An async redirect policy.

    An async redirect policy in the pipeline can be configured directly or per operation.

    :keyword bool permit_redirects: Whether the client allows redirects. Defaults to True.
    :keyword int redirect_max: The maximum allowed redirects. Defaults to 30.

    .. admonition:: Example:

        .. literalinclude:: ../samples/test_example_async.py
            :start-after: [START async_redirect_policy]
            :end-before: [END async_redirect_policy]
            :language: python
            :dedent: 4
            :caption: Configuring an async redirect policy.
    """

    async def send(
        self, request: PipelineRequest[HTTPRequestType]
    ) -> PipelineResponse[HTTPRequestType, AsyncHTTPResponseType]:
        """Sends the PipelineRequest object to the next policy.
        Uses redirect settings to send the request to redirect endpoint if necessary.

        :param request: The PipelineRequest object
        :type request: ~azure.core.pipeline.PipelineRequest
        :return: the PipelineResponse.
        :rtype: ~azure.core.pipeline.PipelineResponse
        :raises ~azure.core.exceptions.TooManyRedirectsError: if maximum redirects exceeded.
        """
        redirects_remaining = True
        redirect_settings = self.configure_redirects(request.context.options)
        original_domain = get_domain(request.http_request.url) if redirect_settings["allow"] else None
        while redirects_remaining:
            response = await self.next.send(request)
            redirect_location = self.get_redirect_location(response)
            if redirect_location and redirect_settings["allow"]:
                redirects_remaining = self.increment(redirect_settings, response, redirect_location)
                request.http_request = response.http_request
                if domain_changed(original_domain, request.http_request.url):
                    # "insecure_domain_change" is used to indicate that a redirect
                    # has occurred to a different domain. This tells the SensitiveHeaderCleanupPolicy
                    # to clean up sensitive headers. We need to remove it before sending the request
                    # to the transport layer.
                    request.context.options["insecure_domain_change"] = True
                continue
            return response

        raise TooManyRedirectsError(redirect_settings["history"])
