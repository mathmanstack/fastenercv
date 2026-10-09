from pathlib import Path
import json
root=Path(__file__).resolve().parent
p=root/'index-v2.html'; s=p.read_text(encoding='utf-8-sig')
s=s.replace('let roi=settings.roi','let roi=settings.roi')
s=s.replace("roi:[Math.round(Math.min", "auto_area:false,roi:[Math.round(Math.min")
s=s.replace("scale_mode:'ruler',ruler_points:points", "scale_mode:'ruler',auto_area:true,ruler_points:points")
s=s.replace("{roi:null}); settings.roi=null", "{roi:null,auto_area:false}); settings.roi=null")
s=s.replace("let s=await(await fetch('/state')).json();", "let s=await(await fetch('/state')).json();if(s.roi)settings.roi=s.roi;")
p.write_text(s,encoding='utf-8')
# Calibrate the clearly visible 1-inch and 5-inch ticks in the latest frame.
(root/'ruler-reference.jpg').write_bytes((root/'final-raw.jpg').read_bytes())
settings={'camera':1,'card_width':32.,'card_height':24.,'corners':None,'threshold':32,
          'scale_mode':'ruler','ruler_points':[[767,472],[1370,460]],'ruler_mm':101.6,
          'roi':[610,0,950,457],'follow_ruler':True,'auto_area':True}
(root/'calibration.json').write_text(json.dumps(settings,indent=2))
print('UI and ruler reference saved')
