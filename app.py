import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import meshtastic
import meshtastic.serial_interface
from pubsub import pub
import time
import requests
from datetime import datetime
import json
import threading
import serial.tools.list_ports
import copy

class MeshtasticTelemetryApp:
    def __init__(self, master):
        self.master = master
        master.title("Meshtastic Telemetry Harbor Integration")
        master.geometry("700x700")  # Increased window size
        master.minsize(600, 600)    # Set minimum size
        
        # Configure the grid to expand properly
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        # Set theme colors
        self.bg_color = "#f0f4f8"
        self.accent_color = "#3498db"
        self.master.configure(bg=self.bg_color)
        
        # Create a style
        self.style = ttk.Style()
        self.style.configure("TFrame", background=self.bg_color)
        self.style.configure("TLabel", background=self.bg_color, font=("Arial", 10))
        self.style.configure("TButton", font=("Arial", 10, "bold"))
        self.style.configure("Header.TLabel", font=("Arial", 14, "bold"))
        
        self.create_widgets()
        self.interface = None
        self.is_running = False
        self.nodes_lock = threading.Lock()
        self.node_data_cache = {}

    def create_widgets(self):
        main_frame = ttk.Frame(self.master, padding="20", style="TFrame")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=3)
        
        # Header
        header_label = ttk.Label(main_frame, text="Meshtastic Telemetry Harbor Integration", style="Header.TLabel")
        header_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Connection Settings Frame
        settings_frame = ttk.LabelFrame(main_frame, text="Connection Settings", padding="10")
        settings_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        settings_frame.columnconfigure(1, weight=1)
        
        # API Key
        ttk.Label(settings_frame, text="API Key:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.api_key = ttk.Entry(settings_frame, width=50)
        self.api_key.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)

        # Batch Endpoint
        ttk.Label(settings_frame, text="Batch Endpoint:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.batch_endpoint = ttk.Entry(settings_frame, width=50)
        self.batch_endpoint.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)

        # COM Port with refresh button
        port_frame = ttk.Frame(settings_frame)
        port_frame.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        port_frame.columnconfigure(0, weight=1)
        
        ttk.Label(settings_frame, text="COM Port:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.com_ports = self.get_available_ports()
        self.com_port = ttk.Combobox(port_frame, values=self.com_ports, width=40)
        if self.com_ports:
            self.com_port.set(self.com_ports[0])
        self.com_port.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        refresh_button = ttk.Button(port_frame, text="⟳", width=3, command=self.refresh_ports)
        refresh_button.grid(row=0, column=1, padx=(5, 0))

        # Data Collection Settings Frame
        collection_frame = ttk.LabelFrame(main_frame, text="Data Collection Settings", padding="10")
        collection_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        collection_frame.columnconfigure(1, weight=1)
        
        # Pushing Rate
        ttk.Label(collection_frame, text="Pushing Rate (seconds):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.pushing_rate_var = tk.StringVar(value="300")
        self.pushing_rate_entry = ttk.Entry(collection_frame, textvariable=self.pushing_rate_var, width=10)
        self.pushing_rate_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)

        # Control Buttons Frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=(0, 10))
        
        # Start/Stop Button
        self.start_stop_button = ttk.Button(button_frame, text="Start Collection", command=self.toggle_data_collection, width=20)
        self.start_stop_button.grid(row=0, column=0, padx=5)
        
        # Clear Log Button
        self.clear_log_button = ttk.Button(button_frame, text="Clear Log", command=self.clear_log, width=20)
        self.clear_log_button.grid(row=0, column=1, padx=5)

        # Log Display Frame
        log_frame = ttk.LabelFrame(main_frame, text="Log Output", padding="10")
        log_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        
        # Log Display - made wider and with more height
        self.log_display = scrolledtext.ScrolledText(log_frame, width=80, height=25, wrap=tk.WORD)
        self.log_display.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        # Status Bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E))
        
        # Configure main frame to expand
        main_frame.rowconfigure(4, weight=1)

    def refresh_ports(self):
        """Refresh the list of available COM ports"""
        self.com_ports = self.get_available_ports()
        self.com_port['values'] = self.com_ports
        if self.com_ports:
            self.com_port.set(self.com_ports[0])
        self.log("COM ports refreshed")

    def get_available_ports(self):
        """Get a list of available COM ports"""
        return [port.device for port in serial.tools.list_ports.comports()]

    def clear_log(self):
        """Clear the log display"""
        self.log_display.delete(1.0, tk.END)
        self.log("Log cleared")

    def log(self, message):
        """Add a timestamped message to the log display"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_display.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_display.see(tk.END)

    def toggle_data_collection(self):
        """Toggle between starting and stopping data collection"""
        if not self.is_running:
            self.start_data_collection()
        else:
            self.stop_data_collection()

    def start_data_collection(self):
        """Start collecting data from Meshtastic device"""
        # Validate inputs
        if not self.api_key.get().strip():
            messagebox.showerror("Error", "API Key is required")
            return
            
        if not self.batch_endpoint.get().strip():
            messagebox.showerror("Error", "Batch Endpoint is required")
            return
            
        if not self.com_port.get():
            messagebox.showerror("Error", "COM Port is required")
            return
            
        try:
            self.pushing_rate = int(self.pushing_rate_var.get())
            if self.pushing_rate < 10:
                messagebox.showwarning("Warning", "Pushing rate is very low. This may cause performance issues.")
        except ValueError:
            messagebox.showerror("Error", "Pushing Rate must be a number")
            return
        
        self.is_running = True
        self.start_stop_button.config(text="Stop Collection")
        self.status_var.set("Running")
        self.log("Starting data collection...")
        
        try:
            # Connect to Meshtastic device
            self.log(f"Connecting to Meshtastic device on {self.com_port.get()}...")
            self.interface = meshtastic.serial_interface.SerialInterface(devPath=self.com_port.get())
            self.log("Connected to Meshtastic device successfully")
            
            # Subscribe to receive messages
            pub.subscribe(self.on_receive, "meshtastic.receive")
            self.log("Subscribed to Meshtastic messages")
            
            # Start data collection thread
            threading.Thread(target=self.collect_and_send_data, daemon=True).start()
        except Exception as e:
            self.log(f"Error connecting to Meshtastic device: {str(e)}")
            messagebox.showerror("Connection Error", f"Failed to connect to Meshtastic device: {str(e)}")
            self.stop_data_collection()

    def on_receive(self, packet, interface):
        """Handle received messages from the mesh network"""
        try:
            self.log(f"Received packet: {packet['decoded']['portnum']}")
            # Process any real-time data if needed
        except Exception as e:
            self.log(f"Error processing received packet: {str(e)}")

    def stop_data_collection(self):
        """Stop collecting data from Meshtastic device"""
        self.is_running = False
        self.start_stop_button.config(text="Start Collection")
        self.status_var.set("Stopped")
        self.log("Stopping data collection...")
        
        if self.interface:
            try:
                pub.unsubscribe(self.on_receive, "meshtastic.receive")
                self.interface.close()
                self.log("Meshtastic interface closed")
            except Exception as e:
                self.log(f"Error closing interface: {str(e)}")
            finally:
                self.interface = None

    def collect_and_send_data(self):
        """Main loop for collecting and sending data"""
        while self.is_running:
            try:
                self.process_nodes()
                self.log(f"Waiting {self.pushing_rate} seconds until next data collection...")
                
                # Use a loop with small sleeps to allow for more responsive stopping
                for _ in range(self.pushing_rate):
                    if not self.is_running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                self.log(f"Error during data collection: {str(e)}")
                if not self.is_running:
                    break
                time.sleep(10)  # Wait a bit before retrying

    def process_nodes(self):
        """Process all nodes in the mesh network"""
        self.log("Starting node data collection...")
        
        try:
            # Make a deep copy of nodes to avoid issues with concurrent modification
            with self.nodes_lock:
                all_nodes = copy.deepcopy(self.interface.nodes)
            
            if not all_nodes:
                self.log("No nodes found in the mesh network")
                return
                
            self.log(f"Found {len(all_nodes)} nodes in the mesh network")
            
            for node_id, node in all_nodes.items():
                try:
                    self.process_single_node(node_id, node)
                except Exception as e:
                    self.log(f"Error processing node {node_id}: {str(e)}")
        except Exception as e:
            self.log(f"Error accessing nodes: {str(e)}")

    def safe_cast(self, value, to_type, default=None):
        """Safely cast a value to the specified type"""
        try:
            if value is None:
                return default
            if to_type is int:
                # First try direct conversion
                try:
                    return int(value)
                except (ValueError, TypeError):
                    # If direct conversion fails, try float first then convert to int
                    return int(float(value))
            elif to_type is float:
                return float(value)
            else:
                return to_type(value)
        except (ValueError, TypeError):
            self.log(f"Warning: Could not convert '{value}' to {to_type.__name__}, using default {default}")
            return default

    def create_data_point(self, time, ship_id, cargo_id, value, value_type=float):
        """Create a properly formatted data point with type casting"""
        # Skip if value can't be converted to a number
        converted_value = self.safe_cast(value, value_type)
        if converted_value is None:
            return None
            
        return {
            "time": str(time),
            "ship_id": str(ship_id),
            "cargo_id": str(cargo_id),
            "value": converted_value  # Keep as numeric value
        }

    def process_single_node(self, node_id, node):
        """Process a single node and send its data to Telemetry Harbor"""
        current_time = datetime.utcnow().isoformat() + "Z"
        node_data = []
        
        self.log(f"Processing Node ID: {node_id}")
        
        # Extract user information
        user_info = node.get('user', {})
        node_name = user_info.get('longName', f"Unknown-{node_id[:8]}")
        self.log(f"  Name: {node_name}")
        self.log(f"  Short Name: {user_info.get('shortName', 'Unknown')}")
        self.log(f"  Hardware Model: {user_info.get('hwModel', 'Unknown')}")
        
        # Skip node info as it's not numeric data
        # Process position data
        position = node.get('position', {})
        if position:
            lat = position.get('latitude')
            lon = position.get('longitude')
            alt = position.get('altitude')
            hdop = position.get('HDOP')
            sats = position.get('satsInView')
            
            self.log(f"  Position: Lat {lat}, Lon {lon}, Alt {alt}, HDOP {hdop}, Sats {sats}")
            
            if lat is not None and lon is not None:
                lat_point = self.create_data_point(current_time, node_name, "latitude", lat, float)
                lon_point = self.create_data_point(current_time, node_name, "longitude", lon, float)
                if lat_point: node_data.append(lat_point)
                if lon_point: node_data.append(lon_point)
            
            if alt is not None:
                alt_point = self.create_data_point(current_time, node_name, "altitude", alt, float)
                if alt_point: node_data.append(alt_point)
            
            if hdop is not None:
                hdop_point = self.create_data_point(current_time, node_name, "HDOP", hdop, float)
                if hdop_point: node_data.append(hdop_point)
            
            if sats is not None:
                sats_point = self.create_data_point(current_time, node_name, "satsInView", sats, int)
                if sats_point: node_data.append(sats_point)
        
        # Process last heard time
        last_heard = node.get('lastHeard', 0)
        if last_heard:
            last_heard_time = datetime.fromtimestamp(last_heard).strftime('%Y-%m-%d %H:%M:%S')
            self.log(f"  Last Heard: {last_heard_time}")
            last_heard_point = self.create_data_point(current_time, node_name, "LastHeard", last_heard, int)
            if last_heard_point: node_data.append(last_heard_point)
        
        # Process device metrics
        device_metrics = node.get('deviceMetrics', {})
        if device_metrics:
            self.log("  Device Metrics:")
            metrics_to_log = [
                ('batteryLevel', 'BatteryLevel', int, '%'),
                ('voltage', 'Voltage', float, 'V'),
                ('channelUtilization', 'ChannelUtilization', float, '%'),
                ('airUtilTx', 'AirUtilTX', float, '%'),
                ('airUtilRx', 'AirUtilRX', float, '%')
            ]
            
            for metric_key, cargo_id, value_type, unit in metrics_to_log:
                value = device_metrics.get(metric_key)
                if value is not None:
                    self.log(f"    {cargo_id}: {value}{unit}")
                    data_point = self.create_data_point(current_time, node_name, cargo_id, value, value_type)
                    if data_point: node_data.append(data_point)
        
        # Process environment metrics
        env_metrics = node.get('environmentMetrics', {})
        if env_metrics:
            self.log("  Environment Metrics:")
            metrics_to_log = [
                ('temperature', 'Temperature', float, '°C'),
                ('relativeHumidity', 'RelativeHumidity', float, '%'),
                ('barometricPressure', 'BarometricPressure', float, 'hPa'),
                ('gasResistance', 'GasResistance', float, 'Ω'),
                ('voltage', 'EnvVoltage', float, 'V'),
                ('current', 'EnvCurrent', float, 'A')
            ]
            
            for metric_key, cargo_id, value_type, unit in metrics_to_log:
                value = env_metrics.get(metric_key)
                if value is not None:
                    self.log(f"    {cargo_id}: {value}{unit}")
                    data_point = self.create_data_point(current_time, node_name, cargo_id, value, value_type)
                    if data_point: node_data.append(data_point)
        
        # Process air quality metrics
        air_metrics = node.get('airQualityMetrics', {})
        if air_metrics:
            self.log("  Air Quality Metrics:")
            metrics_to_log = [
                ('airQuality', 'AirQuality', int, ''),
                ('vocIndex', 'VOCIndex', int, ''),
                ('pm10Standard', 'PM10', float, 'μg/m³'),
                ('pm25Standard', 'PM25', float, 'μg/m³'),
                ('pm100Standard', 'PM100', float, 'μg/m³'),
                ('co2', 'CO2', int, 'ppm')
            ]
            
            for metric_key, cargo_id, value_type, unit in metrics_to_log:
                value = air_metrics.get(metric_key)
                if value is not None:
                    self.log(f"    {cargo_id}: {value}{unit}")
                    data_point = self.create_data_point(current_time, node_name, cargo_id, value, value_type)
                    if data_point: node_data.append(data_point)
        
        # Process power metrics
        power_metrics = node.get('powerMetrics', {})
        if power_metrics:
            self.log("  Power Metrics:")
            metrics_to_log = [
                ('power', 'Power', float, 'W'),
                ('voltage', 'PowerVoltage', float, 'V'),
                ('current', 'Current', float, 'A'),
                ('powerInDb', 'PowerInDb', float, 'dB')
            ]
            
            for metric_key, cargo_id, value_type, unit in metrics_to_log:
                value = power_metrics.get(metric_key)
                if value is not None:
                    self.log(f"    {cargo_id}: {value}{unit}")
                    data_point = self.create_data_point(current_time, node_name, cargo_id, value, value_type)
                    if data_point: node_data.append(data_point)
        
        # Process node info metrics
        node_info = node.get('nodeInfo', {})
        if node_info:
            self.log("  Node Info:")
            node_num = node_info.get('num')
            if node_num is not None:
                self.log(f"    Node Number: {node_num}")
                node_num_point = self.create_data_point(current_time, node_name, "NodeNumber", node_num, int)
                if node_num_point: node_data.append(node_num_point)
            
            role = node_info.get('role')
            if role is not None:
                self.log(f"    Role: {role}")
                role_point = self.create_data_point(current_time, node_name, "Role", role, int)
                if role_point: node_data.append(role_point)
        
        # Send batch request to Telemetry Harbor for this node
        if node_data:
            self.send_telemetry_data(node_data, node_name)
        else:
            self.log(f"No data to send for Node: {node_name}")

    def send_telemetry_data(self, data, node_name):
        """Send collected data to Telemetry Harbor"""
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key.get()
        }
        
        try:
            self.log(f"Sending {len(data)} data points for node {node_name} to Telemetry Harbor...")
            
            # Log the first few data points for debugging
            for i, point in enumerate(data[:3]):
                self.log(f"  Sample data point {i+1}: {point['cargo_id']} = {point['value']} (type: {type(point['value']).__name__})")
            
            response = requests.post(self.batch_endpoint.get(), headers=headers, json=data)
            
            if response.status_code == 200:
                self.log(f"✓ Data for node {node_name} successfully sent to Telemetry Harbor")
            else:
                self.log(f"✗ Failed to send data for node {node_name}. Status code: {response.status_code}")
                self.log(f"Response: {response.text[:200]}")
                
                # If there's an error, log the full request payload for debugging
                if response.status_code >= 400:
                    self.log("Request payload sample:")
                    payload_str = json.dumps(data)
                    self.log(payload_str[:500] + "..." if len(payload_str) > 500 else payload_str)
                    
        except requests.exceptions.RequestException as e:
            self.log(f"✗ Error sending data for node {node_name}: {str(e)}")
        except Exception as e:
            self.log(f"✗ Unexpected error sending data: {str(e)}")

def main():
    root = tk.Tk()
    app = MeshtasticTelemetryApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
