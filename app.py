import tkinter as tk
from tkinter import ttk, scrolledtext
import meshtastic
import meshtastic.serial_interface
from pubsub import pub
import time
import requests
from datetime import datetime
import json
import threading
import serial.tools.list_ports

class MeshtasticTelemetryApp:
    def __init__(self, master):
        self.master = master
        master.title("Meshtastic Telemetry Harbor Integration")
        master.geometry("400x600")
        master.resizable(False, False)

        self.create_widgets()
        self.interface = None
        self.is_running = False

    def create_widgets(self):
        frame = ttk.Frame(self.master, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # API Key
        ttk.Label(frame, text="API Key:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.api_key = ttk.Entry(frame, width=30)
        self.api_key.grid(row=0, column=1, padx=5, pady=5)

        # Batch Endpoint
        ttk.Label(frame, text="Batch Endpoint:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.batch_endpoint = ttk.Entry(frame, width=30)
        self.batch_endpoint.grid(row=1, column=1, padx=5, pady=5)

        # COM Port
        ttk.Label(frame, text="COM Port:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.com_ports = self.get_available_ports()
        self.com_port = ttk.Combobox(frame, values=self.com_ports, width=27)
        if self.com_ports:
            self.com_port.set(self.com_ports[0])
        self.com_port.grid(row=2, column=1, padx=5, pady=5)

        # Pushing Rate
        #ttk.Label(frame, text="Pushing Rate (s):").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        #self.pushing_rate = ttk.Entry(frame, width=30)
        #self.pushing_rate.insert(0, "1")
        #self.pushing_rate.grid(row=3, column=1, padx=5, pady=5)
        self.pushing_rate = 300
        # Start/Stop Button
        self.start_stop_button = ttk.Button(frame, text="Start", command=self.toggle_data_collection)
        self.start_stop_button.grid(row=4, column=0, columnspan=2, pady=10)

        # Log Display
        self.log_display = scrolledtext.ScrolledText(frame, width=45, height=20)
        self.log_display.grid(row=5, column=0, columnspan=2, padx=5, pady=5)

    def get_available_ports(self):
        return [port.device for port in serial.tools.list_ports.comports()]

    def log(self, message):
        self.log_display.insert(tk.END, f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
        self.log_display.see(tk.END)

    def toggle_data_collection(self):
        if not self.is_running:
            self.start_data_collection()
        else:
            self.stop_data_collection()

    def start_data_collection(self):
        self.is_running = True
        self.start_stop_button.config(text="Stop")
        self.log("Starting data collection...")
        
        try:
            self.interface = meshtastic.serial_interface.SerialInterface(devPath=self.com_port.get())
            self.log("Connected to Meshtastic device")
            
            threading.Thread(target=self.collect_and_send_data, daemon=True).start()
        except Exception as e:
            self.log(f"Error connecting to Meshtastic device: {str(e)}")
            self.stop_data_collection()

    def stop_data_collection(self):
        self.is_running = False
        self.start_stop_button.config(text="Start")
        self.log("Stopping data collection...")
        
        if self.interface:
            self.interface.close()
            self.interface = None
            self.log("Meshtastic interface closed")

    def collect_and_send_data(self):
        while self.is_running:
            try:
                self.process_nodes()
                time.sleep(float(self.pushing_rate))
            except Exception as e:
                self.log(f"Error during data collection: {str(e)}")
                self.stop_data_collection()
                break

    def process_nodes(self):
        all_nodes = self.interface.nodes
        
        for node_id, node in all_nodes.items():
            current_time = datetime.utcnow().isoformat() + "Z"
            node_data = []
            
            self.log(f"Processing Node ID: {node_id}")
            
            user_info = node.get('user', {})
            self.log(f"  Name: {user_info.get('longName', 'Unknown')}")
            self.log(f"  Short Name: {user_info.get('shortName', 'Unknown')}")
            self.log(f"  Hardware Model: {user_info.get('hwModel', 'Unknown')}")
            
            position = node.get('position', {})
            if position:
                self.log(f"  Position: Lat {position.get('latitude', 'N/A')}, Lon {position.get('longitude', 'N/A')}")
                node_data.extend([
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "Lat", "value": position.get('latitude', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "Long", "value": position.get('longitude', 0)}
                ])
            
            self.log(f"  Last Heard: {node.get('lastHeard', 'N/A')}")
            
            # Process telemetry data
            self.log("  Telemetry Data:")
            device_metrics = node.get('deviceMetrics', {})
            if device_metrics:
                self.log(f"    Battery Level: {device_metrics.get('batteryLevel', 'N/A')}%")
                self.log(f"    Voltage: {device_metrics.get('voltage', 'N/A')}V")
                self.log(f"    Channel Utilization: {device_metrics.get('channelUtilization', 'N/A')}%")
                self.log(f"    Air Util TX: {device_metrics.get('airUtilTx', 'N/A')}%")
                node_data.extend([
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "BatteryLevel", "value": device_metrics.get('batteryLevel', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "Voltage", "value": device_metrics.get('voltage', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "ChannelUtilization", "value": device_metrics.get('channelUtilization', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "AirUtilTX", "value": device_metrics.get('airUtilTx', 0)}
                ])
            
            env_metrics = node.get('environmentMetrics', {})
            if env_metrics:
                self.log(f"    Temperature: {env_metrics.get('temperature', 'N/A')}°C")
                self.log(f"    Relative Humidity: {env_metrics.get('relativeHumidity', 'N/A')}%")
                self.log(f"    Barometric Pressure: {env_metrics.get('barometricPressure', 'N/A')} hPa")
                node_data.extend([
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "Temperature", "value": env_metrics.get('temperature', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "RelativeHumidity", "value": env_metrics.get('relativeHumidity', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "BarometricPressure", "value": env_metrics.get('barometricPressure', 0)}
                ])
            
            air_metrics = node.get('airQualityMetrics', {})
            if air_metrics:
                self.log(f"    Air Quality: {air_metrics.get('airQuality', 'N/A')}")
                node_data.append({"time": current_time, "ship_id": str(node_id), "cargo_id": "AirQuality", "value": air_metrics.get('airQuality', 0)})
            
            power_metrics = node.get('powerMetrics', {})
            if power_metrics:
                self.log(f"    Power: {power_metrics.get('power', 'N/A')}W")
                self.log(f"    Voltage: {power_metrics.get('voltage', 'N/A')}V")
                self.log(f"    Current: {power_metrics.get('current', 'N/A')}A")
                node_data.extend([
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "Power", "value": power_metrics.get('power', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "PowerVoltage", "value": power_metrics.get('voltage', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "Current", "value": power_metrics.get('current', 0)}
                ])
            
            # Send batch request to Telemetry Harbor for this node
            if node_data:
                self.send_telemetry_data(node_data)
                time.sleep(2)
            else:
                self.log(f"No data to send for Node ID: {node_id}")

    def send_telemetry_data(self, data):
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key.get()
        }
        
        try:
            response = requests.post(self.batch_endpoint.get(), headers=headers, json=data)
            response.raise_for_status()
            self.log(f"Data for node {data[0]['ship_id']} successfully sent to Telemetry Harbor")
        except requests.exceptions.RequestException as e:
            self.log(f"Failed to send data for node {data[0]['ship_id']} to Telemetry Harbor. Error: {str(e)}")

def main():
    root = tk.Tk()
    app = MeshtasticTelemetryApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
