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
import queue

class MeshtasticTelemetryApp:
    def __init__(self, master):
        self.master = master
        master.title("Meshtastic Telemetry Harbor Integration")
        master.geometry("700x800")
        master.minsize(600, 750)
        
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self.bg_color = "#f0f4f8"
        self.master.configure(bg=self.bg_color)
        
        self.style = ttk.Style()
        self.style.configure("TFrame", background=self.bg_color)
        self.style.configure("TLabel", background=self.bg_color, font=("Arial", 10))
        self.style.configure("TButton", font=("Arial", 10, "bold"))
        self.style.configure("Header.TLabel", font=("Arial", 14, "bold"))
        self.style.configure("Warning.TLabel", background=self.bg_color, foreground="red", font=("Arial", 10, "bold"))
        
        self.collect_position_var = tk.BooleanVar(value=False)
        self.collect_device_metrics_var = tk.BooleanVar(value=False)
        self.collect_env_metrics_var = tk.BooleanVar(value=False)
        self.collect_air_quality_var = tk.BooleanVar(value=False)
        self.collect_power_metrics_var = tk.BooleanVar(value=False)
        self.collect_pax_counter_var = tk.BooleanVar(value=False)

        self.send_queue = queue.Queue()
        self.collection_thread = None
        self.sender_thread = None
        
        self.create_widgets()
        self.interface = None
        self.is_running = False
        self.nodes_lock = threading.Lock()

    def create_widgets(self):
        main_frame = ttk.Frame(self.master, padding="20", style="TFrame")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(1, weight=1)
        
        header_label = ttk.Label(main_frame, text="Meshtastic Telemetry Harbor Integration", style="Header.TLabel")
        header_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        settings_frame = ttk.LabelFrame(main_frame, text="Connection Settings", padding="10")
        settings_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        settings_frame.columnconfigure(1, weight=1)
        
        ttk.Label(settings_frame, text="API Key:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.api_key = ttk.Entry(settings_frame, width=50)
        self.api_key.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)

        # --- Changed: "Batch Endpoint" is now just "Endpoint" ---
        ttk.Label(settings_frame, text="Endpoint:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.endpoint = ttk.Entry(settings_frame, width=50)
        self.endpoint.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)

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

        selection_frame = ttk.LabelFrame(main_frame, text="Data to Collect", padding="10")
        selection_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Checkbutton(selection_frame, text="Position", variable=self.collect_position_var).grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Checkbutton(selection_frame, text="Device Metrics", variable=self.collect_device_metrics_var).grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Checkbutton(selection_frame, text="Environment", variable=self.collect_env_metrics_var).grid(row=0, column=2, sticky=tk.W, padx=5)
        ttk.Checkbutton(selection_frame, text="Air Quality", variable=self.collect_air_quality_var).grid(row=1, column=0, sticky=tk.W, padx=5)
        ttk.Checkbutton(selection_frame, text="Power", variable=self.collect_power_metrics_var).grid(row=1, column=1, sticky=tk.W, padx=5)
        ttk.Checkbutton(selection_frame, text="Pax Counter", variable=self.collect_pax_counter_var).grid(row=1, column=2, sticky=tk.W, padx=5)

        collection_frame = ttk.LabelFrame(main_frame, text="Timing Settings", padding="10")
        collection_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        collection_frame.columnconfigure(1, weight=1)
        
        ttk.Label(collection_frame, text="Collection Interval (sec):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.pushing_rate_var = tk.StringVar(value="900")
        self.pushing_rate_entry = ttk.Entry(collection_frame, textvariable=self.pushing_rate_var, width=10)
        self.pushing_rate_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)

        # --- Changed: "Batches Per Min" is now "Request Delay" ---
        ttk.Label(collection_frame, text="Request Delay (sec):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.request_delay_var = tk.StringVar(value="1.0")
        self.request_delay_entry = ttk.Entry(collection_frame, textvariable=self.request_delay_var, width=10)
        self.request_delay_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)

        hint_text = "Data is sent one point at a time. Adjust delay and interval to prevent backlog."
        ttk.Label(collection_frame, text=hint_text, font=("Arial", 9, "italic")).grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=5)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=(10, 10))
        
        self.start_stop_button = ttk.Button(button_frame, text="Start Collection", command=self.toggle_data_collection, width=20)
        self.start_stop_button.grid(row=0, column=0, padx=5)
        
        self.clear_log_button = ttk.Button(button_frame, text="Clear Log", command=self.clear_log, width=20)
        self.clear_log_button.grid(row=0, column=1, padx=5)

        self.rate_limit_warning_label = ttk.Label(main_frame, text="", style="Warning.TLabel")
        self.rate_limit_warning_label.grid(row=5, column=0, columnspan=2, pady=(0, 5))

        log_frame = ttk.LabelFrame(main_frame, text="Log Output", padding="10")
        log_frame.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        
        self.log_display = scrolledtext.ScrolledText(log_frame, width=80, height=20, wrap=tk.WORD)
        self.log_display.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E))
        
        main_frame.rowconfigure(6, weight=1)

    def show_rate_limit_warning(self):
        warning_text = "RATE LIMIT EXCEEDED! Your plan may not support this sending frequency."
        self.rate_limit_warning_label.config(text=warning_text)
        self.status_var.set("Warning: Rate Limit Exceeded")

    def refresh_ports(self):
        # ... (no changes in this section) ...
        self.com_ports = self.get_available_ports()
        self.com_port['values'] = self.com_ports
        if self.com_ports:
            self.com_port.set(self.com_ports[0])
        self.log("COM ports refreshed")

    def get_available_ports(self):
        # ... (no changes in this section) ...
        return [port.device for port in serial.tools.list_ports.comports()]

    def clear_log(self):
        # ... (no changes in this section) ...
        self.log_display.delete(1.0, tk.END)
        self.log("Log cleared")

    def log(self, message):
        # ... (no changes in this section) ...
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_display.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_display.see(tk.END)

    def toggle_data_collection(self):
        # ... (no changes in this section) ...
        if not self.is_running:
            self.start_data_collection()
        else:
            self.stop_data_collection()

    def start_data_collection(self):
        if not all([self.api_key.get().strip(), self.endpoint.get().strip(), self.com_port.get()]):
            messagebox.showerror("Error", "API Key, Endpoint, and COM Port are required.")
            return
        
        try:
            int(self.pushing_rate_var.get())
            float(self.request_delay_var.get())
        except ValueError:
            messagebox.showerror("Error", "Timing settings must be valid numbers.")
            return
        
        self.is_running = True
        self.rate_limit_warning_label.config(text="") 
        self.start_stop_button.config(text="Stop Collection")
        self.status_var.set("Running")
        self.log("Starting data collection...")
        
        try:
            self.log(f"Connecting to Meshtastic device on {self.com_port.get()}...")
            self.interface = meshtastic.serial_interface.SerialInterface(devPath=self.com_port.get())
            self.log("Connected to Meshtastic device successfully")
            
            pub.subscribe(self.on_receive, "meshtastic.receive")
            self.log("Subscribed to Meshtastic messages")
            
            self.collection_thread = threading.Thread(target=self.collect_data_loop, daemon=True)
            self.collection_thread.start()

            self.sender_thread = threading.Thread(target=self.process_send_queue, daemon=True)
            self.sender_thread.start()

        except Exception as e:
            self.log(f"Error connecting to Meshtastic device: {str(e)}")
            messagebox.showerror("Connection Error", f"Failed to connect: {str(e)}")
            self.stop_data_collection()

    def on_receive(self, packet, interface):
        # ... (no changes in this section) ...
        try:
            if 'decoded' in packet and 'text' in packet['decoded']:
                self.log(f"Received text message from {packet['from']}: {packet['decoded']['text']}")
        except Exception as e:
            self.log(f"Error processing received packet: {str(e)}")

    def stop_data_collection(self):
        # ... (no changes in this section) ...
        if not self.is_running:
            return

        self.is_running = False
        if self.status_var.get() != "Warning: Rate Limit Exceeded":
             self.status_var.set("Stopped")
        self.start_stop_button.config(text="Start Collection")
        self.log("Stopping data collection...")

        if self.sender_thread:
            self.send_queue.put(None) 
            self.sender_thread.join(timeout=2)
        if self.collection_thread:
            self.collection_thread.join(timeout=2)
        
        if self.interface:
            try:
                self.interface.close()
                self.log("Meshtastic interface closed")
            except Exception as e:
                self.log(f"Error closing interface: {str(e)}")
            finally:
                self.interface = None

    def collect_data_loop(self):
        # ... (no changes in this section, it still collects batches per node) ...
        while self.is_running:
            try:
                push_rate = int(self.pushing_rate_var.get())
                self.log("Starting new data collection cycle...")
                
                with self.nodes_lock:
                    all_nodes = copy.deepcopy(self.interface.nodes)

                if all_nodes:
                    self.log(f"Found {len(all_nodes)} nodes. Processing and queueing data...")
                    for node_id, node in all_nodes.items():
                        if not self.is_running: break
                        try:
                            node_data = self.process_single_node(node_id, node)
                            if node_data:
                                self.send_queue.put(node_data)
                        except Exception as e:
                            self.log(f"Error processing node {node_id}: {str(e)}")
                
                self.log(f"Collection cycle complete. Waiting {push_rate} seconds...")
                for _ in range(push_rate):
                    if not self.is_running: break
                    time.sleep(1)

            except Exception as e:
                self.log(f"Error in collection loop: {str(e)}")
                if not self.is_running: break
                time.sleep(10)

    # --- Changed: The entire sending loop is different ---
    def process_send_queue(self):
        """Processes batches from the queue by sending each data point individually."""
        while self.is_running:
            try:
                # Get a whole batch for one node
                node_data_batch = self.send_queue.get(timeout=1)
                
                if node_data_batch is None: break
                
                if self.is_running:
                    # Get the delay once per batch
                    try:
                        pause_duration = float(self.request_delay_var.get())
                        if pause_duration < 0: pause_duration = 0
                    except ValueError:
                        pause_duration = 1.0 # Default on error

                    # Iterate through the batch and send each point
                    for data_point in node_data_batch:
                        if not self.is_running: break
                        
                        self.send_telemetry_data(data_point)
                        time.sleep(pause_duration)

            except queue.Empty:
                continue
            except Exception as e:
                self.log(f"Error in sender thread: {str(e)}")
                time.sleep(5)

    def safe_cast(self, value, to_type, default=None):
        # ... (no changes in this section) ...
        try:
            if value is None: return default
            return to_type(value)
        except (ValueError, TypeError):
            self.log(f"Warning: Could not convert '{value}' to {to_type.__name__}, using default {default}")
            return default

    def create_data_point(self, time, ship_id, cargo_id, value, value_type=float):
        # ... (no changes in this section) ...
        converted_value = self.safe_cast(value, value_type)
        if converted_value is None: return None
        return {"time": str(time), "ship_id": str(ship_id), "cargo_id": str(cargo_id), "value": converted_value}

    def process_single_node(self, node_id, node):
        # ... (no changes in this section, it still creates a list of data points) ...
        current_time = datetime.utcnow().isoformat() + "Z"
        node_data = []
        user_info = node.get('user', {})
        node_name = user_info.get('longName', f"Unknown-{node_id[:8]}")
        
        if self.collect_position_var.get() and 'position' in node:
            pos = node['position']
            node_data.extend(filter(None, [ self.create_data_point(current_time, node_name, "latitude", pos.get('latitude'), float), self.create_data_point(current_time, node_name, "longitude", pos.get('longitude'), float), self.create_data_point(current_time, node_name, "altitude", pos.get('altitude'), int), self.create_data_point(current_time, node_name, "satsInView", pos.get('satsInView'), int) ]))
        if self.collect_device_metrics_var.get() and 'deviceMetrics' in node:
            dm = node['deviceMetrics']
            node_data.extend(filter(None, [ self.create_data_point(current_time, node_name, "BatteryLevel", dm.get('batteryLevel'), int), self.create_data_point(current_time, node_name, "Voltage", dm.get('voltage'), float), self.create_data_point(current_time, node_name, "ChannelUtilization", dm.get('channelUtilization'), float), self.create_data_point(current_time, node_name, "AirUtilTX", dm.get('airUtilTx'), float) ]))
        if self.collect_env_metrics_var.get() and 'environmentMetrics' in node:
            em = node['environmentMetrics']
            node_data.extend(filter(None, [ self.create_data_point(current_time, node_name, "Temperature", em.get('temperature'), float), self.create_data_point(current_time, node_name, "RelativeHumidity", em.get('relativeHumidity'), float), self.create_data_point(current_time, node_name, "BarometricPressure", em.get('barometricPressure'), float) ]))
        if self.collect_air_quality_var.get() and 'airQualityMetrics' in node:
            aqm = node['airQualityMetrics']
            node_data.extend(filter(None, [ self.create_data_point(current_time, node_name, "PM25", aqm.get('pm25Standard'), float), self.create_data_point(current_time, node_name, "CO2", aqm.get('co2'), int) ]))
        if self.collect_power_metrics_var.get() and 'powerMetrics' in node:
            pm = node['powerMetrics']
            node_data.extend(filter(None, [ self.create_data_point(current_time, node_name, "Power", pm.get('power'), float), self.create_data_point(current_time, node_name, "Current", pm.get('current'), float) ]))
        if self.collect_pax_counter_var.get() and 'paxcounter' in node:
            pax = node['paxcounter']
            node_data.extend(filter(None, [ self.create_data_point(current_time, node_name, "PaxCounter", pax.get('pax'), int) ]))
        
        if node_data:
             self.log(f"Processed {len(node_data)} points for Node: {node_name}")
        return node_data

    # --- Changed: This function now sends a single data point (a dictionary) ---
    def send_telemetry_data(self, data_point):
        """Sends a single data point to the endpoint."""
        if not data_point:
            return

        node_name = data_point.get('ship_id', 'Unknown Node')
        cargo_id = data_point.get('cargo_id', 'unknown_metric')
        
        headers = {"Content-Type": "application/json", "X-API-Key": self.api_key.get()}
        
        try:
            self.log(f"🚀 Sending '{cargo_id}' for node {node_name}...")
            # The JSON payload is now the single data_point dictionary
            response = requests.post(self.endpoint.get(), headers=headers, json=data_point, timeout=15)
            
            if response.status_code == 200:
                self.log(f"✓ Success.")
            elif response.status_code == 429:
                self.log(f"🛑 WARNING: Rate Limit Exceeded (429) for '{cargo_id}'.")
                self.master.after(0, self.show_rate_limit_warning)
            else:
                self.log(f"✗ FAILED to send '{cargo_id}'. Status: {response.status_code}")
                self.log(f"Response: {response.text[:200]}")
                
        except requests.exceptions.RequestException as e:
            self.log(f"✗ Network error sending '{cargo_id}': {str(e)}")
        except Exception as e:
            self.log(f"✗ Unexpected error sending '{cargo_id}': {str(e)}")

def main():
    root = tk.Tk()
    app = MeshtasticTelemetryApp(root)
    def on_closing():
        if app.is_running:
            app.stop_data_collection()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
