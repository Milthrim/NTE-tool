"""Local Windows helper. F8 toggles automation; F9 stops and releases held keys."""
from pathlib import Path
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import queue
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk, messagebox

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent

def self_test(report_path):
    """Validate runtime and GUI initialization without sending game inputs."""
    import numpy as np
    import scipy
    import cv2
    from PIL import Image
    from vision import Vision
    from controller import Controller
    import native
    vision = Vision()
    reading = vision.analyze(Image.new('RGB', (1536, 864)))
    assert not reading.playing and reading.button is None
    root = tk.Tk()
    root.withdraw()
    root.update()
    root.destroy()
    Path(report_path).write_text(json.dumps({
        'ok': True, 'frozen': bool(getattr(sys, 'frozen', False)),
        'python': sys.version, 'numpy': np.__version__, 'scipy': scipy.__version__,
        'opencv': cv2.__version__, 'templates': len(vision.assets),
        'tk': tk.TkVersion, 'executable': sys.executable,
        'checks': ['imports', 'templates', 'blank_frame_recognition', 'tk_window_initialization']
    }, ensure_ascii=False, indent=2), encoding='utf-8')

def run():
    from native import dpi_awareness, foreground_game, capture, pressed, Input, single_instance
    from vision import Vision
    from controller import Controller
    dpi_awareness()
    instance = single_instance()
    if instance is None:
        return
    args = argparse.ArgumentParser()
    args.add_argument('--test-rounds',type=int,default=0)
    args.add_argument('--auto-start',action='store_true')
    args.add_argument('--observe',action='store_true')
    args.add_argument('--record',metavar='DIRECTORY',help='Save at most 400 local calibration frames.')
    opts = args.parse_args()
    log = logging.getLogger('helper')
    log.setLevel(logging.INFO)
    handler = RotatingFileHandler(ROOT/'run.log',maxBytes=1_000_000,backupCount=2,encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    log.addHandler(handler)

    root = tk.Tk()
    root.title('异环小游戏助手 · 甜蜜大摆圈')
    root.geometry('610x560')
    root.minsize(570,550)
    root.configure(bg='#161c29')
    style=ttk.Style(root)
    style.theme_use('clam')
    style.configure('TFrame',background='#161c29')
    style.configure('TLabel',background='#161c29',foreground='#e7ebf5',font=('Microsoft YaHei UI',10))
    style.configure('Title.TLabel',font=('Microsoft YaHei UI',19,'bold'),foreground='#f8c8df')
    style.configure('Big.TLabel',font=('Microsoft YaHei UI',22,'bold'),foreground='#8ee2ce')
    style.configure('TCheckbutton',background='#161c29',foreground='#e7ebf5',font=('Microsoft YaHei UI',10))
    style.map('TCheckbutton',background=[('active','#243049'),('disabled','#161c29')],
              foreground=[('active','#e7ebf5'),('disabled','#7d879a')])
    style.configure('TButton',font=('Microsoft YaHei UI',11),padding=8)
    body=ttk.Frame(root,padding=22)
    body.pack(fill='both',expand=True)
    ttk.Label(body,text='甜蜜大摆圈',style='Title.TLabel').pack(anchor='w')
    ttk.Label(body,text='自动识别方向 → 达到 9000 分停手 → 结算后重新开始').pack(anchor='w',pady=(6,16))
    score=tk.StringVar(value='本局分数  —')
    status=tk.StringVar(value='待启动 · 将游戏保持在前台')
    stats=tk.StringVar(value='已完成 0 局')
    ttk.Label(body,textvariable=score,style='Big.TLabel').pack(anchor='w')
    ttk.Label(body,textvariable=status,wraplength=555).pack(anchor='w',pady=(8,4))
    ttk.Label(body,textvariable=stats).pack(anchor='w',pady=(0,14))
    controls=ttk.Frame(body);controls.pack(fill='x')
    repeat=tk.BooleanVar(value=True)
    observe=tk.BooleanVar(value=opts.observe)
    rounds=tk.StringVar(value=str(opts.test_rounds))
    trigger=tk.StringVar(value='85')
    ttk.Checkbutton(controls,text='结算后自动重开',variable=repeat).grid(row=0,column=0,sticky='w')
    ttk.Checkbutton(controls,text='仅识别，不按键',variable=observe).grid(row=0,column=1,sticky='w',padx=12)
    ttk.Label(controls,text='运行局数（0 = 持续）').grid(row=1,column=0,sticky='w',pady=10)
    ttk.Spinbox(controls,from_=0,to=999,width=9,textvariable=rounds).grid(row=1,column=1,sticky='w',padx=12)
    ttk.Label(controls,text='触发大小（数值越小，按得越早）').grid(row=2,column=0,sticky='w')
    ttk.Spinbox(controls,from_=65,to=220,width=9,textvariable=trigger).grid(row=2,column=1,sticky='w',padx=12)
    buttons=ttk.Frame(body);buttons.pack(fill='x',pady=(20,14))
    text=tk.Text(body,height=6,bg='#101520',fg='#bac7dc',relief='flat',font=('Microsoft YaHei UI',9),wrap='word')
    text.pack(fill='x')
    text.insert('1.0','F8：开始 / 暂停    F9：立即停止\n使用 16:9 分辨率，游戏保持前台。切换窗口时自动暂停输入。\n粉色点按，蓝色长按，橙色连按。每次重开会消耗界面标示的 500 游戏币。\n首次建议先设为 1 局，查看实际得分后再开启连续运行。')
    text.configure(state='disabled')

    active=threading.Event()
    quitting=threading.Event()
    messages=queue.Queue()
    commands=queue.Queue()
    state={'controller':None,'settings':None,'started':0.0,'active_since':0.0,'failed':False}
    io=Input(lambda:active.is_set() and not quitting.is_set())

    def stop():
        active.clear()
        commands.put(('stop',None))
        status.set('已停止 · 按键正在释放')
        log.info('USER STOP')

    def toggle():
        if state['failed']:
            messagebox.showerror('需要重启','发生错误后请关闭助手并重新打开；详细错误见 run.log。')
            return
        if active.is_set():
            active.clear()
            status.set('已暂停 · F8 继续')
            log.info('PAUSE')
            return
        try:
            n=int(rounds.get()); size=int(trigger.get())
            if n<0 or not 65<=size<=220:raise ValueError()
        except ValueError:
            messagebox.showerror('参数错误','局数须为非负整数；触发大小范围为 65～220。')
            return
        settings={'max_rounds':n,'trigger_size':size,'repeat':bool(repeat.get()),'observe':bool(observe.get())}
        commands.put(('start',settings))
        active.set()
        status.set('3 秒后开始 · 请切回游戏')
        log.info('START %s',json.dumps(settings,ensure_ascii=False))

    ttk.Button(buttons,text='F8  开始 / 暂停',command=toggle).pack(side='left',fill='x',expand=True,padx=(0,10))
    ttk.Button(buttons,text='F9  停止',command=stop).pack(side='left',fill='x',expand=True)

    def worker():
        try:
            vision=Vision()
            last_report=0.;last_log_score='';last_hwnd=None;last_no_focus=False;last_metrics=0.
            record_count=0
            record_dir=Path(opts.record) if opts.record else None
            if record_dir:record_dir.mkdir(parents=True,exist_ok=True)
            while not quitting.is_set():
                try:
                    while True:
                        command,data=commands.get_nowait()
                        if command=='stop':
                            io.release_all();state['controller']=None
                        elif command=='start':
                            if state['controller'] is None or state['settings']!=data:
                                state['controller']=Controller(data['trigger_size'],data['max_rounds'],data['repeat'])
                            else:
                                state['controller'].suspend()
                            state['settings']=data
                            state['started']=time.monotonic()+3
                            state['active_since']=time.monotonic()
                except queue.Empty:
                    pass
                ctl=state['controller']
                if not active.is_set() or ctl is None:
                    io.release_all()
                    if ctl:ctl.suspend()
                    time.sleep(.035)
                    continue
                now=time.monotonic()
                if now<state['started']:
                    time.sleep(.03);continue
                hwnd=foreground_game()
                if not hwnd:
                    io.release_all();ctl.suspend()
                    if not last_no_focus:
                        messages.put(('status','游戏不在前台，输入已暂停'))
                        log.info('FOCUS PAUSE')
                    last_no_focus=True
                    time.sleep(.08);continue
                last_no_focus=False
                if last_hwnd is not None and last_hwnd!=hwnd:
                    io.release_all();ctl.suspend()
                last_hwnd=hwnd
                begun=time.perf_counter()
                screenshot,box=capture(hwnd)
                capture_done=time.perf_counter()
                reading=vision.analyze(screenshot)
                analysis_done=time.perf_counter()
                actions=ctl.tick(reading,time.monotonic())
                if reading.score_text!='—' and reading.score_text!=last_log_score:
                    log.info('SCORE %s reached=%s',reading.score_text,reading.reached)
                    last_log_score=reading.score_text
                for action in actions:
                    if action.name=='release':
                        if action.key in io.held:io.key(action.key,False)
                        continue
                    if action.name=='stop':
                        active.clear();io.release_all();state['controller']=None
                        log.info('COMPLETED rounds=%s',ctl.rounds)
                        continue
                    if not active.is_set() or state['settings']['observe']:
                        continue
                    if action.name=='hold':io.key(action.key,True,hwnd)
                    elif action.name=='tap':io.tap(action.key,hwnd)
                    elif action.name=='click':io.click(action.key,hwnd,box)
                    log.info('ACTION %s %s note=%s',action.name,action.key,reading.note)
                if opts.record and record_count<1200:
                    # Record after issuing input, so encoding cannot delay a press.
                    screenshot.resize((1536,864)).save(record_dir/f'{record_count:04}.jpg',quality=88)
                    record_count+=1
                elapsed=time.perf_counter()-begun
                if time.monotonic()-last_metrics>5:
                    log.info('TIMING capture=%.0fms vision=%.0fms loop=%.0fms',
                             1000*(capture_done-begun),1000*(analysis_done-capture_done),1000*elapsed)
                    last_metrics=time.monotonic()
                if time.monotonic()-last_report>.15:
                    messages.put(('reading',(reading.score_text,ctl.status,ctl.rounds,elapsed,state['settings']['observe'])))
                    last_report=time.monotonic()
                time.sleep(max(0,.055-elapsed))
        except Exception:
            active.clear()
            state['failed']=True
            detail=traceback.format_exc()
            log.error(detail)
            messages.put(('error',detail.splitlines()[-1]))
        finally:
            try:io.release_all()
            except Exception:log.exception('KEY RELEASE FAILED')

    keys={0x77:False,0x78:False}
    def update():
        if quitting.is_set():return
        for vk in keys:
            down=pressed(vk)
            if down and not keys[vk]:
                (toggle if vk==0x77 else stop)()
            keys[vk]=down
        try:
            while True:
                kind,payload=messages.get_nowait()
                if kind=='reading':
                    value,description,count,elapsed,preview=payload
                    score.set('本局分数  '+value)
                    status.set(('仅识别 · ' if preview else '')+description)
                    stats.set(f'已完成 {count} 局  ·  单帧 {elapsed*1000:.0f} ms')
                elif kind=='status':status.set(payload)
                elif kind=='error':
                    status.set('已停止：'+payload)
                    messagebox.showerror('助手已停止',payload+'\n详细记录在 run.log。')
        except queue.Empty:pass
        root.after(25,update)

    worker_thread=threading.Thread(target=worker,name='game-helper',daemon=False)
    worker_thread.start()
    def close():
        active.clear();quitting.set()
        root.withdraw()
        def finish():
            if worker_thread.is_alive():root.after(50,finish)
            else:root.destroy()
        finish()
    root.protocol('WM_DELETE_WINDOW',close)
    update()
    if opts.auto_start:root.after(600,toggle)
    root.mainloop()

if __name__=='__main__':
    try:
        if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
            self_test(sys.argv[2])
        else:
            run()
    except Exception:
        detail=traceback.format_exc()
        (ROOT/'startup-error.log').write_text(detail,encoding='utf-8')
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'启动失败。请查看同目录 startup-error.log。\n'+detail.splitlines()[-1],'异环小游戏助手',16)
        except Exception:
            print(detail,file=sys.stderr)
