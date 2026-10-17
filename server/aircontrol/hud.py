"""Shared physical HUD geometry for rendering and head-only dwell hit testing."""
HEAD_ACTIONS={'dwell_left':'left_click','dwell_double':'double_click','dwell_right':'right_click','dwell_drag':'drag'}


def layout(display,*,active=False,head=False,dragging=False):
    rect=display['rect'];expanded=active and head
    top=rect['y']+rect['height']-(200 if expanded else 150)
    left=rect['x']+rect['width']-320
    targets=[]
    if expanded:
        for i,(action,label) in enumerate(zip(HEAD_ACTIONS,('Click','Double','Right','Drop' if dragging else 'Drag'))):
            targets.append(dict(action=action,label=label,x=12+i*72,y=76,w=60,h=44))
    row=124 if expanded else 76
    if active:
        targets.extend([dict(action='pause',label='Pause',x=12,y=row,w=133,h=44),dict(action='stop',label='Stop',x=155,y=row,w=133,h=44)])
    else:
        targets.extend(dict(action=action,label=label,x=x,y=row,w=88,h=42) for action,label,x in
            [('resume','Resume',12),('recenter','Recenter',106),('stop','Stop',200)])
    return dict(x=left,y=top,width=300,height=174 if expanded else 124,targets=targets)


def regions(display,*,active=False):
    if not display:return []
    spec=layout(display,active=active,head=True);r=display['rect'];w=r['width']-1;h=r['height']-1
    if w<=0 or h<=0:return []
    return [dict(action=t['action'],rect=[(spec['x']+t['x']-r['x'])/w,(spec['y']+t['y']-r['y'])/h,
        (spec['x']+t['x']+t['w']-r['x'])/w,(spec['y']+t['y']+t['h']-r['y'])/h])
        for t in spec['targets'] if active or t['action'] in ('resume','recenter')]
