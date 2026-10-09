"""Camera sources returning OpenCV-compatible BGR frames."""
import sys
from pathlib import Path


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


def camera_candidates(preferred_index):
    """CSI cameras first; USB entries in libcamera are not Pi cameras."""
    try:
        from picamera2 import Picamera2
        for index, info in enumerate(Picamera2.global_camera_info()):
            identity = info.get('Id', '')
            if identity and '/usb' not in identity.lower():
                yield 'picamera2', index, identity, f"Pi Camera ({info.get('Model', index)})"
    except (ImportError, RuntimeError, OSError) as exc:
        print(f'Pi Camera discovery: {exc}; looking for USB cameras', flush=True)

    if sys.platform.startswith('linux'):
        # Scan actual USB devices, excluding the Pi's codec/ISP video nodes.
        nodes = sorted(Path('/sys/class/video4linux').glob('video*'),
                       key=lambda p: int(p.name[5:]))
        nodes.sort(key=lambda p: int(p.name[5:]) != preferred_index)
        for node in nodes:
            device = (node / 'device').resolve()
            if '/usb' in str(device).lower():
                path = '/dev/' + node.name
                yield 'opencv', path, str(device), f'USB camera ({path})'
    else:
        for index in dict.fromkeys([preferred_index, *range(10)]):
            yield 'opencv', index, str(index), f'Webcam ({index})'


class SelectedCamera:
    def __init__(self, capture, frame, source_id, label):
        self.capture = capture
        self.first_frame = frame
        self.source_id = source_id
        self.label = label

    def read(self):
        if self.first_frame is not None:
            frame, self.first_frame = self.first_frame, None
            return True, frame
        return self.capture.read()

    def release(self):
        self.capture.release()


def open_auto_camera(index, width, height):
    errors = []
    for backend, number, identity, label in camera_candidates(index):
        cap = None
        try:
            cap = open_camera(backend, number, width, height)
            ok, frame = cap.read()
            if not ok or frame is None or frame.size == 0:
                raise RuntimeError('no frame received')
            source_id = f'{backend}:{identity}:{frame.shape[1]}x{frame.shape[0]}'
            print(f'Using {label}', flush=True)
            return SelectedCamera(cap, frame, source_id, label)
        except Exception as exc:
            errors.append(f'{label}: {exc}')
            print(f'{label} unavailable: {exc}', flush=True)
            if cap is not None:
                try: cap.release()
                except Exception: pass
    detail = '; '.join(errors) if errors else 'no Pi Camera or USB webcam detected'
    raise RuntimeError(detail)


def open_camera(backend, index, width, height):
    if backend == 'auto':
        return open_auto_camera(index, width, height)
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
