import sys
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'vendor'))
import cv2
for i in range(2):
    cap=cv2.VideoCapture(i,cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT,1080)
    ok=False
    for _ in range(12):
        ok,frame=cap.read()
        if ok: break
    print(i,cap.isOpened(),frame.shape if ok else 'no frame',flush=True)
    if ok: cv2.imwrite(str(root/f'camera-{i}.jpg'),frame)
    cap.release()
