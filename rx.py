import asyncio, websockets, json, socket

HUB = "ws://192.168.1.148:8000/ws/nodes/"
NAME = socket.gethostname()

async def run():
    async with websockets.connect(HUB) as ws:
        reg = {"type": "register", "role": "RX", "name": NAME}
        await ws.send(json.dumps(reg))
        print("Registered RX:", reg)

        async def heartbeat():
            while True:
                hb = {"type": "heartbeat", "role": "RX", "name": NAME, "status": "ok"}
                await ws.send(json.dumps(hb))
                await asyncio.sleep(5)

        asyncio.create_task(heartbeat())

        # Listen for commands
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            if data.get("type") == "route":
                print(f"[RX] Got route command: connect to {data['from']}")
            else:
                print("[RX] Unknown command:", data)

asyncio.run(run())
