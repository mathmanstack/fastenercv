from pathlib import Path
r=Path(__file__).resolve().parent
p=r/'app.py'
s=p.read_text()
s=s.replace('import numpy as np','import numpy as np\nfrom vision import detect, size_label, Stabilizer')
s=s.replace("config={'camera':1,'card_width':32.,'card_height':24.,'corners':None,'threshold':22}","config={'camera':1,'card_width':32.,'card_height':24.,'corners':None,'threshold':32, 'scale_mode':'ruler','ruler_points':[[852,529],[1450,514]],'ruler_mm':101.6,'roi':[810,290,610,215]}\nsettings=ROOT/'calibration.json'\nif settings.exists():\n    config.update(json.loads(settings.read_text()))")
start=s.index('    corners=cfg[\'corners\']; auto=False')
end=s.index('\ndef camera_loop():')
replacement='''    auto=False
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
    results=detect(gray,transform,p,cfg)
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
'''
s=s[:start]+replacement+s[end:]
s=s.replace('cap=None; current=None; failures=0','cap=None; current=None; failures=0; tracker=Stabilizer(); previous_cfg=None')
s=s.replace('out,results,status=analyze(frame,cfg)','''out,results,status=analyze(frame,cfg)
            if cfg!=previous_cfg: tracker=Stabilizer(); previous_cfg=cfg
            results=tracker.update(results)
            annotate(out,results)
            _,raw=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,95])''')
s=s.replace("state.update(jpeg=jpg.tobytes(),results=results", "state.update(jpeg=jpg.tobytes(),raw=raw.tobytes(),results=results")
s=s.replace("if k!='jpeg'", "if k not in ('jpeg','raw')")
s=s.replace("elif self.path.startswith('/frame'):","elif self.path.startswith('/raw'):\n            with lock: data=state.get('raw')\n            if data is None: self.send_error(503); return\n            mime='image/jpeg'\n        elif self.path.startswith('/frame'):")
s=s.replace("if key in data: config[key]=data[key]", "if key in data: config[key]=data[key]\n                    settings.write_text(json.dumps(config,indent=2))")
s=s.replace("cv2.imwrite(str(ROOT/'analysis.jpg'),out)","cv2.imwrite(str(ROOT/'analysis.jpg'),annotate(out,results))")
p.write_text(s)
print('Updated app')
