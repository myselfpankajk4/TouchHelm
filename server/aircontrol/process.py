"""Bounded observation pipe. Only one frame survives reader backpressure."""
import json
import math
from collections import deque
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

class CameraWorker:
    def __init__(self,setup):
        self.setup=setup;self.process=None;self.queue=queue.Queue(maxsize=1);self._usage={};self._cpu=None;self._sampled=0.
        self._terminal=None;self._stderr=deque(maxlen=8);self._readers=[];self._usage_sample=None
    def read_usage(self,sample):
        if not isinstance(sample,dict):return
        if any(type(sample.get(k)) not in (int,float) or not math.isfinite(sample[k]) or sample[k]<0 for k in ('at','cpu_seconds')):return
        memory=sample.get('memory_mb')
        if memory is not None and (type(memory) not in (int,float) or not math.isfinite(memory) or memory<=0):return
        if self._usage_sample and sample['at']<=self._usage_sample['at']:return
        self._usage_sample={k:sample[k] for k in ('at','cpu_seconds','memory_mb') if k in sample}
    def stats(self):
        process=self.process
        if not process or process.poll() is not None:return {}
        sample=self._usage_sample
        if not sample:return {}
        stamp,cpu=sample['at'],sample['cpu_seconds']
        if self._cpu and stamp>self._cpu[0]:
            self._usage['cpu_percent']=round(max(0.,min(100.,(cpu-self._cpu[1])/(stamp-self._cpu[0])*100/(os.cpu_count() or 1))),1)
        self._cpu=(stamp,cpu)
        if 'memory_mb' in sample:self._usage['memory_mb']=sample['memory_mb']
        else:self._usage.pop('memory_mb',None)
        return dict(self._usage)
    def start(self,profile):
        self.process=subprocess.Popen([str(self.setup.python),'-u',str(Path(__file__).with_name('worker.py')),
            '--models',str(self.setup.models),'--config',json.dumps(profile)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
            env=dict(os.environ,PYTHONUTF8='1'))
        process=self.process
        self._terminal=None;self._stderr.clear()
        def errors():
            while True:
                line=process.stderr.readline(2049)
                if not line:break
                self._stderr.append(line.strip()[-350:])
        error_reader=threading.Thread(target=errors,daemon=True,name='TouchHelm camera errors')
        error_reader.start()
        def read():
            try:
                # A fast exit can leave its final JSON error in the pipe.
                # Drain to EOF instead of discarding it based on poll().
                while True:
                    line=process.stdout.readline(400001)
                    if not line:break
                    if len(line)>400000:break
                    try:item=json.loads(line)
                    except ValueError:continue
                    if not isinstance(item,dict):continue
                    self.read_usage(item.get('usage'))
                    if item.get('type')=='error':self._terminal=item
                    try:self.queue.put_nowait(item)
                    except queue.Full:
                        try:self.queue.get_nowait()
                        except queue.Empty:pass
                        try:self.queue.put_nowait(item)
                        except queue.Full:pass
            finally:
                error_reader.join(timeout=.2)
                if self._terminal is None:
                    code=process.poll()
                    detail=next((line for line in reversed(self._stderr) if line),'')
                    self._terminal={'type':'error','message':f'Camera worker stopped (exit {code if code is not None else "pending"}). '+
                        (detail[:350] if detail else 'Restart the camera. Check its USB connection and whether another app is using it.')}
        reader=threading.Thread(target=read,daemon=True,name='TouchHelm camera pipe')
        self._readers=[reader,error_reader];reader.start()
    def latest(self):
        try:return self.queue.get_nowait()
        except queue.Empty:
            if self._terminal:return dict(self._terminal)
            if self.process and self.process.poll() is not None:
                # Let the pipe reader finish draining the final error first.
                if any(t.is_alive() for t in self._readers):return None
                return {'type':'error','message':f'Camera worker stopped (exit {self.process.poll()}). Restart the camera.'}
            return None
    def recenter(self):
        if self.process and self.process.poll() is None:
            self.process.stdin.write('{"action":"recenter"}\n');self.process.stdin.flush()
    def stop(self):
        process,self.process=self.process,None
        if not process:return
        if process.poll() is None:
            try:process.stdin.write('{"action":"stop"}\n');process.stdin.flush()
            except (OSError,ValueError):pass
            try:process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                # Store/venv launchers can own a separate Python interpreter.
                # Only this owned helper's process tree is eligible for fallback.
                try:subprocess.run(['taskkill.exe','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=2,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                except (OSError,subprocess.TimeoutExpired):pass
                if process.poll() is None:process.kill()
                process.wait(timeout=1)
        for reader in self._readers:reader.join(timeout=.3)
        self._readers=[]
        for stream in (process.stdin,process.stdout,process.stderr):
            if stream:stream.close()
