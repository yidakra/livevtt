#!/usr/bin/env python3
"""Tests for caption_sender.py utility."""

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python" / "tools"))

import caption_sender


class TestSendCaption:
    """Tests for send_caption function."""

    def test_send_caption_success(self):
        """Test successful caption sending."""
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Caption sent"

        with mock.patch('caption_sender.requests.post', return_value=mock_response) as mock_post:
            result = caption_sender.send_caption(
                "localhost", 8086, "testStream", "Test caption"
            )
            assert result is True
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "http://localhost:8086/livevtt/captions" in call_args[0]
            assert call_args[1]['json']['text'] == "Test caption"
            assert call_args[1]['json']['streamname'] == "testStream"
        print("✓ test_send_caption_success passed")

    def test_send_caption_stream_not_found(self):
        """Test caption sending when stream not found."""
        mock_response = mock.MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Stream not found"

        with mock.patch('caption_sender.requests.post', return_value=mock_response):
            result = caption_sender.send_caption(
                "localhost", 8086, "nonexistent", "Test caption"
            )
            # 404 is considered successful API test
            assert result is True
        print("✓ test_send_caption_stream_not_found passed")

    def test_send_caption_server_error(self):
        """Test caption sending with server error."""
        mock_response = mock.MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"

        with mock.patch('caption_sender.requests.post', return_value=mock_response):
            result = caption_sender.send_caption(
                "localhost", 8086, "testStream", "Test caption"
            )
            assert result is False
        print("✓ test_send_caption_server_error passed")

    def test_send_caption_with_custom_language(self):
        """Test caption sending with custom language code."""
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Caption sent"

        with mock.patch('caption_sender.requests.post', return_value=mock_response) as mock_post:
            result = caption_sender.send_caption(
                "localhost", 8086, "testStream", "Test caption",
                language="spa", track_id=50
            )
            assert result is True
            call_args = mock_post.call_args
            assert call_args[1]['json']['lang'] == "spa"
            assert call_args[1]['json']['trackid'] == 50
        print("✓ test_send_caption_with_custom_language passed")

    def test_send_caption_with_authentication(self):
        """Test caption sending with authentication."""
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Caption sent"

        with mock.patch('caption_sender.requests.post', return_value=mock_response) as mock_post:
            result = caption_sender.send_caption(
                "localhost", 8086, "testStream", "Test caption",
                username="admin", password="secret"
            )
            assert result is True
            call_args = mock_post.call_args
            assert call_args[1]['auth'] == ("admin", "secret")
        print("✓ test_send_caption_with_authentication passed")

    def test_send_caption_connection_error(self):
        """Test caption sending with connection error."""
        with mock.patch('caption_sender.requests.post', side_effect=Exception("Connection refused")):
            result = caption_sender.send_caption(
                "localhost", 8086, "testStream", "Test caption"
            )
            assert result is False
        print("✓ test_send_caption_connection_error passed")

    def test_send_caption_payload_structure(self):
        """Test caption payload has correct structure."""
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Caption sent"

        with mock.patch('caption_sender.requests.post', return_value=mock_response) as mock_post:
            caption_sender.send_caption(
                "localhost", 8086, "myStream", "Caption text",
                language="rus", track_id=100
            )
            call_args = mock_post.call_args
            payload = call_args[1]['json']
            assert 'text' in payload
            assert 'lang' in payload
            assert 'trackid' in payload
            assert 'streamname' in payload
            assert payload['text'] == "Caption text"
            assert payload['lang'] == "rus"
            assert payload['trackid'] == 100
            assert payload['streamname'] == "myStream"
        print("✓ test_send_caption_payload_structure passed")


class TestMainFunction:
    """Tests for main function."""

    def test_main_with_single_caption(self):
        """Test main function with single caption."""
        test_args = [
            'caption_sender.py',
            '--stream', 'testStream',
            '--count', '1'
        ]

        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Success"

        with mock.patch('sys.argv', test_args):
            with mock.patch('caption_sender.requests.post', return_value=mock_response):
                result = caption_sender.main()
                assert result == 0
        print("✓ test_main_with_single_caption passed")

    def test_main_with_multiple_captions(self):
        """Test main function with multiple captions."""
        test_args = [
            'caption_sender.py',
            '--stream', 'testStream',
            '--count', '3'
        ]

        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Success"

        with mock.patch('sys.argv', test_args):
            with mock.patch('caption_sender.requests.post', return_value=mock_response) as mock_post:
                with mock.patch('caption_sender.time.sleep'):  # Skip actual sleep
                    result = caption_sender.main()
                    assert result == 0
                    assert mock_post.call_count == 3
        print("✓ test_main_with_multiple_captions passed")

    def test_main_with_custom_parameters(self):
        """Test main function with custom parameters."""
        test_args = [
            'caption_sender.py',
            '--stream', 'customStream',
            '--server', 'example.com',
            '--port', '9000',
            '--text', 'Custom caption',
            '--language', 'fra',
            '--track-id', '42'
        ]

        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Success"

        with mock.patch('sys.argv', test_args):
            with mock.patch('caption_sender.requests.post', return_value=mock_response) as mock_post:
                result = caption_sender.main()
                assert result == 0
                call_args = mock_post.call_args
                assert "example.com:9000" in call_args[0][0]
                assert call_args[1]['json']['lang'] == 'fra'
                assert call_args[1]['json']['trackid'] == 42
        print("✓ test_main_with_custom_parameters passed")

    def test_main_with_failures(self):
        """Test main function with some failures."""
        test_args = [
            'caption_sender.py',
            '--stream', 'testStream',
            '--count', '3'
        ]

        # Simulate some failures
        mock_responses = [
            mock.MagicMock(status_code=200, text="Success"),
            mock.MagicMock(status_code=500, text="Error"),
            mock.MagicMock(status_code=200, text="Success")
        ]

        with mock.patch('sys.argv', test_args):
            with mock.patch('caption_sender.requests.post', side_effect=mock_responses):
                with mock.patch('caption_sender.time.sleep'):
                    result = caption_sender.main()
                    # Should return 1 because not all captions succeeded
                    assert result == 1
        print("✓ test_main_with_failures passed")


def run_all_tests():
    """
    Execute all test methods defined on the test classes and report aggregated results.
    
    Discovers methods whose names start with "test_" on each test class, instantiates the class for each method, runs the method, prints per-test failures and a final summary to stdout, and counts passed and failed tests.
    
    Returns:
        bool: `True` if all tests passed, `False` otherwise.
    """
    test_classes = [
        TestSendCaption,
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