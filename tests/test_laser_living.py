"""Laser visuals and helper lifecycle without creating a desktop window."""
import io
import json
import unittest
from unittest.mock import Mock, patch

from server import laser_overlay


class LaserLivingTests(unittest.TestCase):
    def test_glow_has_soft_per_pixel_alpha_and_opaque_core(self):
        sprite = laser_overlay.glow_sprite('red')
        self.assertEqual(sprite.mode, 'RGBA')
        middle = sprite.width // 2
        self.assertEqual(sprite.getpixel((0, middle))[3], 0)
        self.assertGreater(sprite.getpixel((middle - 14, middle))[3], 0)
        self.assertEqual(sprite.getpixel((middle, middle))[3], 255)

    def test_selected_monitor_coordinates_keep_exact_pointer_center(self):
        rect = {'x': -1920, 'y': 100, 'width': 1920, 'height': 1080}
        self.assertEqual(laser_overlay.laser_geometry(.25, .5, rect, 64),
                         (-1472, 608, 64))
        self.assertEqual(laser_overlay.laser_geometry(2, -1, rect, 64),
                         (-32, 68, 64))

    def test_client_stop_requests_clean_exit_before_fallback(self):
        process = Mock()
        process.poll.return_value = None
        process.stdin = io.StringIO()
        client = laser_overlay.LaserOverlayClient()
        client.proc = process
        client.stop()
        self.assertEqual(json.loads(process.stdin.getvalue()), {'cmd': 'quit'})
        process.wait.assert_called_once()
        process.terminate.assert_not_called()
