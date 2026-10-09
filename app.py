import sys, json, time, threading, argparse
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
ROOT=Path(__file__).resolve().parent
if sys.platform == 'win32':
    sys.path.insert(0,str(ROOT/'vendor'))
import cv2
import numpy as np
from vision import detect, size_label, Stabilizer
from ruler import RulerTracker
from camera import open_camera

config={'camera':1,'card_width':32.,'card_height':24.,'corners':None,'threshold':32, 'scale_mode':'ruler','ruler_points':[[795,554],[1397,532]],'ruler_mm':101.6,'roi':[790,255,630,280], 'follow_ruler':True,'auto_area':True}
settings=ROOT/'calibration.json'
if settings.exists():
    config.update(json.loads(settings.read_text()))
lock=threading.Lock()
state={'jpeg':None,'results':[],'status':'Starting camera'}
stop=threading.Event()

def order(points):
    p=np.array(points,np.float32)
    s=p.sum(axis=1); d=np.diff(p,axis=1).ravel()
    return np.array([p[np.argmin(s)],p[np.argmin(d)],p[np.argmax(s)],p[np.argmax(d)]],np.float32)

def analyze(frame,cfg):
    out=frame.copy(); gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    auto=False
    if cfg.get('scale_mode')=='ruler':
        marks=cfg.get('ruler_points')
        if marks is None: return out,[], 'Click two ruler marks and enter their distance to calibrate'
        a,b=np.array(marks,np.float32)
        distance=float(np.linalg.norm(b-a))
        if distance<20 or cfg['ruler_mm']<=0: return out,[], 'Calibration span is too short'
        scale=cfg['ruler_mm']/distance
        transform=np.array([[scale,0,0],[0,scale,0],[0,0,1]],np.float32)
        p=np.zeros((4,2),np.float32)
        cv2.line(out,tuple(a.astype(int)),tuple(b.astype(int)),(50,230,120),3)
        cv2.putText(out,f"Ruler span {cfg['ruler_mm']:g} mm",tuple(a.astype(int)-[0,15]),cv2.FONT_HERSHEY_SIMPLEX,.65,(50,230,120),2)
        status='Ruler calibrated | keep camera fixed and ruler beside parts'
    else:
        corners=cfg['corners']
        if corners is None:
            mask=cv2.inRange(gray,0,105)
            contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            candidates=[]
            for c in contours:
                area=cv2.contourArea(c); rect=cv2.minAreaRect(c); a,b=rect[1]
                if min(a,b)<35 or not 2500<area<gray.size*.08: continue
                if 1.15<max(a,b)/min(a,b)<1.65 and area/(a*b)>.75:
                    candidates.append((area,cv2.boxPoints(rect)))
            if candidates: corners=order(max(candidates,key=lambda x:x[0])[1]); auto=True
        if corners is None: return out,[], 'Scale missing: calibrate a ruler span or SD rectangle'
        p=order(corners); w,h=cfg['card_width'],cfg['card_height']
        if np.linalg.norm(p[1]-p[0])<np.linalg.norm(p[3]-p[0]): w,h=h,w
        transform=cv2.getPerspectiveTransform(p,np.array([[0,0],[w,0],[w,h],[0,h]],np.float32))
        cv2.polylines(out,[p.astype(np.int32)],True,(0,220,100),2)
        status='SD scale '+('automatic' if auto else 'manual')
    results=detect(gray,transform,p,cfg,frame)
    roi=cfg.get('roi')
    if roi:
        rx,ry,rw,rh=roi
        results=[item for item in results if rx<=item['box'][0] and ry<=item['box'][1] and item['box'][0]+item['box'][2]<=rx+rw and item['box'][1]+item['box'][3]<=ry+rh]
        cv2.rectangle(out,(rx,ry),(rx+rw,ry+rh),(180,150,70),1)
    for i,item in enumerate(results): item.update(id=i+1,size=size_label(item))
    return out,results,status

def annotate(out,results):
    for item in results:
        x,y,w,h=item['box']
        cv2.rectangle(out,(x,y),(x+w,y+h),(40,180,255),2)
        cv2.putText(out,f"{item['id']}: {item['size']}",(max(0,x-20),max(22,y-10)),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,90,240),2)
    return out

def camera_loop(width=1920,height=1080,backend='opencv'):
    cap=None; current=None; tracker=Stabilizer(); previous_cfg=None; ruler=RulerTracker(ROOT)
    try:
        while not stop.is_set():
            with lock: cfg=dict(config)
            try:
                if cap is None or current!=cfg['camera']:
                    if cap is not None:
                        cap.release(); cap=None
                    cap=open_camera(backend,cfg['camera'],width,height)
                    current=cfg['camera']
                    tracker=Stabilizer(); previous_cfg=None; ruler=RulerTracker(ROOT)
                ok,frame=cap.read()
                if not ok: raise RuntimeError('No frame received; check the camera connection and index')
            except Exception as e:
                message=f'Camera unavailable ({backend}): {e}'
                with lock: state.update(jpeg=None,raw=None,results=[],status=message)
                print(message,file=sys.stderr,flush=True)
                if cap is not None:
                    try: cap.release()
                    except Exception: pass
                    cap=None
                stop.wait(2)
                continue
            try:
                if cfg!=previous_cfg: tracker=Stabilizer(); previous_cfg=cfg
                effective=ruler.follow(frame,cfg)
                out,results,status=analyze(frame,effective)
                results=tracker.update(results)
                annotate(out,results)
                _,raw=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,95])
                _,jpg=cv2.imencode('.jpg',out,[cv2.IMWRITE_JPEG_QUALITY,85])
                with lock: state.update(jpeg=jpg.tobytes(),raw=raw.tobytes(),results=results,status=status,width=frame.shape[1],height=frame.shape[0],roi=effective.get('roi'))
            except Exception as e:
                with lock: state['status']=str(e)
            stop.wait(.08)
    finally:
        if cap is not None: cap.release()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        if self.path=='/': data=(ROOT/'index-v2.html').read_bytes(); mime='text/html'
        elif self.path=='/settings':
            with lock: data=json.dumps(config).encode()
            mime='application/json'
        elif self.path.startswith('/raw'):
            with lock: data=state.get('raw')
            if data is None: self.send_error(503); return
            mime='image/jpeg'
        elif self.path.startswith('/frame'):
            with lock: data=state['jpeg']
            if data is None: self.send_error(503); return
            mime='image/jpeg'
        elif self.path=='/state':
            with lock: data=json.dumps({k:v for k,v in state.items() if k not in ('jpeg','raw')}).encode()
            mime='application/json'
        else: self.send_error(404); return
        self.send_response(200); self.send_header('Content-Type',mime); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        try:
            data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
            if self.path=='/config':
                with lock:
                    if 'ruler_points' in data and data['ruler_points'] is not None and state.get('raw'):
                        (ROOT/'ruler-reference.jpg').write_bytes(state['raw'])
                    for key in config:
                        if key in data: config[key]=data[key]
                    settings.write_text(json.dumps(config,indent=2))
                self.send_response(200); self.end_headers(); self.wfile.write(b'OK')
            elif self.path=='/save':
                folder=ROOT/'captures'; folder.mkdir(exist_ok=True); name=time.strftime('%Y%m%d-%H%M%S')
                with lock:
                    (folder/(name+'.jpg')).write_bytes(state['jpeg'])
                    (folder/(name+'.json')).write_text(json.dumps({k:v for k,v in state.items() if k not in ('jpeg','raw')},indent=2))
                self.send_response(200); self.end_headers(); self.wfile.write(name.encode())
            else: self.send_error(404)
        except Exception as e: self.send_error(400,str(e))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--image')
    parser.add_argument('--host',default='127.0.0.1',help='Use 0.0.0.0 for access on a trusted LAN')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--camera-backend',choices=('opencv','picamera2'),default='opencv',help='Use picamera2 for the ribbon-connected Raspberry Pi Camera; opencv for USB cameras')
    parser.add_argument('--camera',type=int,help='Camera index; Pi Camera defaults to 0')
    parser.add_argument('--width',type=int,default=1920)
    parser.add_argument('--height',type=int,default=1080)
    parser.add_argument('--reset-calibration',action='store_true',help='Start with no scale or parts area; calibrate in the browser')
    args=parser.parse_args()
    if args.width<=0 or args.height<=0: parser.error('Width and height must be positive')
    if args.camera is not None and args.camera<0: parser.error('Camera index must be nonnegative')
    if not 1<=args.port<=65535: parser.error('Port must be between 1 and 65535')
    if args.camera is not None: config['camera']=args.camera
    elif args.camera_backend=='picamera2': config['camera']=0
    if args.reset_calibration:
        config.update(scale_mode='ruler',ruler_points=None,corners=None,roi=None)
    if args.image:
        out,results,status=analyze(cv2.imread(args.image),config)
        cv2.imwrite(str(ROOT/'analysis.jpg'),annotate(out,results))
        print(json.dumps({'status':status,'results':results},indent=2))
    else:
        with ThreadingHTTPServer((args.host,args.port),Handler) as server:
            worker=threading.Thread(target=camera_loop,args=(args.width,args.height,args.camera_backend),daemon=True)
            worker.start()
            print(f'Fastener CV: http://{args.host}:{args.port} ({args.camera_backend}, camera {config["camera"]})',flush=True)
            try: server.serve_forever()
            except KeyboardInterrupt: pass
            finally:
                stop.set()
                worker.join(timeout=5)
