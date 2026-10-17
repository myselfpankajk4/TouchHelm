"""Measured expression calibration. Scores are activation, never confidence."""
import math
import statistics

NAMES=('wink_left','wink_right','smile','brows_up')
CHANNELS=('eyeBlinkLeft','eyeBlinkRight','mouthSmileLeft','mouthSmileRight','browInnerUp')

def levels(face):
    values=face.get('expressions',{})
    if any(type(values.get(k)) not in (int,float) or not math.isfinite(values[k]) or not 0<=values[k]<=1 for k in CHANNELS):return {}
    left=values['eyeBlinkLeft'];right=values['eyeBlinkRight']
    return {'wink_left':left,'wink_right':right,'smile':(values['mouthSmileLeft']+values['mouthSmileRight'])/2,'brows_up':values['browInnerUp']}

def measure(frames):
    frames=frames[-8:]
    if len(frames)<5:raise ValueError('Keep the expression steady for about one second, then capture again.')
    times=[f.get('timestamp') for f in frames]
    if any(type(t) not in (int,float) or not math.isfinite(t) for t in times) or times[-1]-times[0]<.3 or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('Wait for a current, stable expression sample.')
    values=[levels(f.get('face') or {}) if (f.get('face') or {}).get('count')==1 else {} for f in frames]
    if any(not v for v in values):raise ValueError('Expression data is unavailable. Keep one face clearly visible.')
    if any(statistics.pstdev(v[k] for v in values)>.12 for k in NAMES):raise ValueError('Hold the selected expression steady, then capture again.')
    return {k:statistics.median(v[k] for v in values) for k in NAMES}

def learn(neutral,active,gesture):
    if gesture not in NAMES:raise ValueError('Choose a supported facial expression.')
    delta=active[gesture]-neutral[gesture]
    if delta<.14:raise ValueError('The change is too small. Capture a relaxed face, then hold a more deliberate expression.')
    result={'on':neutral[gesture]+.6*delta,'off':neutral[gesture]+.3*delta}
    if gesture.startswith('wink_'):
        other='wink_right' if gesture=='wink_left' else 'wink_left'
        ceiling=min(.65,neutral[other]+.18)
        if active[other]>=ceiling:raise ValueError('Keep the other eye open. An ordinary two-eye blink is not a wink.')
        result['other_max']=ceiling
    return result

def recognize(face,profile,held):
    if not profile['expressions_calibrated']:return ''
    values=levels(face)
    # Legacy observations may contain only the expression used by their profile.
    if not values:
        e=face.get('expressions',{})
        value=lambda k: e.get(k,0.) if type(e.get(k,0.)) in (int,float) and math.isfinite(e.get(k,0.)) else 0.
        values={'wink_left':value('eyeBlinkLeft'),'wink_right':value('eyeBlinkRight'),
            'smile':min(value('mouthSmileLeft'),value('mouthSmileRight')),'brows_up':value('browInnerUp')}
    matches=[]
    for gesture in NAMES:
        if gesture not in profile['calibrated_expressions'] or profile['bindings'][gesture]=='none':continue
        limits=profile.get('expression_thresholds',{}).get(gesture,{'on':.7 if gesture=='smile' else .75,'off':.5,'other_max':.25})
        threshold=limits['off'] if held==gesture else limits['on']
        if values[gesture]<threshold:continue
        if gesture.startswith('wink_'):
            other='wink_right' if gesture=='wink_left' else 'wink_left'
            if values[other]>=limits.get('other_max',.25):continue
        matches.append(gesture)
    return 'conflict' if len(matches)>1 else matches[0] if matches else ''
