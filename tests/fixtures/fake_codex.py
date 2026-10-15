"""Protocol fixture, no network or real authentication."""
import sys,json

def send(m):
    raw=json.dumps(m)+'\n';mid=len(raw)//2
    sys.stdout.write(raw[:mid]);sys.stdout.flush();sys.stdout.write(raw[mid:]);sys.stdout.flush()
for line in sys.stdin:
    q=json.loads(line);method=q.get('method');i=q.get('id')
    if i is None:continue
    result={}
    if method=='account/read':result={'account':{'type':'chatgpt','planType':'plus'}}
    elif method=='model/list':result={'data':[{'id':'test','model':'test'}],'nextCursor':None}
    elif method=='account/rateLimits/read':result={'rateLimits':{'primary':{'usedPercent':3}}}
    elif method=='thread/start':
        if q['params'].get('sandbox')!='read-only':
            send({'id':i,'error':{'code':-32602,'message':'Invalid sandbox; expected read-only'}});continue
        result={'thread':{'id':'thread1'}}
    elif method=='turn/start':result={'turn':{'id':'turn1','status':'inProgress'}}
    send({'id':i,'result':result})
    if method=='turn/start':
        send({'method':'item/completed','params':{'threadId':'thread1','turnId':'turn1','item':{'type':'agentMessage','phase':'final_answer','text':'{"title":"","body":"Example.","note_zh":"老细，协议示例。","questions":[],"citations":[]}'}}})
        send({'method':'turn/completed','params':{'threadId':'thread1','turn':{'id':'turn1','status':'completed'}}})
