"""Camera integration tests with simulated hardware; run python3 -m unittest -v."""
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import camera
import app


V2_MODES = [
    {'size': (640, 480), 'crop_limits': (1000, 752, 1280, 960), 'bit_depth': 10},
    {'size': (1920, 1080), 'crop_limits': (680, 692, 1920, 1080), 'bit_depth': 10},
    {'size': (1640, 1232), 'crop_limits': (0, 0, 3280, 2464), 'bit_depth': 10},
    {'size': (3280, 2464), 'crop_limits': (0, 0, 3280, 2464), 'bit_depth': 10},
]


class CameraTests(unittest.TestCase):
    def test_auto_prefers_pi_over_connected_usb(self):
        frame = np.zeros((48, 64, 3), dtype=np.uint8)
        pi = Mock()
        pi.read.return_value = (True, frame)
        candidates = [('picamera2', 1, 'imx219', 'Pi Camera'),
                      ('opencv', '/dev/video0', 'usb', 'USB camera')]
        with patch.object(camera, 'camera_candidates', return_value=candidates), \
             patch.object(camera, 'open_camera', return_value=pi) as opener:
            selected = camera.open_auto_camera(0, 64, 48)
            self.assertTrue(selected.read()[0])
            self.assertIn('imx219', selected.source_id)
            opener.assert_called_once_with('picamera2', 1, 64, 48)
            pi.read.assert_called_once()
            selected.release()
        pi.release.assert_called_once()

    def test_auto_skips_failed_pi_and_usb_metadata_node(self):
        bad = Mock()
        bad.read.return_value = (False, None)
        usb = Mock()
        usb.read.return_value = (True, np.zeros((48, 64, 3), dtype=np.uint8))
        candidates = [('picamera2', 0, 'imx219', 'Pi Camera'),
                      ('opencv', '/dev/video0', 'usb0', 'USB camera 0'),
                      ('opencv', '/dev/video1', 'usb1', 'USB camera 1')]
        with patch.object(camera, 'camera_candidates', return_value=candidates), \
             patch.object(camera, 'open_camera', side_effect=[RuntimeError('not connected'), bad, usb]):
            selected = camera.open_auto_camera(0, 64, 48)
            self.assertEqual(selected.label, 'USB camera 1')
        bad.release.assert_called_once()

    def test_auto_no_cameras_reports_retriable_error(self):
        with patch.object(camera, 'camera_candidates', return_value=[]):
            with self.assertRaisesRegex(RuntimeError, 'no Pi Camera or USB webcam detected'):
                camera.open_auto_camera(0, 64, 48)

    def test_discovery_does_not_mistake_libcamera_usb_for_pi(self):
        api = Mock()
        api.global_camera_info.return_value = [
            {'Id': '/base/usb@1/camera', 'Model': 'Webcam', 'Num': 7},
            {'Id': '/base/i2c/imx219@10', 'Model': 'imx219', 'Num': 4},
        ]
        with patch.dict(sys.modules, picamera2=SimpleNamespace(Picamera2=api)), \
             patch.object(camera.sys, 'platform', 'linux'), \
             patch.object(camera.Path, 'glob', return_value=[]):
            candidates = list(camera.camera_candidates(0))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][:2], ('picamera2', 1))

    def test_auto_switch_invalidates_calibration(self):
        event = threading.Event()
        cap = Mock(source_id='opencv:usb:64x48', label='USB camera')
        cap.read.return_value = (True, np.zeros((48, 64, 3), dtype=np.uint8))
        cfg = dict(app.config, camera_source='picamera2:imx219:64x48',
                   ruler_points=[[0, 0], [100, 0]], roi=[0, 0, 10, 10])
        with patch.object(app, 'stop', event), \
             patch.object(event, 'wait', side_effect=lambda _: event.set()), \
             patch.object(app, 'open_camera', return_value=cap), \
             patch.object(app, 'config', cfg), patch.object(app, 'state', {}):
            app.camera_loop(64, 48, 'auto')
            self.assertIsNone(cfg['ruler_points'])
            self.assertIsNone(cfg['roi'])
            self.assertEqual(cfg['camera_source'], cap.source_id)
            self.assertTrue(app.state['status'].startswith('USB camera |'))

    def test_missing_picamera_still_discovers_usb_and_skips_isp(self):
        usb = Mock(name='usbnode')
        usb.name = 'video2'
        isp = Mock(name='ispnode')
        isp.name = 'video10'
        # Path division resolves each node's sysfs device link.
        usb = unittest.mock.MagicMock(wraps=usb)
        usb.name = 'video2'
        usb.__truediv__.return_value.resolve.return_value = '/sys/devices/platform/usb1/1-1'
        isp = unittest.mock.MagicMock(wraps=isp)
        isp.name = 'video10'
        isp.__truediv__.return_value.resolve.return_value = '/sys/devices/platform/bcm2835-codec'
        with patch.dict(sys.modules, picamera2=None), \
             patch.object(camera.sys, 'platform', 'linux'), \
             patch.object(camera.Path, 'glob', return_value=[isp, usb]):
            candidates = list(camera.camera_candidates(0))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][:2], ('opencv', '/dev/video2'))

    def test_wide_view_avoids_cropped_modes_even_for_small_output(self):
        for size in [(640, 480), (1280, 720), (1280, 960)]:
            mode = camera.widest_sensor_mode(V2_MODES, *size)
            self.assertEqual(mode['size'], (1640, 1232))
            self.assertEqual(mode['crop_limits'], (0, 0, 3280, 2464))

    def test_wide_view_preserves_detail_for_larger_output(self):
        self.assertEqual(camera.widest_sensor_mode(V2_MODES, 1920, 1440)['size'], (3280, 2464))
        self.assertIsNone(camera.widest_sensor_mode([], 640, 480))

    def test_pi_frames_keep_opencv_color_order_and_release(self):
        frame = np.array([[[10, 20, 30]]], dtype=np.uint8)
        device = Mock()
        device.sensor_modes = V2_MODES
        device.capture_array.return_value = frame
        constructor = Mock(return_value=device)
        with patch.dict(sys.modules, picamera2=SimpleNamespace(Picamera2=constructor)):
            cap = camera.open_camera('picamera2', 0, 640, 480)
            ok, captured = cap.read()
            self.assertTrue(ok)
            self.assertIs(captured, frame)
            self.assertEqual(device.create_video_configuration.call_args.kwargs['main'],
                             {'size': (640, 480), 'format': 'RGB888'})
            self.assertEqual(device.create_video_configuration.call_args.kwargs['sensor'],
                             {'output_size': (1640, 1232), 'bit_depth': 10})
            self.assertEqual(device.create_video_configuration.call_args.kwargs['controls'],
                             {'ScalerCrop': (0, 0, 3280, 2464)})
            cap.release()
            cap.release()
        constructor.assert_called_once_with(camera_num=0)
        device.close.assert_called_once()

    def test_pi_start_failure_releases_camera(self):
        device = Mock()
        device.sensor_modes = V2_MODES
        device.start.side_effect = RuntimeError('camera busy')
        with patch.dict(sys.modules, picamera2=SimpleNamespace(Picamera2=Mock(return_value=device))):
            with self.assertRaisesRegex(RuntimeError, 'camera busy'):
                camera.open_camera('picamera2', 0, 640, 480)
        device.close.assert_called_once()

    def test_missing_picamera2_has_install_instruction(self):
        with patch.dict(sys.modules, picamera2=None):
            with self.assertRaisesRegex(RuntimeError, 'sudo apt install python3-picamera2'):
                camera.open_camera('picamera2', 0, 640, 480)

    def test_usb_does_not_need_picamera2(self):
        with patch.dict(sys.modules, picamera2=None), patch.object(app.cv2, 'VideoCapture') as capture:
            cap = camera.open_camera('opencv', 1, 640, 480)
            self.assertIs(cap, capture.return_value)
            self.assertEqual(capture.call_args.args[0], 1)

    def test_failed_capture_clears_stale_measurements_and_retries(self):
        event = threading.Event()
        bad = Mock()
        bad.read.side_effect = RuntimeError('disconnected')
        good = Mock()
        frame = np.zeros((48, 64, 3), dtype=np.uint8)
        good.read.return_value = (True, frame)
        waits = []
        def wait(seconds):
            waits.append(seconds)
            if seconds == 2:
                self.assertIsNone(app.state['jpeg'])
                self.assertEqual(app.state['results'], [])
                self.assertIn('disconnected', app.state['status'])
            else:
                event.set()
        fresh = dict(app.config, ruler_points=None, roi=None)
        with patch.object(app, 'stop', event), patch.object(event, 'wait', side_effect=wait), \
             patch.object(app, 'open_camera', side_effect=[bad, good]), \
             patch.object(app, 'config', fresh), \
             patch.object(app, 'state', {'jpeg': b'stale', 'results': [{'id': 1}]}):
            app.camera_loop(64, 48, 'picamera2')
            self.assertTrue(app.state['jpeg'].startswith(b'\xff\xd8'))
            self.assertEqual((app.state['width'], app.state['height']), (64, 48))
        self.assertEqual(waits, [2, .08])
        bad.release.assert_called_once()
        good.release.assert_called_once()

    def test_open_failure_reports_status_without_killing_worker(self):
        event = threading.Event()
        with patch.object(app, 'stop', event), \
             patch.object(event, 'wait', side_effect=lambda _: event.set()), \
             patch.object(app, 'open_camera', side_effect=RuntimeError('No cameras found')), \
             patch.object(app, 'state', {'jpeg': b'stale', 'results': []}):
            app.camera_loop(640, 480, 'picamera2')
            self.assertIn('No cameras found', app.state['status'])
            self.assertIsNone(app.state['jpeg'])


if __name__ == '__main__':
    unittest.main()
