import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'vendor'))
import cv2
import numpy as np
from vision import profile_measure, Stabilizer

# A 3 mm x 20 mm blunt shaft with a 6 mm wide, 2 mm long head.
bolt=np.array([[0,-3],[2,-3],[2,-1.5],[22,-1.5],[22,1.5],[2,1.5],[2,3],[0,3]],np.float32)
screw=np.array([[0,-3],[2,-3],[2,-1.5],[16,-1.5],[22,0],[16,1.5],[2,1.5],[2,3],[0,3]],np.float32)
for degrees in [0,25,65,120]:
    angle=np.deg2rad(degrees); rotation=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]],np.float32)
    for shape,kind in [(bolt,'Bolt / machine screw'),(screw,'Pointed screw (likely)')]:
        m=profile_measure(shape@rotation)
        assert m is not None,(degrees,kind)
        assert abs(m['diameter_mm']-3)<.2,m
        assert abs(m['under_head_length_mm']-20)<.4,m
        assert m['type']==kind,m
tracker=Stabilizer()
for i in range(6):
    item=profile_measure(bolt); item['box']=[100+i,100,130,35]
    stable=tracker.update([item])
assert len(stable)==1 and stable[0]['id']==1
print('PASS: rotated diameter/length, blunt vs tapered tips, stable track identity')
from ruler import RulerTracker
import app
frame=cv2.imread(str(app.ROOT/'ruler-reference.jpg'))
shifted=cv2.warpAffine(frame,np.array([[1,0,20],[0,1,-15]],np.float32),(frame.shape[1],frame.shape[0]))
followed=RulerTracker(app.ROOT).follow(shifted,app.config)
assert np.allclose(np.array(followed['ruler_points']),np.array(app.config['ruler_points'])+[20,-15],atol=3)
lost=RulerTracker(app.ROOT).follow(np.full_like(frame,180),app.config)
assert lost['ruler_points'] is None
print('PASS: ruler translation and refusal to measure when reference is lost')
(app.ROOT/'ui-check.js').write_text((app.ROOT/'index-v2.html').read_text(encoding='utf-8').split('<script>')[1].split('</script>')[0],encoding='utf-8')
