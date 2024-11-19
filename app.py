import tkinter as tk
from tkinter import ttk, scrolledtext, font, messagebox
import meshtastic
import meshtastic.serial_interface
from pubsub import pub
import time
import requests
from datetime import datetime
import json
import threading
import serial.tools.list_ports
import serial

class MeshtasticTelemetryApp:
    def __init__(self, master):
        self.master = master
        master.title("Meshtastic Telemetry Harbor")
        master.geometry("800x450")
        master.resizable(False, False)

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TFrame", background="#f0f0f0")
        self.style.configure("TLabel", background="#f0f0f0", font=("Helvetica", 10))
        self.style.configure("TEntry", font=("Helvetica", 10))
        self.style.configure("TButton", font=("Helvetica", 10, "bold"))

        self.create_widgets()
        self.interface = None
        self.is_running = False

    def create_widgets(self):
        main_frame = ttk.Frame(self.master, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        left_frame = ttk.Frame(main_frame, padding="0 0 10 0")
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Left frame widgets
        ttk.Label(left_frame, text="API Key:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.api_key = ttk.Entry(left_frame, width=30)
        self.api_key.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(left_frame, text="Batch Endpoint:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.batch_endpoint = ttk.Entry(left_frame, width=30)
        self.batch_endpoint.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(left_frame, text="COM Port:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.com_ports = self.get_available_ports()
        self.com_port = ttk.Combobox(left_frame, values=self.com_ports, width=27)
        self.com_port.grid(row=2, column=1, padx=5, pady=5)

        self.refresh_button = ttk.Button(left_frame, text="Refresh COM Ports", command=self.refresh_com_ports)
        self.refresh_button.grid(row=3, column=0, columnspan=2, pady=10)

        self.start_stop_button = ttk.Button(left_frame, text="Start", command=self.toggle_data_collection)
        self.start_stop_button.grid(row=4, column=0, columnspan=2, pady=10)

        # Right frame widget (Log Display)
        log_font = font.Font(family="Consolas", size=9)
        self.log_display = scrolledtext.ScrolledText(right_frame, width=60, height=22, font=log_font, bg="#282c34", fg="#abb2bf")
        self.log_display.pack(expand=True, fill=tk.BOTH)

    def get_available_ports(self):
        return [port.device for port in serial.tools.list_ports.comports()]

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if level == "ERROR":
            color = "#e06c75"  # Red for errors
        elif level == "SUCCESS":
            color = "#98c379"  # Green for success
        else:
            color = "#abb2bf"  # Default color

        self.log_display.insert(tk.END, f"{timestamp} - ", "timestamp")
        self.log_display.insert(tk.END, f"{message}\n", level)
        self.log_display.tag_config("timestamp", foreground="#61afef")
        self.log_display.tag_config(level, foreground=color)
        self.log_display.see(tk.END)

    def toggle_data_collection(self):
        if not self.is_running:
            self.start_data_collection()
        else:
            self.stop_data_collection()

    def start_data_collection(self):
        self.is_running = True
        self.start_stop_button.config(text="Stop")
        self.log("Starting data collection...", "INFO")
        
        try:
            # Attempt to connect with a timeout
            connection_thread = threading.Thread(target=self.connect_to_device)
            connection_thread.start()
            connection_thread.join(timeout=10)  # Wait for 10 seconds

            if connection_thread.is_alive():
                raise TimeoutError("Connection attempt timed out")

            if self.interface is None:
                raise ConnectionError("Failed to establish connection")

            self.log("Connected to Meshtastic device", "SUCCESS")
            threading.Thread(target=self.collect_and_send_data, daemon=True).start()
        except (TimeoutError, ConnectionError, serial.SerialException) as e:
            self.log(f"Error connecting to Meshtastic device: {str(e)}", "ERROR")
            self.stop_data_collection()
            messagebox.showerror("Connection Error", f"Failed to connect to the device on {self.com_port.get()}. Please check the COM port and try again.")

    def connect_to_device(self):
        try:
            self.interface = meshtastic.serial_interface.SerialInterface(devPath=self.com_port.get())
        except Exception as e:
            self.log(f"Error in connection thread: {str(e)}", "ERROR")
            self.interface = None

    def stop_data_collection(self):
        self.is_running = False
        self.start_stop_button.config(text="Start")
        self.log("Stopping data collection...", "INFO")
        
        if self.interface:
            self.interface.close()
            self.interface = None
            self.log("Meshtastic interface closed", "INFO")

    def collect_and_send_data(self):
        while self.is_running:
            try:
                self.process_nodes()
                time.sleep(300)  # 5 minutes
            except Exception as e:
                self.log(f"Error during data collection: {str(e)}", "ERROR")
                self.stop_data_collection()
                break

    def process_nodes(self):
        all_nodes = self.interface.nodes
        
        for node_id, node in all_nodes.items():
            current_time = datetime.utcnow().isoformat() + "Z"
            node_data = []
            
            self.log(f"Processing Node ID: {node_id}", "INFO")
            
            user_info = node.get('user', {})
            self.log(f"  Name: {user_info.get('longName', 'Unknown')}", "INFO")
            self.log(f"  Short Name: {user_info.get('shortName', 'Unknown')}", "INFO")
            self.log(f"  Hardware Model: {user_info.get('hwModel', 'Unknown')}", "INFO")
            
            position = node.get('position', {})
            if position:
                self.log(f"  Position: Lat {position.get('latitude', 'N/A')}, Lon {position.get('longitude', 'N/A')}", "INFO")
                node_data.extend([
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "Lat", "value": position.get('latitude', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "Long", "value": position.get('longitude', 0)}
                ])
            
            self.log(f"  Last Heard: {node.get('lastHeard', 'N/A')}", "INFO")
            
            # Process telemetry data
            self.log("  Telemetry Data:", "INFO")
            device_metrics = node.get('deviceMetrics', {})
            if device_metrics:
                self.log(f"    Battery Level: {device_metrics.get('batteryLevel', 'N/A')}%", "INFO")
                self.log(f"    Voltage: {device_metrics.get('voltage', 'N/A')}V", "INFO")
                self.log(f"    Channel Utilization: {device_metrics.get('channelUtilization', 'N/A')}%", "INFO")
                self.log(f"    Air Util TX: {device_metrics.get('airUtilTx', 'N/A')}%", "INFO")
                node_data.extend([
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "BatteryLevel", "value": device_metrics.get('batteryLevel', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "Voltage", "value": device_metrics.get('voltage', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "ChannelUtilization", "value": device_metrics.get('channelUtilization', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "AirUtilTX", "value": device_metrics.get('airUtilTx', 0)}
                ])
            
            env_metrics = node.get('environmentMetrics', {})
            if env_metrics:
                self.log(f"    Temperature: {env_metrics.get('temperature', 'N/A')}°C", "INFO")
                self.log(f"    Relative Humidity: {env_metrics.get('relativeHumidity', 'N/A')}%", "INFO")
                self.log(f"    Barometric Pressure: {env_metrics.get('barometricPressure', 'N/A')} hPa", "INFO")
                node_data.extend([
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "Temperature", "value": env_metrics.get('temperature', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "RelativeHumidity", "value": env_metrics.get('relativeHumidity', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "BarometricPressure", "value": env_metrics.get('barometricPressure', 0)}
                ])
            
            air_metrics = node.get('airQualityMetrics', {})
            if air_metrics:
                self.log(f"    Air Quality: {air_metrics.get('airQuality', 'N/A')}", "INFO")
                node_data.append({"time": current_time, "ship_id": str(node_id), "cargo_id": "AirQuality", "value": air_metrics.get('airQuality', 0)})
            
            power_metrics = node.get('powerMetrics', {})
            if power_metrics:
                self.log(f"    Power: {power_metrics.get('power', 'N/A')}W", "INFO")
                self.log(f"    Voltage: {power_metrics.get('voltage', 'N/A')}V", "INFO")
                self.log(f"    Current: {power_metrics.get('current', 'N/A')}A", "INFO")
                node_data.extend([
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "Power", "value": power_metrics.get('power', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "PowerVoltage", "value": power_metrics.get('voltage', 0)},
                    {"time": current_time, "ship_id": str(node_id), "cargo_id": "Current", "value": power_metrics.get('current', 0)}
                ])
            
            # Send batch request to Telemetry Harbor for this node
            if node_data:
                self.send_telemetry_data(node_data)
                time.sleep(2)  # 2-second delay after each request
            else:
                self.log(f"No data to send for Node ID: {node_id}", "INFO")

    def send_telemetry_data(self, data):
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key.get()
        }
        
        try:
            response = requests.post(self.batch_endpoint.get(), headers=headers, json=data)
            response.raise_for_status()
            self.log(f"Data for node {data[0]['ship_id']} successfully sent to Telemetry Harbor", "SUCCESS")
        except requests.exceptions.RequestException as e:
            self.log(f"Failed to send data for node {data[0]['ship_id']} to Telemetry Harbor. Error: {str(e)}", "ERROR")

    def refresh_com_ports(self):
        self.com_ports = self.get_available_ports()
        self.com_port['values'] = self.com_ports
        if self.com_ports:
            self.com_port.set(self.com_ports[0])
        self.log("COM ports refreshed", "INFO")

def main():
    root = tk.Tk()
    app = MeshtasticTelemetryApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
