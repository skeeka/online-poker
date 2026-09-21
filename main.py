from poker.server import Server
import asyncio

s = Server()
asyncio.run(s.main(),debug=False)
