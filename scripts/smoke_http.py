#!/usr/bin/env python3
"""Exercise real HTTP, cookies and CSRF against a temporary SQLite database.
Starts its own loopback Gunicorn process. Never touches the normal local database.
"""
import http.cookiejar
import json
import os
import re
import secrets
import socket
import sqlite3
# local isolated test processes; no shell execution
import subprocess  # nosec B404
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
class Session:
    def __init__(self,base):
        self.base=base
        self.jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def request(self,path,data=None,headers=None,form=False):
        headers=dict(headers or {})
        if data is not None:
            headers["Content-Type"]="application/x-www-form-urlencoded" if form else "application/json"
            data=(urllib.parse.urlencode(data) if form else json.dumps(data)).encode()
            token=next((c.value for c in self.jar if c.name=="csrftoken"),"")
            headers["X-CSRFToken"]=token
        req=urllib.request.Request(self.base+path,data=data,headers=headers)
        try: response=self.opener.open(req,timeout=10)
        except urllib.error.HTTPError as error: response=error
        with response: return response.status,response.read(),dict(response.headers)
    def login(self,username,password):
        status,page,_=self.request("/login/")
        require(status==200,"Login form failed")
        token=re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"',page).group(1).decode()
        status,page,_=self.request("/login/",{"username":username,"password":password,"csrfmiddlewaretoken":token},form=True)
        require(status==200 and b"Workspace overview" in page,"Login failed for "+username)
    def json(self,path,data=None,expected=200,headers=None):
        status,content,_=self.request(path,data,headers)
        require(status==expected,f"{path}: expected {expected}, received {status}: "+content.decode()[:300])
        return json.loads(content)
def require(condition,message):
    if not condition: raise RuntimeError(message)
def run():
    with tempfile.TemporaryDirectory(prefix="harborcart-smoke-") as directory:
        db=Path(directory)/"smoke.sqlite3"
        env={**os.environ,"HC_ENV":"local","ENABLE_DEMO":"1","DJANGO_SECRET_KEY":secrets.token_urlsafe(60),
            "DEMO_PASSWORD":secrets.token_urlsafe(20),"METRICS_TOKEN":secrets.token_urlsafe(32),
            "DATABASE_URL":"","SQLITE_PATH":str(db),"ALLOWED_HOSTS":"127.0.0.1,localhost",
            "WORKER_FAIL_KIND":""}
        env.pop("DJANGO_SETTINGS_MODULE",None)
        def command(*args,database=None):
            child_env=env if database is None else {**env,"SQLITE_PATH":str(database)}
            # args are constants at call sites below
            result=subprocess.run([sys.executable,"manage.py",*args],cwd=ROOT,env=child_env,  # nosec B603
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
            require(result.returncode==0,"Command failed: "+str(args)+"\n"+result.stdout[-2000:])
            return result.stdout
        command("migrate","--noinput");command("collectstatic","--noinput");command("seed_demo")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
        base="http://127.0.0.1:"+str(port)
        with (Path(directory)/"server.log").open("w+") as log:
            # fixed executable/module/argv
            server=subprocess.Popen([sys.executable,"-m","gunicorn","harbor.wsgi:application",  # nosec B603
                "--bind","127.0.0.1:"+str(port),"--workers","1","--threads","1","--access-logfile","-"],
                cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                anonymous=Session(base)
                deadline=time.monotonic()+20
                while True:
                    try:
                        if anonymous.request("/readyz")[0]==200: break
                    except (OSError,urllib.error.URLError): pass
                    if server.poll() is not None or time.monotonic()>deadline:
                        log.seek(0);raise RuntimeError("Server did not start: "+log.read()[-2000:])
                    time.sleep(.1)
                sessions={}
                for username in ("buyer","manager","warehouse","finance","operator","rival"):
                    session=Session(base);session.login(username,env["DEMO_PASSWORD"]);sessions[username]=session
                buyer=sessions["buyer"]
                status,catalog,headers=buyer.request("/catalog/")
                require(status==200 and b"Managed network switch" in catalog,"Catalog is not populated")
                require("Content-Security-Policy" in headers,"CSP missing")
                static=re.search(rb'href="([^"]+app[^"]+\.css)"',catalog).group(1).decode()
                require(anonymous.request(static)[0]==200,"Static CSS unavailable")
                cart=buyer.json("/api/cart/",{"product_id":1,"quantity":4})
                payload={"warehouse_id":1,"shipping_address":"100 Market Street, Receiving Bay A","cart_version":cart["version"]}
                key={"Idempotency-Key":"smoke-real-http-checkout"}
                order=buyer.json("/api/checkout/",payload,201,key)
                repeated=buyer.json("/api/checkout/",payload,200,key)
                require(order["id"]==repeated["id"] and repeated["replayed"],"Checkout replay duplicated order")
                require(order["status"]=="awaiting_approval","Approval threshold bypassed")
                path="/api/orders/"+order["id"]+"/action/"
                sessions["manager"].json(path,{"action":"approve"})
                pending=buyer.json("/api/orders/"+order["id"]+"/")
                require(pending["status"]=="queued","Queue boundary not visible")
                command("worker","--drain")
                confirmed=buyer.json("/api/orders/"+order["id"]+"/")
                require(confirmed["status"]=="confirmed","Worker failed to confirm purchase")
                for action in ("pack","ship","deliver"): sessions["warehouse"].json(path,{"action":action})
                status,detail,_=sessions["finance"].request("/orders/"+order["id"]+"/")
                invoice_id=re.search(rb'/api/invoices/(\d+)/payment/',detail).group(1).decode()
                sessions["finance"].json("/api/invoices/"+invoice_id+"/payment/",{"reference":"HTTP-SMOKE-PAY-001"})
                case=buyer.json(path,{"action":"return","reason":"Branch deployment cancelled"},201)
                sessions["warehouse"].json("/api/returns/"+str(case["id"])+"/",{"action":"receive"})
                sessions["finance"].json("/api/returns/"+str(case["id"])+"/",{"action":"refund","reference":"HTTP-SMOKE-REFUND-001"})
                command("worker","--drain")
                final=buyer.json("/api/orders/"+order["id"]+"/")
                require(final["status"]=="refunded","Return lifecycle incomplete")
                sessions["rival"].json("/api/orders/"+order["id"]+"/",expected=404)
                require(buyer.request("/operations/")[0]==403,"Role boundary failed")
                require(anonymous.request("/metrics")[0]==401,"Metrics exposed without token")
                require(anonymous.request("/metrics",headers={"Authorization":"Bearer "+env["METRICS_TOKEN"]})[0]==200,"Metrics scrape failed")
                for path in ("/","/catalog/","/orders/","/approvals/","/fulfillment/","/inventory/","/finance/","/returns/","/operations/","/audit/","/notifications/"):
                    require(sessions["operator"].request(path)[0]==200,"Workspace page failed: "+path)
                report=json.loads(command("reconcile"));require(report["passed"],"Business reconciliation failed")
                with sqlite3.connect(db) as connection:
                    count=connection.execute("SELECT count(*) FROM commerce_order WHERE idempotency_key=?",("smoke-real-http-checkout",)).fetchone()[0]
                    require(count==1,"Duplicate persisted purchase")
                preparation=command("lab_scenario","prepare")
                fault_order=re.search(r"Investigate order ([0-9a-f-]{36})",preparation).group(1)
                command("worker","--drain")
                with sqlite3.connect(db) as connection:
                    failed=connection.execute("SELECT id,status FROM commerce_outboxevent WHERE order_id=?",(fault_order.replace("-",""),)).fetchone()
                require(failed[1]=="retry","Incident did not reach the expected failed attempt")
                command("lab_scenario","repair","--order",fault_order)
                sessions["operator"].json("/api/outbox/"+str(uuid.UUID(failed[0]))+"/replay/",{})
                command("worker","--drain")
                recovered=buyer.json("/api/orders/"+fault_order+"/")
                require(recovered["status"]=="confirmed","Incident recovery failed")
                backup=json.loads(command("recovery_check"))
                require(backup["passed"],"Isolated backup/restore failed")
                restored_report=json.loads(command("reconcile",database=ROOT/".local"/"recovery"/backup["restored"]))
                require(restored_report["passed"],"Restored business records failed reconciliation")
                print(json.dumps({"timestamp":datetime.now(timezone.utc).isoformat(),"passed":True,
                    "transport":"real HTTP via loopback Gunicorn","database":"temporary SQLite",
                    "journey":"checkout -> approval -> worker invoice -> pack -> ship -> deliver -> payment -> return -> restock -> refund",
                    "checks":["cookie login for 6 roles","CSRF-protected mutations","checkout replay",
                              "tenant 404","role 403","metrics authentication","static CSS","11 workspace pages","business reconciliation",
                              "HC-01 failed attempt and repair/replay","SQLite backup/restore integrity and counts","restored business reconciliation"],
                    "recovery_evidence":backup,
                    "browser_javascript_executed":False,"aws_calls":0},indent=2))
            finally:
                server.terminate()
                try: server.wait(timeout=10)
                except subprocess.TimeoutExpired: server.kill();server.wait()
if __name__=="__main__": run()
