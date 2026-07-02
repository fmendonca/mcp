"""Tests for the Prometheus /metrics endpoint and request instrumentation."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestMetricsEndpoint:
    """Test suite for the /metrics endpoint."""

    def test_metrics_endpoint_public(self, client):
        """Test that /metrics is reachable without auth, like /healthz."""
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_exposition_format(self, client):
        """Test that /metrics returns Prometheus text exposition format."""
        response = client.get("/metrics")
        assert "text/plain" in response.headers["content-type"]
        assert b"mcp_openshift_http_requests_total" in response.content

    def test_metrics_records_request_count(self, client):
        """Test that hitting an endpoint increments its request counter."""
        client.get("/healthz")
        client.get("/healthz")

        response = client.get("/metrics")
        body = response.text
        assert 'path="/healthz"' in body
        assert 'method="GET"' in body

    def test_metrics_collapses_path_params_into_template(self, client):
        """Test that different path param values share one label series
        instead of exploding cardinality (e.g. /namespaces/{namespace}, not
        one series per actual namespace name).
        """
        client.get("/api/v1/namespaces/ns-one")
        client.get("/api/v1/namespaces/ns-two")

        response = client.get("/metrics")
        body = response.text
        assert 'path="/api/v1/namespaces/{namespace}"' in body
        assert "ns-one" not in body
        assert "ns-two" not in body

    def test_metrics_records_duration_histogram(self, client):
        """Test that request duration is recorded in a histogram."""
        client.get("/healthz")

        response = client.get("/metrics")
        assert b"mcp_openshift_http_request_duration_seconds_bucket" in response.content
