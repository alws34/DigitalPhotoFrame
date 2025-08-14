import psutil
import time


class StatsService:
    def __init__(self) -> None:
        self.cached = "CPU: N/A\nRAM: N/A\nCPU Temp: N/A"

    @staticmethod
    def _cpu_temp() -> str:
        try:
            temps = psutil.sensors_temperatures().get("cpu_thermal", [])
            return f"{round(temps[0].current, 1)}" if temps else "N/A"
        except Exception:
            return "N/A"

    def collect_once(self) -> str:
        cpu_usage = int(psutil.cpu_percent(interval=1))
        ram = psutil.virtual_memory()
        ram_used = ram.used // (1024 * 1024)
        ram_total = ram.total // (1024 * 1024)
        ram_percent = ram.percent
        cpu_temp = self._cpu_temp()
        return f"CPU: {cpu_usage}%\nRAM: {ram_percent}% ({ram_used}/{ram_total}MB)\nCPU Temp: {cpu_temp}C"

    def loop_update(self, stop_flag, interval_sec: int = 1) -> None:
        while not stop_flag():
            try:
                self.cached = self.collect_once()
            except Exception:
                pass
            time.sleep(interval_sec)
