import MetaTrader5 as mt5
import time

class MT5Connector:
    def __init__(self):
        self.connected = False
        self.login = None
        self.password = None
        self.server = None

    def connect(self, login, password, server):
        self.login = login
        self.password = password
        self.server = server
        if not mt5.initialize(server, login=int(login), password=password):
            return False, mt5.last_error()
        self.connected = True
        return True, "Connected"

    def is_connected(self):
        return mt5.initialize() or self.connected

    def auto_reconnect(self):
        for _ in range(10):
            if self.is_connected():
                return True
            time.sleep(5)
            mt5.shutdown()
            mt5.initialize(self.server, login=int(self.login), password=self.password)
        return self.is_connected()

    def shutdown(self):
        mt5.shutdown()
        self.connected = False
