import dearpygui.dearpygui as dpg
import meshtastic
import meshtastic.serial_interface
from pubsub import pub
import threading
import queue
import time
import requests
from datetime import datetime
import copy
import serial.tools.list_ports


# ----------------- Helper Functions -----------------
def get_available_ports():
    """Gets a list of available serial COM ports."""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports] if ports else ["No Ports Found"]


# Global log queue to pass messages from threads to the GUI
log_queue = queue.Queue()


def log_message_to_queue(message):
    """Puts a log message into the global queue."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_queue.put(f"[{timestamp}] {message}")


# ----------------- Main App -----------------
class MeshtasticTelemetryApp:
    def __init__(self):
        # Data collection flags
        self.collect_position_var = False
        self.collect_device_metrics_var = False
        self.collect_env_metrics_var = False
        self.collect_air_quality_var = False
        self.collect_power_metrics_var = False
        self.collect_pax_counter_var = False

        self.send_queue = queue.Queue()
        self.collection_thread = None
        self.sender_thread = None
        self.interface = None
        self.is_running = False
        self.nodes_lock = threading.Lock()

    def log(self, message):
        """Sends a log message to the GUI via the thread-safe queue."""
        log_message_to_queue(message)

    # ----------------- Data Collection -----------------
    def toggle_data_collection(self):
        if not self.is_running:
            self.start_data_collection()
        else:
            self.stop_data_collection()

    def start_data_collection(self):
        api_key = dpg.get_value("api_key_input").strip()
        endpoint = dpg.get_value("endpoint_input").strip()
        com_port = dpg.get_value("com_port_combo")

        if not (api_key and endpoint and com_port):
            self.log("ERROR: API Key, Endpoint, and COM Port are required.")
            return

        try:
            int(dpg.get_value("interval_input"))
            float(dpg.get_value("delay_input"))
        except ValueError:
            self.log("ERROR: Timing settings must be valid numbers.")
            return

        self.collect_position_var = dpg.get_value("position_check")
        self.collect_device_metrics_var = dpg.get_value("device_metrics_check")
        self.collect_env_metrics_var = dpg.get_value("env_metrics_check")
        self.collect_air_quality_var = dpg.get_value("air_quality_check")
        self.collect_power_metrics_var = dpg.get_value("power_check")
        self.collect_pax_counter_var = dpg.get_value("pax_check")

        self.api_key = api_key
        self.endpoint = endpoint
        self.pushing_rate = int(dpg.get_value("interval_input"))
        self.request_delay = float(dpg.get_value("delay_input"))
        self.com_port = com_port

        self.is_running = True
        dpg.set_value("rate_warning_text", "")
        dpg.set_value("status_text", "Status: Running")
        dpg.configure_item("start_stop_button", label="Stop Collection")
        self.log("Starting data collection...")

        try:
            self.log(f"Connecting to Meshtastic device on {self.com_port}...")
            self.interface = meshtastic.serial_interface.SerialInterface(
                devPath=self.com_port
            )
            self.log("Connected to Meshtastic device successfully.")
            pub.subscribe(self.on_receive, "meshtastic.receive")
            self.log("Subscribed to Meshtastic messages.")
            self.collection_thread = threading.Thread(
                target=self.collect_data_loop, daemon=True
            )
            self.collection_thread.start()
            self.sender_thread = threading.Thread(
                target=self.process_send_queue, daemon=True
            )
            self.sender_thread.start()
        except Exception as e:
            self.log(f"Error connecting to Meshtastic device: {e}")
            self.stop_data_collection()

    def stop_data_collection(self):
        if not self.is_running:
            return
        self.is_running = False
        self.log("Stopping data collection...")
        if self.sender_thread:
            self.send_queue.put(None)
            self.sender_thread.join(timeout=2)
        if self.collection_thread:
            self.collection_thread.join(timeout=2)
        if self.interface:
            try:
                self.interface.close()
                self.log("Meshtastic interface closed.")
            except Exception as e:
                self.log(f"Error closing interface: {e}")
            finally:
                self.interface = None
        dpg.set_value("status_text", "Status: Stopped")
        dpg.configure_item("start_stop_button", label="Start Collection")

    # The rest of your MeshtasticTelemetryApp class methods (collect_data_loop,
    # process_send_queue, process_single_node, etc.) remain exactly the same.
    # ... (all methods from the original class go here) ...
    # ----------------- Collection Loop -----------------
    def collect_data_loop(self):
        while self.is_running:
            try:
                self.log("Starting new data collection cycle...")

                with self.nodes_lock:
                    if not self.interface:
                        self.log("Interface not available. Skipping cycle.")
                        time.sleep(5)
                        continue
                    all_nodes = copy.deepcopy(self.interface.nodes)

                if all_nodes:
                    self.log(
                        f"Found {len(all_nodes)} nodes. Processing and queueing data..."
                    )
                    for node_id, node in all_nodes.items():
                        if not self.is_running:
                            break
                        node_data = self.process_single_node(node_id, node)
                        if node_data:
                            self.send_queue.put(node_data)
                else:
                    self.log("No nodes found in this cycle.")

                self.log(
                    f"Collection cycle complete. Waiting {self.pushing_rate} seconds..."
                )
                for _ in range(self.pushing_rate):
                    if not self.is_running:
                        break
                    time.sleep(1)

            except Exception as e:
                self.log(f"Error in collection loop: {e}")
                if not self.is_running:
                    break
                time.sleep(10)

    def process_send_queue(self):
        while self.is_running:
            try:
                node_data_batch = self.send_queue.get(timeout=1)
                if node_data_batch is None:  # Shutdown signal
                    break

                pause_duration = max(self.request_delay, 0)

                for data_point in node_data_batch:
                    if not self.is_running:
                        break
                    self.send_telemetry_data(data_point)
                    time.sleep(pause_duration)

            except queue.Empty:
                continue
            except Exception as e:
                self.log(f"Error in sender thread: {e}")
                time.sleep(5)

    def on_receive(self, packet, interface):
        try:
            if "decoded" in packet and "text" in packet["decoded"]:
                self.log(
                    f"Received text from {packet.get('from', 'N/A')}: {packet['decoded']['text']}"
                )
        except Exception as e:
            self.log(f"Error processing received packet: {e}")

    # ----------------- Node Processing -----------------
    def safe_cast(self, value, to_type, default=None):
        try:
            if value is None:
                return default
            return to_type(value)
        except (ValueError, TypeError):
            self.log(
                f"Warning: Could not convert '{value}' to {to_type.__name__}, using default {default}"
            )
            return default

    def create_data_point(self, time_str, ship_id, cargo_id, value, value_type=float):
        converted_value = self.safe_cast(value, value_type)
        if converted_value is None:
            return None
        return {
            "time": str(time_str),
            "ship_id": str(ship_id),
            "cargo_id": str(cargo_id),
            "value": converted_value,
        }

    def process_single_node(self, node_id, node):
        current_time = datetime.utcnow().isoformat() + "Z"
        node_data = []
        user_info = node.get("user", {})
        node_name = user_info.get("longName", f"Unknown-{node_id[:8]}")

        # Position Data
        if self.collect_position_var and "position" in node:
            pos = node["position"]
            node_data.extend(
                filter(
                    None,
                    [
                        self.create_data_point(
                            current_time,
                            node_name,
                            "latitude",
                            pos.get("latitude"),
                            float,
                        ),
                        self.create_data_point(
                            current_time,
                            node_name,
                            "longitude",
                            pos.get("longitude"),
                            float,
                        ),
                        self.create_data_point(
                            current_time,
                            node_name,
                            "altitude",
                            pos.get("altitude"),
                            int,
                        ),
                        self.create_data_point(
                            current_time,
                            node_name,
                            "satsInView",
                            pos.get("satsInView"),
                            int,
                        ),
                    ],
                )
            )

        # Device Metrics
        if self.collect_device_metrics_var and "deviceMetrics" in node:
            dm = node["deviceMetrics"]
            node_data.extend(
                filter(
                    None,
                    [
                        self.create_data_point(
                            current_time,
                            node_name,
                            "BatteryLevel",
                            dm.get("batteryLevel"),
                            int,
                        ),
                        self.create_data_point(
                            current_time, node_name, "Voltage", dm.get("voltage"), float
                        ),
                        self.create_data_point(
                            current_time,
                            node_name,
                            "ChannelUtilization",
                            dm.get("channelUtilization"),
                            float,
                        ),
                        self.create_data_point(
                            current_time,
                            node_name,
                            "AirUtilTX",
                            dm.get("airUtilTx"),
                            float,
                        ),
                    ],
                )
            )

        # Environment Metrics
        if self.collect_env_metrics_var and "environmentMetrics" in node:
            em = node["environmentMetrics"]
            node_data.extend(
                filter(
                    None,
                    [
                        self.create_data_point(
                            current_time,
                            node_name,
                            "Temperature",
                            em.get("temperature"),
                            float,
                        ),
                        self.create_data_point(
                            current_time,
                            node_name,
                            "RelativeHumidity",
                            em.get("relativeHumidity"),
                            float,
                        ),
                        self.create_data_point(
                            current_time,
                            node_name,
                            "BarometricPressure",
                            em.get("barometricPressure"),
                            float,
                        ),
                    ],
                )
            )

        # Air Quality Metrics
        if self.collect_air_quality_var and "airQualityMetrics" in node:
            aqm = node["airQualityMetrics"]
            node_data.extend(
                filter(
                    None,
                    [
                        self.create_data_point(
                            current_time,
                            node_name,
                            "PM25",
                            aqm.get("pm25Standard"),
                            float,
                        ),
                        self.create_data_point(
                            current_time, node_name, "CO2", aqm.get("co2"), int
                        ),
                    ],
                )
            )

        # Power Metrics
        if self.collect_power_metrics_var and "powerMetrics" in node:
            pm = node["powerMetrics"]
            node_data.extend(
                filter(
                    None,
                    [
                        self.create_data_point(
                            current_time, node_name, "Power", pm.get("power"), float
                        ),
                        self.create_data_point(
                            current_time, node_name, "Current", pm.get("current"), float
                        ),
                    ],
                )
            )

        # Pax Counter
        if self.collect_pax_counter_var and "paxcounter" in node:
            pax = node["paxcounter"]
            node_data.extend(
                filter(
                    None,
                    [
                        self.create_data_point(
                            current_time, node_name, "PaxCounter", pax.get("pax"), int
                        )
                    ],
                )
            )

        if node_data:
            self.log(f"Processed {len(node_data)} points for Node: {node_name}")
        return node_data

    # ----------------- Sending Data -----------------
    def send_telemetry_data(self, data_point):
        if not data_point:
            return

        node_name = data_point.get("ship_id", "Unknown Node")
        cargo_id = data_point.get("cargo_id", "unknown_metric")
        headers = {"Content-Type": "application/json", "X-API-Key": self.api_key}

        try:
            self.log(f"🚀 Sending '{cargo_id}' for node {node_name}...")
            response = requests.post(
                self.endpoint, headers=headers, json=data_point, timeout=15
            )

            if response.status_code == 200:
                self.log(f"✓ Success.")
            elif response.status_code == 429:
                self.log(f"🛑 WARNING: Rate Limit Exceeded (429) for '{cargo_id}'.")
                dpg.set_value("rate_warning_text", "RATE LIMIT EXCEEDED!")
            else:
                self.log(
                    f"✗ FAILED to send '{cargo_id}'. Status: {response.status_code}"
                )
                self.log(f"Response: {response.text[:200]}")

        except requests.exceptions.RequestException as e:
            self.log(f"✗ Network error sending '{cargo_id}': {e}")
        except Exception as e:
            self.log(f"✗ Unexpected error sending '{cargo_id}': {e}")


# ----------------- GUI and Main Loop -----------------
def create_gui(app_instance):
    dpg.create_context()

    with dpg.window(
        label="Meshtastic Telemetry Harbor Integration", tag="primary_window"
    ):
        dpg.add_text("Meshtastic Telemetry Harbor Integration")
        dpg.add_separator()

        with dpg.collapsing_header(label="Connection Settings", default_open=True):
            dpg.add_input_text(label="API Key", tag="api_key_input", width=300)
            dpg.add_input_text(label="Endpoint", tag="endpoint_input", width=300)
            with dpg.group(horizontal=True):
                dpg.add_combo(
                    items=get_available_ports(),
                    label="COM Port",
                    tag="com_port_combo",
                    width=250,
                )

                def refresh_ports():
                    dpg.configure_item("com_port_combo", items=get_available_ports())

                dpg.add_button(label="⟳", callback=refresh_ports)

        with dpg.collapsing_header(label="Data to Collect", default_open=True):
            dpg.add_checkbox(label="Position", tag="position_check", default_value=True)
            dpg.add_checkbox(
                label="Device Metrics", tag="device_metrics_check", default_value=True
            )
            dpg.add_checkbox(
                label="Environment", tag="env_metrics_check", default_value=True
            )
            dpg.add_checkbox(label="Air Quality", tag="air_quality_check")
            dpg.add_checkbox(label="Power", tag="power_check")
            dpg.add_checkbox(label="Pax Counter", tag="pax_check")

        with dpg.collapsing_header(label="Timing Settings", default_open=True):
            dpg.add_input_text(
                label="Collection Interval (sec)",
                tag="interval_input",
                default_value="900",
                width=150,
            )
            dpg.add_input_text(
                label="Request Delay (sec)",
                tag="delay_input",
                default_value="1.0",
                width=150,
            )

        dpg.add_separator()

        with dpg.group(horizontal=True):
            dpg.add_button(
                label="Start Collection",
                tag="start_stop_button",
                callback=app_instance.toggle_data_collection,
            )

            def clear_log():
                dpg.set_value("log_text", "")

            dpg.add_button(label="Clear Log", callback=clear_log)

        dpg.add_text("", tag="rate_warning_text", color=(255, 0, 0))

        # Log window
        dpg.add_text("Log:")
        dpg.add_input_text(
            tag="log_text", multiline=True, readonly=True, width=-1, height=300
        )

        dpg.add_separator()
        dpg.add_text("Status: Ready", tag="status_text")

    dpg.create_viewport(title="Meshtastic Telemetry", width=600, height=800)
    dpg.setup_dearpygui()
    dpg.show_viewport()


def main():
    app = MeshtasticTelemetryApp()
    create_gui(app)

    log_buffer = []

    while dpg.is_dearpygui_running():
        # Process log messages from the queue
        while not log_queue.empty():
            log_buffer.append(log_queue.get())

        if log_buffer:
            # Update the log text box in a batch
            current_log = dpg.get_value("log_text")
            new_log = current_log + "\n".join(log_buffer) + "\n"
            dpg.set_value("log_text", new_log)
            log_buffer.clear()

        dpg.render_dearpygui_frame()

    # Cleanup
    if app.is_running:
        app.stop_data_collection()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
