#!/usr/bin/env python3
"""Tests for stream_checker.py utility."""

import sys
from pathlib import Path
from unittest import mock
import json

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python" / "tools"))

import stream_checker


class TestBasicStreamStatus:
    """Tests for basic stream status checking."""

    def test_check_basic_stream_status_success(self):
        """Test basic stream status check with success response."""
        mock_response = mock.MagicMock()
        mock_response.status_code = 200

        with mock.patch('stream_checker.requests.post', return_value=mock_response):
            result = stream_checker.check_basic_stream_status("localhost")
            assert result is True
        print("✓ test_check_basic_stream_status_success passed")

    def test_check_basic_stream_status_no_streams(self):
        """Test basic stream status check with no active streams."""
        mock_response = mock.MagicMock()
        mock_response.status_code = 404

        with mock.patch('stream_checker.requests.post', return_value=mock_response):
            result = stream_checker.check_basic_stream_status("localhost")
            assert result is True  # Still successful check
        print("✓ test_check_basic_stream_status_no_streams passed")

    def test_check_basic_stream_status_unexpected_code(self):
        """Test basic stream status check with unexpected status code."""
        mock_response = mock.MagicMock()
        mock_response.status_code = 500

        with mock.patch('stream_checker.requests.post', return_value=mock_response):
            result = stream_checker.check_basic_stream_status("localhost")
            assert result is False
        print("✓ test_check_basic_stream_status_unexpected_code passed")

    def test_check_basic_stream_status_connection_error(self):
        """Test basic stream status check with connection error."""
        with mock.patch('stream_checker.requests.post', side_effect=Exception("Connection refused")):
            result = stream_checker.check_basic_stream_status("localhost")
            assert result is False
        print("✓ test_check_basic_stream_status_connection_error passed")


class TestWowzaStreams:
    """Tests for Wowza stream checking via REST API."""

    def test_check_wowza_streams_with_active_streams(self):
        """Test checking Wowza streams with active streams found."""
        # Mock applications response
        apps_response = mock.MagicMock()
        apps_response.status_code = 200
        apps_response.json.return_value = {
            'applications': [
                {'name': 'live'}
            ]
        }

        # Mock instances response
        instances_response = mock.MagicMock()
        instances_response.status_code = 200
        instances_response.json.return_value = {
            'instances': [
                {'name': '_definst_'}
            ]
        }

        # Mock streams response
        streams_response = mock.MagicMock()
        streams_response.status_code = 200
        streams_response.json.return_value = {
            'incomingStreams': [
                {'name': 'testStream'},
                {'name': 'liveShow'}
            ]
        }

        responses = [apps_response, instances_response, streams_response]

        with mock.patch('stream_checker.requests.get', side_effect=responses):
            result = stream_checker.check_wowza_streams("localhost", 8088)
            assert result is True
        print("✓ test_check_wowza_streams_with_active_streams passed")

    def test_check_wowza_streams_no_active_streams(self):
        """Test checking Wowza streams with no active streams."""
        apps_response = mock.MagicMock()
        apps_response.status_code = 200
        apps_response.json.return_value = {
            'applications': []
        }

        with mock.patch('stream_checker.requests.get', return_value=apps_response):
            result = stream_checker.check_wowza_streams("localhost", 8088)
            assert result is True  # Still a successful check
        print("✓ test_check_wowza_streams_no_active_streams passed")

    def test_check_wowza_streams_api_not_accessible(self):
        """Test when Wowza REST API is not accessible."""
        apps_response = mock.MagicMock()
        apps_response.status_code = 404

        # Should fallback to basic check
        basic_response = mock.MagicMock()
        basic_response.status_code = 200

        with mock.patch('stream_checker.requests.get', return_value=apps_response):
            with mock.patch('stream_checker.requests.post', return_value=basic_response):
                result = stream_checker.check_wowza_streams("localhost", 8088)
                assert result is True
        print("✓ test_check_wowza_streams_api_not_accessible passed")

    def test_check_wowza_streams_invalid_json(self):
        """Test when Wowza REST API returns invalid JSON."""
        apps_response = mock.MagicMock()
        apps_response.status_code = 200
        apps_response.json.side_effect = json.JSONDecodeError("Invalid", "", 0)

        # Should fallback to basic check
        basic_response = mock.MagicMock()
        basic_response.status_code = 200

        with mock.patch('stream_checker.requests.get', return_value=apps_response):
            with mock.patch('stream_checker.requests.post', return_value=basic_response):
                result = stream_checker.check_wowza_streams("localhost", 8088)
                assert result is True
        print("✓ test_check_wowza_streams_invalid_json passed")

    def test_check_wowza_streams_connection_error(self):
        """Test when connection to Wowza fails."""
        import requests

        with mock.patch('stream_checker.requests.get',
                       side_effect=requests.exceptions.RequestException("Connection failed")):
            result = stream_checker.check_wowza_streams("localhost", 8088)
            assert result is False
        print("✓ test_check_wowza_streams_connection_error passed")

    def test_check_wowza_streams_multiple_apps_and_streams(self):
        """Test checking multiple applications with multiple streams."""
        apps_response = mock.MagicMock()
        apps_response.status_code = 200
        apps_response.json.return_value = {
            'applications': [
                {'name': 'live'},
                {'name': 'vod'}
            ]
        }

        instances_response = mock.MagicMock()
        instances_response.status_code = 200
        instances_response.json.return_value = {
            'instances': [
                {'name': '_definst_'}
            ]
        }

        streams_response1 = mock.MagicMock()
        streams_response1.status_code = 200
        streams_response1.json.return_value = {
            'incomingStreams': [
                {'name': 'stream1'}
            ]
        }

        streams_response2 = mock.MagicMock()
        streams_response2.status_code = 200
        streams_response2.json.return_value = {
            'incomingStreams': [
                {'name': 'stream2'}
            ]
        }

        responses = [
            apps_response,
            instances_response,
            streams_response1,
            instances_response,
            streams_response2
        ]

        with mock.patch('stream_checker.requests.get', side_effect=responses):
            result = stream_checker.check_wowza_streams("localhost", 8088)
            assert result is True
        print("✓ test_check_wowza_streams_multiple_apps_and_streams passed")


class TestMainFunction:
    """Tests for main function."""

    def test_main_default_arguments(self):
        """Test main function with default arguments."""
        test_args = ['stream_checker.py']

        apps_response = mock.MagicMock()
        apps_response.status_code = 200
        apps_response.json.return_value = {'applications': []}

        with mock.patch('sys.argv', test_args):
            with mock.patch('stream_checker.requests.get', return_value=apps_response):
                result = stream_checker.main()
                assert result == 0
        print("✓ test_main_default_arguments passed")

    def test_main_custom_host_and_port(self):
        """Test main function with custom host and port."""
        test_args = [
            'stream_checker.py',
            '--host', 'example.com',
            '--port', '9090'
        ]

        apps_response = mock.MagicMock()
        apps_response.status_code = 200
        apps_response.json.return_value = {'applications': []}

        with mock.patch('sys.argv', test_args):
            with mock.patch('stream_checker.requests.get', return_value=apps_response) as mock_get:
                result = stream_checker.main()
                assert result == 0
                # Verify correct host and port were used
                call_url = mock_get.call_args[0][0]
                assert 'example.com:9090' in call_url
        print("✓ test_main_custom_host_and_port passed")

    def test_main_with_failure(self):
        """Test main function when check fails."""
        test_args = ['stream_checker.py']

        import requests

        with mock.patch('sys.argv', test_args):
            with mock.patch('stream_checker.requests.get',
                          side_effect=requests.exceptions.RequestException("Error")):
                result = stream_checker.main()
                assert result == 1
        print("✓ test_main_with_failure passed")


def run_all_tests():
    """Run all tests."""
    test_classes = [
        TestBasicStreamStatus,
        TestWowzaStreams,
        TestMainFunction
    ]

    passed = 0
    failed = 0

    for test_class in test_classes:
        print(f"\n{test_class.__name__}:")
        print("-" * 60)

        test_methods = [
            method for method in dir(test_class)
            if method.startswith("test_")
        ]

        for method_name in test_methods:
            try:
                instance = test_class()
                method = getattr(instance, method_name)
                method()
                passed += 1
            except Exception as e:
                print(f"✗ {method_name} failed: {e}")
                import traceback
                traceback.print_exc()
                failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
