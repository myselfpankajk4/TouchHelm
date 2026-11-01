"""Speed-adaptive low-pass filtering, independently implemented from 1€ (CHI 2012).

Reference: https://gery.casiez.net/1euro/ . Units here are normalized screen space.
"""
import math


class OneEuro:
    def __init__(self, minimum=1., beta=2., floor=0.):
        # floor: speed (normalized units/s) treated as tracking noise. Only
        # movement faster than it opens the filter, so a held pose stays calm
        # while a deliberate move still gets the full beta response.
        self.minimum=minimum;self.beta=beta;self.floor=floor;self.reset()

    def reset(self):
        self.time=None;self.raw=None;self.value=None;self.derivative=0.

    @staticmethod
    def alpha(cutoff, dt):
        return 1 / (1 + 1 / (2 * math.pi * cutoff * dt))

    def step(self, value, stamp):
        if not math.isfinite(value) or not math.isfinite(stamp):raise ValueError('Invalid pointer sample')
        if self.time is None or stamp-self.time>.25:
            self.time=stamp;self.raw=self.value=value;self.derivative=0.;return value
        dt=stamp-self.time
        if dt<=0:raise ValueError('Pointer timestamps must increase')
        change=(value-self.raw)/dt
        a=self.alpha(1.,dt)
        self.derivative+=a*(change-self.derivative)
        a=self.alpha(self.minimum+self.beta*max(0.,abs(self.derivative)-self.floor),dt)
        self.value+=a*(value-self.value)
        self.raw=value;self.time=stamp
        return self.value
