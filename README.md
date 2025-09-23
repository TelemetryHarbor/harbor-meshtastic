# Meshtastic Integration

The Meshtastic Integration script allows you to connect your Meshtastic device to Telemetry Harbor effortlessly. By running this Python code, you can send telemetry data from your Meshtastic device to your Telemetry Harbor account, where it can be visualized using Grafana.

## Features  

- **Seamless Device Connection**: Easily connect your Meshtastic device via a selected COM port.  
- **Batch Endpoint Support**: Send data directly to Telemetry Harbor's batch ingestion endpoint.  
- **API Key Authentication**: Ensure secure communication using your unique API key.  
- **Real-Time Data Push**: Continuously stream telemetry data for live monitoring and analysis.  
- **Grafana Compatibility**: Visualize your Meshtastic device data with rich Grafana dashboards.  


## How to Use  

1. **Prepare Your Meshtastic Device**:  
   - Ensure your Meshtastic device is connected and operational.  
   - Note the COM port associated with the device.  
---

2. **Set Up the Script**:  
   - Clone this repository:  
     ```bash
     git clone https://github.com/TelemetryHarbor/harbor-meshtastic.git
     cd harbor-meshtastic
     ```  
   - Install required dependencies:  
     ```bash
     pip install -r requirements.txt
     ```  
---
3. **Run the Script**:
    ```bash
     python app.py
     ```  
   - Execute the script and provide the required information:  
     - **API Normal (NOT BATCH) Endpoint**: Obtain this from your Telemetry Harbor account.  
     - **API Key**: Your unique key for secure communication.  
     - **COM Port**: The port your Meshtastic device is connected to.  


---
4. **Stream Data**:  
   - The script will push telemetry data from your device to the Telemetry Harbor API endpoint.  
---
5. **Visualize in Grafana**:  
   - Log in to your Telemetry Harbor Grafana instance.  
   - Access pre-configured dashboards to view and analyze your Meshtastic data.
