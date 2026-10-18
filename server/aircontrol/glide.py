"""Eases the real Windows cursor between camera-rate pointer targets.

The engine produces one pointer point per camera frame (10-15 Hz). Writing each one
straight to Windows makes the cursor step. ``CursorGlide`` moves at constant speed
from where the cursor is to each new point over about one frame interval, written
from a ~100 Hz thread. The cursor trails the engine by about one frame interval
(never more than ``max_duration``); it does not extrapolate and never overshoots.

Without a running thread (unit tests, camera stopped) every point is written
immediately, which is the pre-glide behavior.
"""
import math
import threading
import time


class CursorGlide:
    def __init__(self,write,*,probe=None,tolerance=12,clock=time.monotonic,rate=100.,
                 min_duration=.03,max_duration=.16,default_duration=.1):
        self._write=write;self._probe=probe;self.tolerance=tolerance;self._clock=clock
        self.period=1/rate;self.min_duration=min_duration;self.max_duration=max_duration
        self.default_duration=default_duration
        self._lock=threading.RLock();self._thread=None;self._exit=threading.Event();self._running=False
        self.error=None;self.taken_over=False
        self._reset()

    def _reset(self):
        self._last=None;self._pos=None;self._target=None;self._segment=None
        self._stamp=None;self._interval=None

    @property
    def last(self):
        """The point most recently written to Windows (None until the first write)."""
        return self._last

    @property
    def running(self):
        return self._running

    def start(self,*,threaded=True):
        """Begin easing. ``threaded=False`` leaves the caller to call ``tick`` (tests)."""
        with self._lock:
            if self._running:return
            self._exit.clear();self.error=None;self.taken_over=False;self._running=True
            if threaded:
                self._thread=threading.Thread(target=self._run,name='aircontrol-cursor-glide',daemon=True)
                self._thread.start()

    def close(self):
        """Stop the thread and forget all state. No write happens after this returns."""
        with self._lock:
            self._running=False;self._exit.set();self._reset();thread=self._thread;self._thread=None
        if thread and thread is not threading.current_thread():thread.join(1)

    def _run(self):
        deadline=self._clock()
        while not self._exit.is_set():
            try:self.tick()
            except Exception as error:
                with self._lock:self.error=error;self._segment=None
                return
            deadline+=self.period;delay=deadline-self._clock()
            if delay<-.25:deadline=self._clock();delay=0
            if delay>0:time.sleep(delay)

    def halt(self):
        """Drop the target and the last point; nothing is written until the next retarget."""
        with self._lock:
            self._reset();self.taken_over=False

    def set_last(self,point):
        """Declare where the cursor really is (for example after reading it from Windows)."""
        with self._lock:
            self._reset();self._last=tuple(point);self._pos=(float(point[0]),float(point[1]))
            self._target=self._last

    def _emit(self,point):
        self._write(*point);self._last=point

    def retarget(self,point):
        point=(int(point[0]),int(point[1]))
        with self._lock:
            now=self._clock()
            if not self._running or self._pos is None:
                self._emit(point);self._pos=(float(point[0]),float(point[1]));self._target=point
                self._segment=None;self._stamp=now if self._running else None;return
            self._advance(now)
            if self._stamp is not None:
                gap=now-self._stamp
                self._interval=None if gap>.5 else gap if self._interval is None else .5*(self._interval+gap)
            self._stamp=now;self._target=point
            if math.dist(self._pos,point)<.5:self._segment=None;return
            duration=min(self.max_duration,max(self.min_duration,self._interval or self.default_duration))
            self._segment=(self._pos,point,now,duration)

    def _advance(self,now):
        if self._segment is None:return
        (sx,sy),(gx,gy),t0,duration=self._segment
        fraction=min(1.,max(0.,(now-t0)/duration))
        self._pos=(gx,gy) if fraction>=1 else (sx+(gx-sx)*fraction,sy+(gy-sy)*fraction)
        if fraction>=1:self._segment=None

    def tick(self,now=None):
        """Move one step toward the target. Returns the point written, or None."""
        with self._lock:
            if self._segment is None:return None
            if self.diverged(self.tolerance):
                self.taken_over=True;self._segment=None;return None
            self._advance(self._clock() if now is None else now)
            point=(round(self._pos[0]),round(self._pos[1]))
            if point==self._last:return None
            self._emit(point);return point

    def settle(self):
        """Jump to the engine's latest point now, so a click lands exactly there."""
        with self._lock:
            if self._segment is not None:
                self._segment=None;self._pos=(float(self._target[0]),float(self._target[1]))
                if self._target!=self._last:self._emit(self._target)
            return self._last

    def diverged(self,tolerance=None):
        """True if Windows reports the cursor away from where this object put it."""
        if self._probe is None:return False
        with self._lock:
            if self._last is None:return False
            actual=self._probe()
            return math.hypot(actual[0]-self._last[0],actual[1]-self._last[1])>(self.tolerance if tolerance is None else tolerance)
