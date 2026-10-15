import argparse,json,os,socket,sys,threading,webbrowser
from pathlib import Path
from urllib.request import urlopen

def data_directory():
    if os.environ.get('CONTENT_WORKBENCH_DATA_DIR'):return Path(os.environ['CONTENT_WORKBENCH_DATA_DIR']).expanduser().resolve()
    if sys.platform=='win32':return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'content-workbench'
    if sys.platform=='darwin':return Path.home()/'Library'/'Application Support'/'content-workbench'
    return Path.home()/'.local'/'share'/'content-workbench'

def launch(data_dir=None,port=8766,open_browser=True):
    with socket.socket() as probe:
        probe.settimeout(0.5)
        occupied=probe.connect_ex(('127.0.0.1',port))==0
    if occupied:
        try:
            with urlopen(f'http://127.0.0.1:{port}/api/session',timeout=1) as response:
                running=json.load(response).get('version')
        except (OSError,ValueError,KeyError,TypeError):running=None
        from waypoint import __version__
        detail=f'当前后台版本 {running}，准备启动的版本 {__version__}' if running else '该端口可能被其他程序占用'
        raise RuntimeError(f'本机端口 {port} 已占用（{detail}）；请先关闭旧工作台窗口，再重新启动。')
    import uvicorn
    from waypoint.server import create_app
    root=Path(data_dir) if data_dir else data_directory()
    print(f'内容工作台（通用版）正在启动。本机地址：http://127.0.0.1:{port}')
    print(f'资料目录：{root}\n请保持此窗口开启。关闭窗口会中断未完成任务。')
    if open_browser:threading.Timer(1.5,lambda:webbrowser.open(f'http://127.0.0.1:{port}')).start()
    uvicorn.run(create_app(root),host='127.0.0.1',port=port,log_level='warning')

def main():
    parser=argparse.ArgumentParser(description='waypoint 本地工作台')
    parser.add_argument('--data-dir',type=Path);parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    try:launch(args.data_dir,args.port,not args.no_browser)
    except RuntimeError as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
if __name__=='__main__':main()
