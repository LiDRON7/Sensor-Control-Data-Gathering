import psutil
import time
import csv
from datetime import datetime

# Configuration
LOG_FILE = "oak_d_pro_resource_usage.csv"
INTERVAL = 1  # Log every 1 second. Adjust as needed.
DURATION = 300  # Log for 300 seconds (5 minutes). Adjust as needed.

def celsius_to_fahrenheit(celsius):
    """Convert Celsius to Fahrenheit"""
    if celsius == -1:
        return -1
    return (celsius * 9/5) + 32

def log_resources():
    # Open the CSV file for writing
    with open(LOG_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        # Header rows - changed to show Fahrenheit
        writer.writerow(['Timestamp', 'CPU_Usage_%', 'Memory_Usage_%', 'Memory_Used_MB', 'CPU_Temperature_C', 'CPU_Temperature_F'])

        start_time = time.time()
        while time.time() - start_time < DURATION:
            # Current timestamp
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # CPU and Memory Usage using psutil
            cpu_percent = psutil.cpu_percent(interval=1)  # Get CPU % over 1 sec
            memory_info = psutil.virtual_memory()
            mem_used_mb = memory_info.used / (1024 * 1024)  # Convert bytes to MB
            mem_percent = memory_info.percent

            # Raspberry Pi Specific: CPU Temperature 
            # This is a common way to read temp on a Pi.
            try:
                with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                    temp_raw = f.read().strip()
                    cpu_temp_c = int(temp_raw) / 1000.0  # Convert to Celsius
                    cpu_temp_f = celsius_to_fahrenheit(cpu_temp_c)  # Convert to Fahrenheit
            except FileNotFoundError:
                cpu_temp_c = -1  # Indicate temperature not available
                cpu_temp_f = -1

            # Write the data row - now including Fahrenheit
            writer.writerow([timestamp, cpu_percent, mem_percent, round(mem_used_mb, 2), round(cpu_temp_c, 2), round(cpu_temp_f, 2)])
            print(f"Logged: CPU={cpu_percent}%, Mem={mem_percent}%, Temp={round(cpu_temp_c, 2)}°C / {round(cpu_temp_f, 2)}°F") # Show both temps

if __name__ == "__main__":
    print(f"Starting resource monitoring for {DURATION} seconds. Logging to {LOG_FILE}")
    log_resources()
    print("Monitoring finished.")
