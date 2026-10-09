"""Camera sources returning OpenCV-compatible BGR frames."""
import sys


def widest_sensor_mode(modes, width, height):
    """Prefer full coverage, then the smallest mode sufficient for the output."""
    if not modes:
        return None
    largest_crop = max(m['crop_limits'][2] * m['crop_limits'][3] for m in modes)
    wide = [m for m in modes
            if m['crop_limits'][2] * m['crop_limits'][3] == largest_crop]
    sufficient = [m for m in wide if m['size'][0] >= width and m['size'][1] >= height]
    if sufficient:
        return min(sufficient, key=lambda m: (m['size'][0] * m['size'][1], -m['bit_depth']))
    return max(wide, key=lambda m: (m['size'][0] * m['size'][1], m['bit_depth']))


class PiCamera:
    def __init__(self, index, width, height):
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise RuntimeError(
                'Pi Camera requires Picamera2. On Raspberry Pi OS run: '
                'sudo apt install python3-picamera2'
            ) from exc
        self.camera = None
        try:
            self.camera = Picamera2(camera_num=index)
            mode = widest_sensor_mode(self.camera.sensor_modes, width, height)
            options = {}
            if mode is not None:
                options['sensor'] = {'output_size': mode['size'], 'bit_depth': mode['bit_depth']}
                options['controls'] = {'ScalerCrop': mode['crop_limits']}
                print(f"Pi Camera: sensor {mode['size']}, full-view crop {mode['crop_limits']}, "
                      f"output {width}x{height}", flush=True)
            # Picamera2 RGB888 arrays have B,G,R byte order, as OpenCV expects.
            configuration = self.camera.create_video_configuration(
                main={'size': (width, height), 'format': 'RGB888'},
                buffer_count=4,
                **options,
            )
            self.camera.configure(configuration)
            self.camera.start()
        except Exception:
            self.release()
            raise

    def read(self):
        frame = self.camera.capture_array('main')
        return frame is not None and frame.size > 0, frame

    def release(self):
        camera, self.camera = self.camera, None
        if camera is not None:
            camera.close()


def open_camera(backend, index, width, height):
    if backend == 'picamera2':
        return PiCamera(index, width, height)
    if backend != 'opencv':
        raise ValueError(f'Unknown camera backend: {backend}')
    import cv2
    api = (cv2.CAP_DSHOW if sys.platform == 'win32' else
           cv2.CAP_V4L2 if sys.platform.startswith('linux') else cv2.CAP_ANY)
    cap = cv2.VideoCapture(index, api)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap
