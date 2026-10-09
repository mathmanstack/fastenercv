"""Silhouette measurements in calibrated planar millimetres."""
import cv2
import numpy as np

def profile_measure(points):
    points=np.asarray(points,np.float32).reshape(-1,2)
    rect=cv2.minAreaRect(points)
    box=cv2.boxPoints(rect)
    edges=np.roll(box,-1,axis=0)-box
    axis=edges[np.argmax(np.linalg.norm(edges,axis=1))]
    axis=axis/np.linalg.norm(axis)
    across=np.array([-axis[1],axis[0]])
    uv=np.stack([points@axis,points@across],axis=1)
    uv-=uv.min(axis=0)
    length=float(uv[:,0].max())
    if not 4<length<80: return None
    # Rasterize the whole outline so profile bins do not depend on sparse
    # contour vertices, which formerly made flat tips look pointed.
    scale=12.
    raster=np.zeros((int(uv[:,1].max()*scale)+5,int(length*scale)+5),np.uint8)
    cv2.fillPoly(raster,[np.round(uv*scale+2).astype(np.int32)],255)
    widths=[]
    for col in raster.T:
        ys=np.flatnonzero(col)
        if len(ys): widths.append((ys[-1]-ys[0]+1)/scale)
    widths=np.array(widths)
    if len(widths)<20: return None
    widths=np.array([np.median(widths[max(0,i-2):i+3]) for i in range(len(widths))])
    n=len(widths); end=max(3,int(n*.24))
    if np.quantile(widths[:end],.85)<np.quantile(widths[-end:],.85): widths=widths[::-1]
    shaft=widths[int(n*.35):int(n*.80)]
    diameter=float(np.quantile(shaft,.6))
    head=float(np.quantile(widths[:end],.85))
    if not 1<diameter<12 or length/diameter<1.6 or not 1.22<head/diameter<3.5: return None
    # Reject branching silhouettes, touching pieces and broad shadow blobs.
    if np.quantile(shaft,.9)/max(np.quantile(shaft,.2),.1)>1.65: return None
    tip=float(np.median(widths[int(n*.92):int(n*.98)]))/diameter
    shoulder=float(np.median(widths[int(n*.78):int(n*.88)]))/diameter
    pointed=(tip<.48 and shoulder<.91) or (tip<.66 and shoulder<.96 and length/diameter>4.5)
    if pointed: kind='Pointed screw (likely)'
    elif tip>.68: kind='Bolt / machine screw'
    else: kind='Fastener — tip unclear'
    peak=int(np.argmax(widths[:int(n*.35)]))
    start=max(peak+1,int(n*.04)); end_head=None
    run=max(3,int(n*.04))
    for i in range(start,int(n*.45)):
        if np.all(widths[i:i+run]<diameter*1.22): end_head=i; break
    if end_head is None: return None
    end_head=max(end_head,int(n*max(.8,head*.18)/length))
    shank=length*(n-end_head)/n
    if shank<1.5: return None
    # Strong width variation signals poor focus, reflection or overlapping parts.
    spread=float(np.quantile(shaft,.9)-np.quantile(shaft,.1))
    return {'type':kind,'diameter_mm':round(diameter,2),'under_head_length_mm':round(shank,1),
            'overall_length_mm':round(length,1),'head_diameter_mm':round(head,1),
            'confidence':'clear outline' if spread<diameter*.22 else 'outline uncertain',
            'tip_ratio':round(tip,2),'shoulder_ratio':round(shoulder,2)}

def detect(gray,transform,card,cfg,frame=None):
    smooth=cv2.GaussianBlur(gray,(3,3),0)
    # Reconstruct local paper brightness; use stronger contrast than the old
    # edge detector so soft shadows are less likely to inflate diameters.
    background=cv2.morphologyEx(smooth,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(91,91)))
    contrast=cv2.subtract(background,smooth)
    mask=np.uint8(contrast>cfg['threshold'])*255
    if frame is not None:
        chroma=frame[:,:,0].astype(np.float32)-frame[:,:,2].astype(np.float32)
        chroma-=cv2.GaussianBlur(chroma,(91,91),0)
        mask=np.uint8(((contrast>18)&(chroma>7)) | (contrast>max(75,cfg['threshold']+25)))*255
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    excluded=np.zeros_like(mask); cv2.fillConvexPoly(excluded,card.astype(np.int32),255)
    excluded=cv2.dilate(excluded,np.ones((15,15),np.uint8)); mask[excluded>0]=0
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
    found=[]
    for c in contours:
        if not 100<cv2.contourArea(c)<12000: continue
        x,y,w,h=cv2.boundingRect(c)
        if x<5 or y<5 or x+w>gray.shape[1]-5 or y+h>gray.shape[0]-5: continue
        pts=cv2.perspectiveTransform(c.astype(np.float32),transform)
        item=profile_measure(pts)
        if item is None:
            sides=cv2.minAreaRect(pts)[1]
            length=max(sides); breadth=min(sides)
            if 3<length<14 and 1.2<breadth<9 and length/max(breadth,.1)>1.15:
                item={'type':'Short fastener — shaft unclear','diameter_mm':None,
                      'under_head_length_mm':None,'overall_length_mm':round(float(length),1),
                      'head_diameter_mm':None,'confidence':'not enough shaft visible'}
        if item:
            item['box']=[x,y,w,h]; found.append(item)
    return sorted(found,key=lambda item:(item['box'][1]//60,item['box'][0]))

def size_label(item):
    diameter=item['diameter_mm']
    if diameter is None: return f"~{item['overall_length_mm']:.1f} mm overall"
    standards=np.array([1.6,2,2.5,3,4,5,6,8,10,12])
    candidates=standards[abs(standards-diameter)<max(.35,diameter*.12)]
    nominal=item['type']=='Bolt / machine screw' and len(candidates)>0
    size='~'+'/'.join(f'M{n:g}' for n in candidates) if nominal else f'~{diameter:.1f} mm dia'
    return size+f" x ~{item['under_head_length_mm']:.1f} mm"

class Stabilizer:
    def __init__(self): self.tracks=[]; self.next_id=1
    def update(self,items):
        used=set(); new=[]
        for item in items:
            x,y,w,h=item['box']; center=np.array([x+w/2,y+h/2])
            candidates=[(np.linalg.norm(center-t['center']),j,t) for j,t in enumerate(self.tracks) if j not in used]
            closest=min(candidates,key=lambda x:x[0]) if candidates else None
            if closest and closest[0]<45:
                _,j,t=closest; used.add(j)
                for field in ['diameter_mm','under_head_length_mm','overall_length_mm','head_diameter_mm']:
                    if item['diameter_mm'] is not None and t['item']['diameter_mm'] is not None and item[field] is not None and t['item'][field] is not None:
                        item[field]=round(.25*item[field]+.75*t['item'][field],2)
                item['id']=t['item']['id']; age=t['age']+1
                votes=(t['votes']+[item['type']])[-12:]
                item['type']=max(set(votes),key=votes.count)
            else:
                item['id']=self.next_id; self.next_id+=1; age=1; votes=[item['type']]
            item['size']=size_label(item)
            new.append({'center':center,'item':item,'age':age,'votes':votes})
        self.tracks=new
        return [t['item'] for t in new if t['age']>=3]
