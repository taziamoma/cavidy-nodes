import asyncio, websockets, json, socket

HUB = "ws://192.168.1.148:8000/ws/test/"  # replace with your hub IP
NAME = socket.gethostname()

async def run():
    try:
        async with websockets.connect(HUB) as ws:
            # Register once
            reg_msg = {"type": "register", "role": "TX", "name": NAME}
            await ws.send(json.dumps(reg_msg))
            print("Registered TX:", reg_msg)

            # Heartbeat loop
            while True:
                hb_msg = {"type": "heartbeat", "role": "TX", "name": NAME, "status": "ok"}
                await ws.send(json.dumps(hb_msg))
                print("Sent heartbeat:", hb_msg)
                await asyncio.sleep(5)

    except Exception as e:
        print("Connection error:", e)

asyncio.run(run())
