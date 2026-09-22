import json
import sys
import threading
import time

lock = threading.Lock()
threads = []

def respond(message):
    args=message.get("params",{})
    method=message["method"]
    time.sleep(args.get("delay",0))
    result={"echo":args.get("value")}
    if method=="initialize": result={"serverInfo":{"version":"0.28.2"}}
    if method=="tools/call": result={"isError":True,"content":[{"type":"text","text":"intentional failure"}]}
    if method=="hang": return
    with lock:
        print(json.dumps({"jsonrpc":"2.0","method":"notifications/progress","params":{}}),flush=True)
        print(json.dumps({"jsonrpc":"2.0","id":message["id"],"result":result}),flush=True)

for line in sys.stdin:
    message=json.loads(line)
    if "id" not in message: continue
    t=threading.Thread(target=respond,args=(message,))
    t.start(); threads.append(t)
for t in threads: t.join()
