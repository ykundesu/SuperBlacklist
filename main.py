from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse, JSONResponse
import hashlib
import httpx
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from bson.objectid import ObjectId
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import json

DATABASE_host = os.environ.get("BLACKLIST_DATABASE_host")
DATABASE_port = int(os.environ.get("BLACKLIST_DATABASE_port"))
DATABASE_username = os.environ.get("BLACKLIST_DATABASE_username")
DATABASE_password = os.environ.get("BLACKLIST_DATABASE_password")
DATABASE_authsource = "admin"

cf_token = os.environ.get("BLACKLIST_CLOUDFLARE_TOKEN")
cf_zone = os.environ.get("BLACKLIST_CLOUDFLARE_ZONE")
Blacklist_APIBase: str = "https://blacklist.supernewroles.com/api/"

client = None
BlacklistBase = None
BlacklistBanned = None
BlacklistPass = None

def initdatabase():
    global client
    global BlacklistBase
    global BlacklistBanned
    client = MongoClient(host=DATABASE_host, port=DATABASE_port,
                         username = DATABASE_username,
                         password = DATABASE_password)
    BlacklistBase = client["Blacklist"]
    BlacklistBanned = BlacklistBase["Banned"]
    print("authed MongoDB")
initdatabase()

POOL = ThreadPoolExecutor()

app = FastAPI()
@app.get("/api/get_list")
async def get_list(isNew: str = None):
    (blockedPlayers, blockedPlayersPUID) = await getblockedplayers()
    blackdetail = f"{json.dumps(blockedPlayers)},{json.dumps(blockedPlayersPUID)}"
    hashcode: str = await tohash(blackdetail)
    if isNew:
        return {"code":-1,"hash":hashcode,"blackData":blackdetail}
    return PlainTextResponse(json.dumps({"code":-1,"hash":hashcode,"blockedPlayers":blockedPlayers,"blockedPlayersPUID":blockedPlayersPUID}), headers={"content-type":"application/json"})
@app.get("/api/get_hash")
async def get_hash():
    (blockedPlayers, blockedPlayersPUID) = await getblockedplayers()
    blackdetail = f"{json.dumps(blockedPlayers)},{json.dumps(blockedPlayersPUID)}"
    hashcode: str = await tohash(blackdetail)
    return PlainTextResponse(hashcode)
async def tohash(text):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(POOL, tohash_sync, text)
def tohash_sync(text):
    return hashlib.sha256(text.encode()).hexdigest()
async def parge_cdn_cache():
    headers = {'Authorization': 'Bearer '+cf_token,"Content-Type": "application/json"}
    request_data={"files":[Blacklist_APIBase+"get_list", 
                           Blacklist_APIBase+"get_list?hash=true",
                           Blacklist_APIBase+"get_list?isNew=a",
                           Blacklist_APIBase+"get_hash"
                           ]}
    async with httpx.AsyncClient() as client:
        response = await client.post("https://api.cloudflare.com/client/v4/zones/"+cf_zone+"/purge_cache",
                                    headers=headers,json=request_data)
async def getblockedplayers():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(POOL, getblockedplayers_sync)
def getblockedplayers_sync():
    query = {}
    all_items = BlacklistBanned.find()
    players = []
    playersPUID = []
    for item in all_items:
        IsLegacy = item["Legacy"]
        data = {}
        data["AddedBy"] = item["Added_by"]
        data["Reason"] = {}
        data["Reason"]["Code"] = str(item["ReasonCode"]) + str(item["_id"])
        if IsLegacy:
            data["Reason"]["Code"] += "_LG"
        data["Reason"]["Title"] = item["ReasonTitle"]
        data["Reason"]["Description"] = item["ReasonDescription"]
        if "EndBanTime" in item:
            data["EndBanTime"] = item["EndBanTime"]
        IsPUID = item.get("dataType", "FriendCode") == "PUID"
        if IsPUID:
            data["PUID"] = tohash_sync(item["Code"])
            playersPUID.append(data)
        else:
            data["FriendCode"] = tohash_sync(item["Code"])
            players.append(data)
    return (players, playersPUID)