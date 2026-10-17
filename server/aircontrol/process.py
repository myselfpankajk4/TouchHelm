"""Bounded observation pipe. Only one frame survives reader backpressure."""
import json
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
        self._terminal=None;self._stderr=deque(maxlen=8);self._readers=[]
    def stats(self):
        if time.monotonic()-self._sampled<.5:return dict(self._usage)
        self._sampled=time.monotonic();process=self.process
        if not process or process.poll() is not None:return {}
        try:
            import ctypes
            from ctypes import wintypes
            class MEMORY(ctypes.Structure):
                _fields_=[('size',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('peak','working','paged_peak','paged','nonpaged_peak','nonpaged','pagefile','pagefile_peak')]
            api=ctypes.windll.kernel32;handle=wintypes.HANDLE(int(process._handle))
            creation=wintypes.FILETIME();exit_time=wintypes.FILETIME();kernel=wintypes.FILETIME();user=wintypes.FILETIME()
            if api.GetProcessTimes(handle,ctypes.byref(creation),ctypes.byref(exit_time),ctypes.byref(kernel),ctypes.byref(user)):
                total=((kernel.dwHighDateTime<<32)+kernel.dwLowDateTime+(user.dwHighDateTime<<32)+user.dwLowDateTime)/1e7
                if self._cpu:
                    stamp,cpu=self._cpu
                    self._usage['cpu_percent']=round(max(0.,min(100.,(total-cpu)/(self._sampled-stamp)*100/(os.cpu_count() or 1))),1)
                self._cpu=(self._sampled,total)
            memory=MEMORY();memory.size=ctypes.sizeof(memory)
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle,ctypes.byref(memory),memory.size):self._usage['memory_mb']=round(memory.working/1048576,1)
        except (OSError,ValueError,AttributeError):pass
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
            process.terminate()
            try:process.wait(timeout=1)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=1)
        for reader in self._readers:reader.join(timeout=.3)
        self._readers=[]
        for stream in (process.stdin,process.stdout,process.stderr):
            if stream:stream.close()
