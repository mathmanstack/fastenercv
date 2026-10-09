from pathlib import Path
import cv2
import numpy as np

class RulerTracker:
    def __init__(self,root):
        self.root=Path(root); self.template=None; self.source_points=None
    def follow(self,frame,cfg):
        points=cfg.get('ruler_points')
        if not points or cfg.get('scale_mode')!='ruler' or not cfg.get('follow_ruler',True): return cfg
        if self.source_points!=points:
            self.source_points=points
            reference=self.root/'ruler-reference.jpg'
            ref=cv2.imread(str(reference if reference.exists() else self.root/'two-screws-view.jpg'))
            if ref is None: return cfg
            p=np.array(points)
            x0=max(0,int(p[:,0].min()-145)); x1=min(ref.shape[1],int(p[:,0].max()+145))
            y0=max(0,int(p[:,1].min()-8)); y1=min(ref.shape[0],int(p[:,1].max()+65))
            self.origin=np.array([x0,y0]); patch=ref[y0:y1,x0:x1]
            self.template=cv2.resize(cv2.cvtColor(patch,cv2.COLOR_BGR2GRAY),None,fx=.5,fy=.5)
        if self.template is None: return cfg
        small=cv2.resize(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),None,fx=.5,fy=.5)
        match=cv2.matchTemplate(small,self.template,cv2.TM_CCOEFF_NORMED)
        _,score,_,loc=cv2.minMaxLoc(match)
        if score<.55:
            return dict(cfg,ruler_points=None)
        delta=np.array(loc)*2-self.origin
        moved=np.array(points)+delta
        a,b=moved
        left=max(0,int(min(a[0],b[0])-185)); right=min(frame.shape[1],int(max(a[0],b[0])+185))
        bottom=max(50,int(min(a[1],b[1])-3))
        roi=[left,0,right-left,bottom] if cfg.get('auto_area',True) else cfg.get('roi')
        return dict(cfg,ruler_points=moved.tolist(),roi=roi)
