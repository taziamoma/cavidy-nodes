import asyncio, websockets, json, socket

HUB = "ws://192.168.1.148:8000/ws/test/"  # change to your Hub Pi IP
NAME = socket.gethostname()

async def run():
    async with websockets.connect(HUB) as ws:
        # Register as TX
        await ws.send(json.dumps({"type": "register", "role": "TX", "name": NAME}))
        print("Registered TX")

        while True:
            # Send heartbeat
            await ws.send(json.dumps({"type": "heartbeat", "role": "TX", "name": NAME, "status": "ok"}))
            await asyncio.sleep(5)

asyncio.run(run())