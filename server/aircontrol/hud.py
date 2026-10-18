"""Shared physical HUD geometry for rendering and head-only dwell hit testing."""
HEAD_ACTIONS={'dwell_left':'left_click','dwell_double':'double_click','dwell_right':'right_click','dwell_drag':'drag'}
HEAD_SCROLL_ACTIONS=('head_scroll','scroll_up','scroll_down','scroll_done')


def layout(display,*,active=False,head=False,dragging=False,scrolling=False):
    rect=display['rect'];expanded=active and head
    tall=expanded and not scrolling
    top=rect['y']+rect['height']-(248 if tall else 200 if expanded else 150)
    left=rect['x']+rect['width']-320
    targets=[]
    if expanded and scrolling:
        targets.extend(dict(action=a,label=l,x=12+i*94,y=76,w=88,h=44)
            for i,(a,l) in enumerate((('scroll_up','Up'),('scroll_down','Down'),('scroll_done','Done'))))
    elif expanded:
        for i,(action,label) in enumerate(zip(HEAD_ACTIONS,('Click','Double','Right','Drop' if dragging else 'Drag'))):
            targets.append(dict(action=action,label=label,x=12+i*72,y=76,w=60,h=44))
        targets.append(dict(action='head_scroll',label='Scroll',x=12,y=124,w=276,h=44))
    row=172 if tall else 124 if expanded else 76
    if active:
        targets.extend([dict(action='pause',label='Pause',x=12,y=row,w=133,h=44),dict(action='stop',label='Stop',x=155,y=row,w=133,h=44)])
    else:
        targets.extend(dict(action=action,label=label,x=x,y=row,w=88,h=44) for action,label,x in
            [('resume','Resume',12),('recenter','Recenter',106),('stop','Stop',200)])
    return dict(x=left,y=top,width=300,height=222 if tall else 174 if expanded else 124,targets=targets)


def regions(display,*,active=False,scrolling=False):
    if not display:return []
    spec=layout(display,active=active,head=True,scrolling=scrolling);r=display['rect'];w=r['width']-1;h=r['height']-1
    if w<=0 or h<=0:return []
    return [dict(action=t['action'],rect=[(spec['x']+t['x']-r['x'])/w,(spec['y']+t['y']-r['y'])/h,
        (spec['x']+t['x']+t['w']-r['x'])/w,(spec['y']+t['y']+t['h']-r['y'])/h])
        for t in spec['targets'] if active or t['action'] in ('resume','recenter')]


def practice_regions(viewport,*,scrolling=False):
    if not scrolling:return []
    w,h=viewport;top=h-148
    return [dict(action=a,label=l,rect=[x/w,y/h,(x+width)/w,(y+44)/h]) for a,l,x,y,width in
        [('scroll_up','Up',8,top,(w-20)/2),('scroll_down','Down',(w+4)/2,top,(w-20)/2),
         ('scroll_done','Done',8,top+48,w-16),('pause','Pause',8,top+96,(w-20)/2),
         ('stop','Stop',(w+4)/2,top+96,(w-20)/2)]]
