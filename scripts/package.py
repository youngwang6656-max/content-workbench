"""Create a shareable source release without needing Git."""
import argparse,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from waypoint.distribution import build_release
def main():
    parser=argparse.ArgumentParser(description='waypoint 纯源码发布包，不包含个人数据')
    parser.add_argument('--output',type=Path,default=root.parent/'releases')
    parser.add_argument('--download-url',default='',help='程序 ZIP 公开 HTTPS 下载地址；留空生成清单模板')
    parser.add_argument('--notes',default='',help='中文更新说明')
    args=parser.parse_args();print(json.dumps(build_release(root,args.output,args.download_url,args.notes),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
